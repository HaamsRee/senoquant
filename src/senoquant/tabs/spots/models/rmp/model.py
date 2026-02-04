"""RMP spot detector implementation."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterable

import numpy as np
from scipy import ndimage as ndi
from skimage.filters import laplace, threshold_otsu
from skimage.morphology import local_maxima
from skimage.segmentation import watershed

try:
    import torch
    import torch.nn.functional as F
except ImportError:  # pragma: no cover - optional dependency
    torch = None  # type: ignore[assignment]
    F = None  # type: ignore[assignment]

from ..base import SenoQuantSpotDetector
from senoquant.utils import layer_data_asarray

try:
    import dask.array as da
except ImportError:  # pragma: no cover - optional dependency
    da = None  # type: ignore[assignment]

try:  # pragma: no cover - optional dependency
    from dask.distributed import Client, LocalCluster
except ImportError:  # pragma: no cover - optional dependency
    Client = None  # type: ignore[assignment]
    LocalCluster = None  # type: ignore[assignment]


Array2D = np.ndarray
KernelShape = tuple[int, int]
EPS = 1e-6
NOISE_FLOOR_SIGMA = 1.5
MIN_SCALE_SIGMA = 5.0
SIGNAL_SCALE_QUANTILE = 99.9
USE_LAPLACE_FOR_PEAKS = False


def _ensure_torch_available() -> None:
    """Ensure torch is available for RMP processing."""
    if torch is None or F is None:  # pragma: no cover - import guard
        raise ImportError("torch is required for the RMP detector.")


def _torch_device() -> "torch.device":
    """Return the best available torch device (CUDA, MPS, then CPU)."""
    _ensure_torch_available()
    assert torch is not None
    if torch.cuda.is_available():
        return torch.device("cuda")
    mps_backend = getattr(torch.backends, "mps", None)
    if mps_backend is not None and mps_backend.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def _to_image_tensor(image: np.ndarray, *, device: "torch.device") -> "torch.Tensor":
    """Convert a 2D image array to a [1,1,H,W] torch tensor."""
    _ensure_torch_available()
    assert torch is not None
    tensor = torch.as_tensor(image, dtype=torch.float32, device=device)
    if tensor.ndim != 2:
        raise ValueError("Expected a 2D image for tensor conversion.")
    return tensor.unsqueeze(0).unsqueeze(0)


def _rotate_tensor(image: "torch.Tensor", angle: float) -> "torch.Tensor":
    """Rotate a [1,1,H,W] tensor with reflection padding."""
    _ensure_torch_available()
    assert torch is not None
    assert F is not None
    if image.ndim != 4:
        raise ValueError("Expected a [N,C,H,W] tensor for rotation.")

    height = float(image.shape[-2])
    width = float(image.shape[-1])
    hw_ratio = height / width if width > 0 else 1.0
    wh_ratio = width / height if height > 0 else 1.0

    radians = np.deg2rad(float(angle))
    cos_v = float(np.cos(radians))
    sin_v = float(np.sin(radians))
    # affine_grid operates in normalized coordinates; non-square images need
    # aspect-ratio correction on the off-diagonal terms.
    theta = torch.tensor(
        [[[cos_v, -sin_v * hw_ratio, 0.0], [sin_v * wh_ratio, cos_v, 0.0]]],
        dtype=image.dtype,
        device=image.device,
    )
    grid = F.affine_grid(theta, image.size(), align_corners=False)
    return F.grid_sample(
        image,
        grid,
        mode="bilinear",
        padding_mode="reflection",
        align_corners=False,
    )


def _grayscale_opening_tensor(
    image: "torch.Tensor",
    kernel_shape: KernelShape,
) -> "torch.Tensor":
    """Apply grayscale opening (erosion then dilation) with a rectangular kernel."""
    _ensure_torch_available()
    assert F is not None
    img_h = int(image.shape[-2])
    img_w = int(image.shape[-1])
    ky = min(max(1, int(kernel_shape[0])), max(1, img_h))
    kx = min(max(1, int(kernel_shape[1])), max(1, img_w))
    pad_y = ky // 2
    pad_x = kx // 2
    pad = (pad_x, pad_x, pad_y, pad_y)

    # Erosion via pooling uses the min-over-window identity:
    # min(x) == -max(-x). Missing the inner negation flips morphology behavior.
    eroded = -F.max_pool2d(
        F.pad(-image, pad, mode="reflect"),
        kernel_size=(ky, kx),
        stride=1,
    )
    opened = F.max_pool2d(
        F.pad(eroded, pad, mode="reflect"),
        kernel_size=(ky, kx),
        stride=1,
    )
    return opened


def _kernel_shape(footprint: KernelShape | np.ndarray) -> KernelShape:
    """Return kernel shape from either a tuple footprint or array."""
    if isinstance(footprint, tuple):
        return max(1, int(footprint[0])), max(1, int(footprint[1]))
    arr = np.asarray(footprint)
    if arr.ndim != 2:
        raise ValueError("Structuring element must be 2D.")
    return max(1, int(arr.shape[0])), max(1, int(arr.shape[1]))


def _normalize_image(image: np.ndarray) -> np.ndarray:
    """Normalize an image to float32 in [0, 1]."""
    device = _torch_device()
    data = np.asarray(image, dtype=np.float32)
    _ensure_torch_available()
    assert torch is not None
    tensor = torch.as_tensor(data, dtype=torch.float32, device=device)
    min_val = tensor.amin()
    max_val = tensor.amax()
    if bool(max_val <= min_val):
        return np.zeros_like(data, dtype=np.float32)
    normalized = (tensor - min_val) / (max_val - min_val)
    normalized = normalized.clamp(0.0, 1.0)
    return normalized.detach().cpu().numpy().astype(np.float32, copy=False)


def _clamp_threshold(value: float) -> float:
    """Clamp threshold to the inclusive [0.0, 1.0] range."""
    return float(np.clip(value, 0.0, 1.0))


def _normalize_top_hat_unit(image: np.ndarray) -> np.ndarray:
    """Robust normalization for top-hat output."""
    data = np.asarray(image, dtype=np.float32)
    finite_mask = np.isfinite(data)
    if not np.any(finite_mask):
        return np.zeros_like(data, dtype=np.float32)

    valid = data[finite_mask]
    background = float(np.nanmedian(valid))
    sigma = 1.4826 * float(np.nanmedian(np.abs(valid - background)))

    if (not np.isfinite(sigma)) or sigma <= EPS:
        sigma = float(np.nanstd(valid))
        if (not np.isfinite(sigma)) or sigma <= EPS:
            return np.zeros_like(data, dtype=np.float32)

    noise_floor = background + (NOISE_FLOOR_SIGMA * sigma)
    residual = np.clip(data - noise_floor, 0.0, None)
    residual = np.where(finite_mask, residual, 0.0)

    positive = residual[residual > 0.0]
    if positive.size == 0:
        return np.zeros_like(data, dtype=np.float32)
    high = float(np.nanpercentile(positive, SIGNAL_SCALE_QUANTILE))
    if (not np.isfinite(high)) or high <= EPS:
        high = float(np.nanmax(positive))
        if (not np.isfinite(high)) or high <= EPS:
            return np.zeros_like(data, dtype=np.float32)

    scale = max(high, MIN_SCALE_SIGMA * sigma, EPS)
    normalized = np.clip(residual / scale, 0.0, 1.0)
    return normalized.astype(np.float32, copy=False)


def _markers_from_local_maxima(
    enhanced: np.ndarray,
    threshold: float,
    use_laplace: bool = USE_LAPLACE_FOR_PEAKS,
) -> np.ndarray:
    """Build marker labels from local maxima and thresholding."""
    connectivity = max(1, min(2, enhanced.ndim))
    response = (
        laplace(enhanced.astype(np.float32, copy=False))
        if use_laplace
        else np.asarray(enhanced, dtype=np.float32)
    )
    mask = local_maxima(response, connectivity=connectivity)
    mask = mask & (response > threshold)

    markers = np.zeros(enhanced.shape, dtype=np.int32)
    coords = np.argwhere(mask)
    if coords.size == 0:
        return markers

    max_indices = np.asarray(enhanced.shape) - 1
    coords = np.clip(coords, 0, max_indices)
    markers[tuple(coords.T)] = 1

    structure = ndi.generate_binary_structure(enhanced.ndim, 1)
    marker_labels, _num = ndi.label(markers > 0, structure=structure)
    return marker_labels.astype(np.int32, copy=False)


def _segment_from_markers(
    enhanced: np.ndarray,
    markers: np.ndarray,
    threshold: float,
) -> np.ndarray:
    """Run watershed from local-maxima markers inside threshold foreground."""
    foreground = enhanced > threshold
    if not np.any(foreground):
        return np.zeros_like(enhanced, dtype=np.int32)

    seeded_markers = markers * foreground.astype(np.int32, copy=False)
    if not np.any(seeded_markers > 0):
        return np.zeros_like(enhanced, dtype=np.int32)

    labels = watershed(
        -enhanced.astype(np.float32, copy=False),
        markers=seeded_markers,
        mask=foreground,
    )
    return labels.astype(np.int32, copy=False)

def _pad_tensor_for_rotation(
    image: "torch.Tensor",
) -> tuple["torch.Tensor", tuple[int, int]]:
    """Pad a [1,1,H,W] tensor to preserve content after rotations."""
    nrows = int(image.shape[-2])
    ncols = int(image.shape[-1])
    diagonal = int(np.ceil(np.sqrt(nrows**2 + ncols**2)))
    rows_to_pad = int(np.ceil((diagonal - nrows) / 2))
    cols_to_pad = int(np.ceil((diagonal - ncols) / 2))
    assert F is not None
    padded = F.pad(
        image,
        (cols_to_pad, cols_to_pad, rows_to_pad, rows_to_pad),
        mode="reflect",
    )
    return padded, (rows_to_pad, cols_to_pad)

def _rmp_opening(
    input_image: Array2D,
    structuring_element: KernelShape | Array2D,
    rotation_angles: Iterable[int],
) -> Array2D:
    """Perform the RMP opening on an image."""
    device = _torch_device()
    tensor = _to_image_tensor(np.asarray(input_image, dtype=np.float32), device=device)
    padded, (newy, newx) = _pad_tensor_for_rotation(tensor)
    kernel_shape = _kernel_shape(structuring_element)

    rotated_images = [_rotate_tensor(padded, angle) for angle in rotation_angles]
    opened_images = [
        _grayscale_opening_tensor(image, kernel_shape) for image in rotated_images
    ]
    rotated_back = [
        _rotate_tensor(image, -angle)
        for image, angle in zip(opened_images, rotation_angles)
    ]
    stacked = torch.stack(rotated_back, dim=0)
    union_image = stacked.max(dim=0).values
    cropped = union_image[
        ...,
        newy : newy + input_image.shape[0],
        newx : newx + input_image.shape[1],
    ]
    return cropped.squeeze(0).squeeze(0).detach().cpu().numpy().astype(np.float32, copy=False)


def _rmp_top_hat(
    input_image: Array2D,
    structuring_element: Array2D,
    rotation_angles: Iterable[int],
) -> Array2D:
    """Return the top-hat (background subtracted) image."""
    opened_image = _rmp_opening(input_image, structuring_element, rotation_angles)
    return input_image - opened_image


def _compute_top_hat(input_image: Array2D, config: "RMPSettings") -> Array2D:
    """Compute the RMP top-hat response for a 2D image."""
    denoising_se: KernelShape = (1, config.denoising_se_length)
    extraction_se: KernelShape = (1, config.extraction_se_length)
    rotation_angles = tuple(range(0, 180, config.angle_spacing))

    working = (
        _rmp_opening(input_image, denoising_se, rotation_angles)
        if config.enable_denoising
        else input_image
    )
    return _rmp_top_hat(working, extraction_se, rotation_angles)


def _ensure_dask_available() -> None:
    """Ensure dask is installed for tiled execution."""
    if da is None:  # pragma: no cover - import guard
        raise ImportError("dask is required for distributed spot detection.")


def _ensure_distributed_available() -> None:
    """Ensure dask.distributed is installed for distributed execution."""
    if Client is None or LocalCluster is None:  # pragma: no cover - import guard
        raise ImportError("dask.distributed is required for distributed execution.")


def _dask_available() -> bool:
    """Return True when dask is available."""
    return da is not None


def _distributed_available() -> bool:
    """Return True when dask.distributed is available."""
    return Client is not None and LocalCluster is not None and da is not None


def _recommended_overlap(config: "RMPSettings") -> int:
    """Derive a suitable overlap from structuring-element sizes."""
    lengths = [config.extraction_se_length]
    if config.enable_denoising:
        lengths.append(config.denoising_se_length)
    return max(1, max(lengths) * 2)


@contextmanager
def _cluster_client():
    """Yield a connected Dask client backed by a local cluster."""
    _ensure_distributed_available()
    with LocalCluster() as cluster:
        with Client(cluster) as client:
            yield client


def _rmp_top_hat_block(block: np.ndarray, config: "RMPSettings") -> np.ndarray:
    """Return background-subtracted tile via the RMP top-hat pipeline."""
    denoising_se: KernelShape = (1, config.denoising_se_length)
    extraction_se: KernelShape = (1, config.extraction_se_length)
    rotation_angles = tuple(range(0, 180, config.angle_spacing))

    working = (
        _rmp_opening(block, denoising_se, rotation_angles)
        if config.enable_denoising
        else block
    )
    top_hat = working - _rmp_opening(working, extraction_se, rotation_angles)
    return np.asarray(top_hat, dtype=np.float32)


def _compute_top_hat_2d(
    image_2d: np.ndarray,
    config: "RMPSettings",
    *,
    use_tiled: bool,
    distributed: bool,
    client: "Client | None" = None,
) -> np.ndarray:
    """Compute a top-hat image for one 2D plane."""
    if use_tiled:
        return _rmp_top_hat_tiled(
            image_2d,
            config=config,
            distributed=distributed,
            client=client,
        )
    return _compute_top_hat(image_2d, config)


def _compute_top_hat_nd(
    image: np.ndarray,
    config: "RMPSettings",
    *,
    use_tiled: bool,
    use_distributed: bool,
) -> np.ndarray:
    """Compute top-hat for 2D images or slice-wise for 3D stacks."""
    if image.ndim == 2:
        return _compute_top_hat_2d(
            image,
            config,
            use_tiled=use_tiled,
            distributed=use_distributed,
        )

    top_hat_stack = np.zeros_like(image, dtype=np.float32)
    if use_tiled and use_distributed:
        with _cluster_client() as client:
            for z in range(image.shape[0]):
                top_hat_stack[z] = _compute_top_hat_2d(
                    image[z],
                    config,
                    use_tiled=True,
                    distributed=True,
                    client=client,
                )
        return top_hat_stack

    for z in range(image.shape[0]):
        top_hat_stack[z] = _compute_top_hat_2d(
            image[z],
            config,
            use_tiled=use_tiled,
            distributed=False,
        )
    return top_hat_stack


def _postprocess_top_hat(
    top_hat: np.ndarray,
    config: "RMPSettings",
) -> tuple[np.ndarray, np.ndarray]:
    """Apply normalization, thresholding, marker extraction, and watershed."""
    top_hat_normalized = _normalize_top_hat_unit(top_hat)
    threshold = (
        _clamp_threshold(float(threshold_otsu(top_hat_normalized)))
        if config.auto_threshold
        else config.manual_threshold
    )
    markers = _markers_from_local_maxima(
        top_hat_normalized,
        threshold,
        use_laplace=USE_LAPLACE_FOR_PEAKS,
    )
    labels = _segment_from_markers(
        top_hat_normalized,
        markers,
        threshold,
    )
    return labels, top_hat_normalized


def _rmp_top_hat_tiled(
    image: np.ndarray,
    config: "RMPSettings",
    chunk_size: tuple[int, int] = (1024, 1024),
    overlap: int | None = None,
    distributed: bool = False,
    client: "Client | None" = None,
) -> np.ndarray:
    """Return the RMP top-hat image using tiled execution."""
    _ensure_dask_available()

    effective_overlap = _recommended_overlap(config) if overlap is None else overlap

    def block_fn(block, block_info=None):
        return _rmp_top_hat_block(block, config)

    arr = da.from_array(image.astype(np.float32, copy=False), chunks=chunk_size)
    result = arr.map_overlap(
        block_fn,
        depth=(effective_overlap, effective_overlap),
        boundary="reflect",
        dtype=np.float32,
        trim=True,
    )

    if distributed:
        _ensure_distributed_available()
        if client is None:
            with _cluster_client() as temp_client:
                return temp_client.compute(result).result()
        return client.compute(result).result()

    return result.compute()


@dataclass(slots=True)
class RMPSettings:
    """Configuration for the RMP detector."""

    denoising_se_length: int = 2
    extraction_se_length: int = 10
    angle_spacing: int = 5
    auto_threshold: bool = True
    manual_threshold: float = 0.05
    enable_denoising: bool = True


class RMPDetector(SenoQuantSpotDetector):
    """RMP spot detector implementation."""

    def __init__(self, models_root=None) -> None:
        super().__init__("rmp", models_root=models_root)

    def run(self, **kwargs) -> dict:
        """Run the RMP detector and return instance labels.

        Parameters
        ----------
        **kwargs
            layer : napari.layers.Image or None
                Image layer used for spot detection.
            settings : dict
                Detector settings keyed by the details.json schema.

        Returns
        -------
        dict
            Dictionary with ``mask`` key containing instance labels.
        """
        layer = kwargs.get("layer")
        if layer is None:
            return {"mask": None, "points": None}
        if getattr(layer, "rgb", False):
            raise ValueError("RMP requires single-channel images.")

        settings = kwargs.get("settings", {})
        manual_threshold = _clamp_threshold(
            float(settings.get("manual_threshold", 0.5))
        )
        config = RMPSettings(
            denoising_se_length=int(settings.get("denoising_kernel_length", 2)),
            extraction_se_length=int(settings.get("extraction_kernel_length", 10)),
            angle_spacing=int(settings.get("angle_spacing", 5)),
            auto_threshold=bool(settings.get("auto_threshold", True)),
            manual_threshold=manual_threshold,
            enable_denoising=bool(settings.get("enable_denoising", True)),
        )

        if config.angle_spacing <= 0:
            raise ValueError("Angle spacing must be positive.")
        if config.denoising_se_length <= 0 or config.extraction_se_length <= 0:
            raise ValueError("Structuring element lengths must be positive.")

        data = layer_data_asarray(layer)
        if data.ndim not in (2, 3):
            raise ValueError("RMP expects 2D images or 3D stacks.")

        normalized = _normalize_image(data)

        use_distributed = _distributed_available()
        use_tiled = _dask_available()
        top_hat = _compute_top_hat_nd(
            normalized,
            config,
            use_tiled=use_tiled,
            use_distributed=use_distributed,
        )
        labels, _top_hat_normalized = _postprocess_top_hat(top_hat, config)
        return {
            "mask": labels,
            # "debug_images": {
            #     "debug_top_hat_before_threshold": _top_hat_normalized.astype(
            #         np.float32,
            #         copy=False,
            #     ),
            # },
        }
