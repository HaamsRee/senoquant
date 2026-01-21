"""RMP spot detector implementation."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterable

import numpy as np
from scipy import ndimage as ndi
from skimage.filters import threshold_otsu
from skimage.measure import label
from skimage.morphology import opening, rectangle
from skimage.segmentation import watershed
from skimage.feature import peak_local_max
from skimage.transform import rotate
from skimage.util import img_as_ubyte

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

try:  # pragma: no cover - optional dependency
    from dask_cuda import LocalCUDACluster
except ImportError:  # pragma: no cover - optional dependency
    LocalCUDACluster = None  # type: ignore[assignment]

try:  # pragma: no cover - optional dependency
    import cupy as cp
    from cucim.skimage.filters import threshold_otsu as gpu_threshold_otsu
    from cucim.skimage.morphology import opening as gpu_opening, rectangle as gpu_rectangle
    from cucim.skimage.transform import rotate as gpu_rotate
except ImportError:  # pragma: no cover - optional dependency
    cp = None  # type: ignore[assignment]
    gpu_threshold_otsu = None  # type: ignore[assignment]
    gpu_opening = None  # type: ignore[assignment]
    gpu_rectangle = None  # type: ignore[assignment]
    gpu_rotate = None  # type: ignore[assignment]


Array2D = np.ndarray


def _normalize_image(image: np.ndarray) -> np.ndarray:
    """Normalize an image to float32 in [0, 1]."""
    data = np.asarray(image, dtype=np.float32)
    min_val = float(data.min())
    max_val = float(data.max())
    if max_val <= min_val:
        return np.zeros_like(data, dtype=np.float32)
    data = (data - min_val) / (max_val - min_val)
    return np.clip(data, 0.0, 1.0)


def _pad_for_rotation(image: Array2D) -> tuple[Array2D, tuple[int, int]]:
    """Pad image to preserve content after rotations."""
    nrows, ncols = image.shape[:2]
    diagonal = int(np.ceil(np.sqrt(nrows**2 + ncols**2)))

    rows_to_pad = int(np.ceil((diagonal - nrows) / 2))
    cols_to_pad = int(np.ceil((diagonal - ncols) / 2))

    padded_image = np.pad(
        image,
        ((rows_to_pad, rows_to_pad), (cols_to_pad, cols_to_pad)),
        mode="reflect",
    )

    return padded_image, (rows_to_pad, cols_to_pad)


def _rmp_opening(
    input_image: Array2D,
    structuring_element: Array2D,
    rotation_angles: Iterable[int],
) -> Array2D:
    """Perform the RMP opening on an image."""
    padded_image, (newy, newx) = _pad_for_rotation(input_image)
    rotated_images = [
        rotate(padded_image, angle, mode="reflect") for angle in rotation_angles
    ]
    opened_images = [
        opening(image, footprint=structuring_element, mode="reflect")
        for image in rotated_images
    ]
    rotated_back = [
        rotate(image, -angle, mode="reflect")
        for image, angle in zip(opened_images, rotation_angles)
    ]

    stacked_images = np.stack(rotated_back, axis=0)
    union_image = np.max(stacked_images, axis=0)
    cropped = union_image[
        newy : newy + input_image.shape[0],
        newx : newx + input_image.shape[1],
    ]
    return cropped


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
    denoising_se = rectangle(1, config.denoising_se_length)
    extraction_se = rectangle(1, config.extraction_se_length)
    rotation_angles = tuple(range(0, 180, config.angle_spacing))

    working = (
        _rmp_opening(input_image, denoising_se, rotation_angles)
        if config.enable_denoising
        else input_image
    )
    return _rmp_top_hat(working, extraction_se, rotation_angles)


def _binary_to_instances(mask: np.ndarray, start_label: int = 1) -> tuple[np.ndarray, int]:
    """Convert a binary mask to instance labels.

    Parameters
    ----------
    mask : numpy.ndarray
        Binary mask where foreground pixels are non-zero.
    start_label : int, optional
        Starting label index for the output. Defaults to 1.

    Returns
    -------
    numpy.ndarray
        Labeled instance mask.
    int
        Next label value after the labeled mask.
    """
    labeled = label(mask > 0)
    if start_label > 1 and labeled.max() > 0:
        labeled = labeled + (start_label - 1)
    next_label = int(labeled.max()) + 1
    return labeled.astype(np.int32, copy=False), next_label


def _watershed_instances(
    image: np.ndarray,
    binary: np.ndarray,
    min_distance: int,
) -> np.ndarray:
    """Split touching spots using watershed segmentation."""
    if not np.any(binary):
        return np.zeros_like(binary, dtype=np.int32)
    if not np.any(~binary):
        labeled, _ = _binary_to_instances(binary)
        return labeled

    distance = ndi.distance_transform_edt(binary)
    coordinates = peak_local_max(
        distance,
        labels=binary.astype(np.uint8),
        min_distance=max(1, int(min_distance)),
        exclude_border=False,
    )
    if coordinates.size == 0:
        labeled, _ = _binary_to_instances(binary)
        return labeled

    peaks = np.zeros(binary.shape, dtype=bool)
    peaks[tuple(coordinates.T)] = True
    markers = label(peaks).astype(np.int32, copy=False)
    if markers.max() == 0:
        labeled, _ = _binary_to_instances(binary)
        return labeled

    labels = watershed(-distance, markers, mask=binary)
    return labels.astype(np.int32, copy=False)


def _ensure_dask_available() -> None:
    """Ensure dask is installed for tiled execution."""
    if da is None:  # pragma: no cover - import guard
        raise ImportError("dask is required for distributed spot detection.")


def _ensure_distributed_available() -> None:
    """Ensure dask.distributed is installed for distributed execution."""
    if Client is None or LocalCluster is None:  # pragma: no cover - import guard
        raise ImportError("dask.distributed is required for distributed execution.")


def _ensure_cupy_available() -> None:
    """Ensure CuPy and cuCIM are installed for GPU execution."""
    if (
        cp is None
        or gpu_threshold_otsu is None
        or gpu_opening is None
        or gpu_rectangle is None
        or gpu_rotate is None
    ):  # pragma: no cover - import guard
        raise ImportError("cupy + cucim are required for GPU execution.")


def _dask_available() -> bool:
    """Return True when dask is available."""
    return da is not None


def _distributed_available() -> bool:
    """Return True when dask.distributed is available."""
    return Client is not None and LocalCluster is not None and da is not None


def _gpu_available() -> bool:
    """Return True when CuPy/cuCIM are available for GPU execution."""
    return (
        cp is not None
        and gpu_threshold_otsu is not None
        and gpu_opening is not None
        and gpu_rectangle is not None
        and gpu_rotate is not None
        and da is not None
    )


def _recommended_overlap(config: "RMPSettings") -> int:
    """Derive a suitable overlap from structuring-element sizes."""
    lengths = [config.extraction_se_length]
    if config.enable_denoising:
        lengths.append(config.denoising_se_length)
    return max(1, max(lengths) * 2)


@contextmanager
def _cluster_client(use_gpu: bool):
    """Yield a connected Dask client backed by a local cluster."""
    _ensure_distributed_available()

    use_cuda_cluster = bool(use_gpu and cp is not None and LocalCUDACluster is not None)
    cluster_cls = LocalCUDACluster if use_cuda_cluster else LocalCluster
    with cluster_cls() as cluster:  # type: ignore[call-arg]
        with Client(cluster) as client:
            yield client


def _cpu_top_hat_block(block: np.ndarray, config: "RMPSettings") -> np.ndarray:
    """Return background-subtracted tile via the RMP top-hat pipeline."""
    denoising_se = rectangle(1, config.denoising_se_length)
    extraction_se = rectangle(1, config.extraction_se_length)
    rotation_angles = tuple(range(0, 180, config.angle_spacing))

    working = (
        _rmp_opening(block, denoising_se, rotation_angles)
        if config.enable_denoising
        else block
    )
    top_hat = working - _rmp_opening(working, extraction_se, rotation_angles)
    return np.asarray(top_hat, dtype=np.float32)


def _gpu_pad_for_rotation(image: "cp.ndarray") -> tuple["cp.ndarray", tuple[int, int]]:
    nrows, ncols = image.shape[:2]
    diagonal = int(cp.ceil(cp.sqrt(nrows**2 + ncols**2)).item())
    rows_to_pad = int(cp.ceil((diagonal - nrows) / 2).item())
    cols_to_pad = int(cp.ceil((diagonal - ncols) / 2).item())
    padded = cp.pad(
        image,
        ((rows_to_pad, rows_to_pad), (cols_to_pad, cols_to_pad)),
        mode="reflect",
    )
    return padded, (rows_to_pad, cols_to_pad)


def _gpu_rmp_opening(
    image: "cp.ndarray",
    structuring_element: "cp.ndarray",
    rotation_angles: Iterable[int],
) -> "cp.ndarray":
    padded, (newy, newx) = _gpu_pad_for_rotation(image)
    rotated = [gpu_rotate(padded, angle, mode="reflect") for angle in rotation_angles]
    opened = [
        gpu_opening(img, footprint=structuring_element, mode="reflect")
        for img in rotated
    ]
    rotated_back = [
        gpu_rotate(img, -angle, mode="reflect")
        for img, angle in zip(opened, rotation_angles)
    ]

    stacked = cp.stack(rotated_back, axis=0)
    union = cp.max(stacked, axis=0)
    return union[newy : newy + image.shape[0], newx : newx + image.shape[1]]


def _gpu_top_hat(block: np.ndarray, config: "RMPSettings") -> np.ndarray:
    """CuPy-backed RMP top-hat for a single tile."""
    _ensure_cupy_available()

    gpu_block = cp.asarray(block, dtype=cp.float32)
    denoising_se = gpu_rectangle(1, config.denoising_se_length)
    extraction_se = gpu_rectangle(1, config.extraction_se_length)
    rotation_angles = tuple(range(0, 180, config.angle_spacing))

    working = (
        _gpu_rmp_opening(gpu_block, denoising_se, rotation_angles)
        if config.enable_denoising
        else gpu_block
    )
    top_hat = working - _gpu_rmp_opening(working, extraction_se, rotation_angles)
    return cp.asnumpy(top_hat).astype(np.float32, copy=False)


def _rmp_top_hat_tiled(
    image: np.ndarray,
    config: "RMPSettings",
    chunk_size: tuple[int, int] = (1024, 1024),
    overlap: int | None = None,
    use_gpu: bool = False,
    distributed: bool = False,
    client: "Client | None" = None,
) -> np.ndarray:
    """Return the RMP top-hat image using tiled execution."""
    _ensure_dask_available()
    if use_gpu:
        _ensure_cupy_available()

    effective_overlap = _recommended_overlap(config) if overlap is None else overlap

    if use_gpu:

        def block_fn(block, block_info=None):
            return _gpu_top_hat(block, config)

    else:

        def block_fn(block, block_info=None):
            return _cpu_top_hat_block(block, config)

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
            with _cluster_client(use_gpu) as temp_client:
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
    use_3d: bool = False

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
        manual_threshold = float(settings.get("manual_threshold", 0.5))
        manual_threshold = max(0.0, min(1.0, manual_threshold))
        config = RMPSettings(
            denoising_se_length=int(settings.get("denoising_kernel_length", 2)),
            extraction_se_length=int(settings.get("extraction_kernel_length", 10)),
            angle_spacing=int(settings.get("angle_spacing", 5)),
            auto_threshold=bool(settings.get("auto_threshold", True)),
            manual_threshold=manual_threshold,
            enable_denoising=bool(settings.get("enable_denoising", True)),
            use_3d=bool(settings.get("use_3d", False)),
        )

        if config.angle_spacing <= 0:
            raise ValueError("Angle spacing must be positive.")
        if config.denoising_se_length <= 0 or config.extraction_se_length <= 0:
            raise ValueError("Structuring element lengths must be positive.")

        data = layer_data_asarray(layer)
        if data.ndim not in (2, 3):
            raise ValueError("RMP expects 2D images or 3D stacks.")

        normalized = _normalize_image(data)
        if normalized.ndim == 3 and not config.use_3d:
            raise ValueError("Enable 3D to process stacks.")

        use_distributed = _distributed_available()
        use_gpu = _gpu_available()
        use_tiled = _dask_available() and (use_distributed or use_gpu)

        if normalized.ndim == 2:
            image_2d = normalized
            if use_tiled:
                top_hat = _rmp_top_hat_tiled(
                    image_2d,
                    config=config,
                    use_gpu=use_gpu,
                    distributed=use_distributed,
                )
            else:
                top_hat = _compute_top_hat(image_2d, config)

            threshold = (
                threshold_otsu(top_hat)
                if config.auto_threshold
                else config.manual_threshold
            )
            binary = img_as_ubyte(top_hat > threshold)
            labels = _watershed_instances(
                top_hat,
                binary > 0,
                min_distance=max(1, config.extraction_se_length // 2),
            )
            return {"mask": labels}

        top_hat_stack = np.zeros_like(normalized, dtype=np.float32)
        if use_tiled and use_distributed:
            with _cluster_client(use_gpu) as client:
                for z in range(normalized.shape[0]):
                    top_hat_stack[z] = _rmp_top_hat_tiled(
                        normalized[z],
                        config=config,
                        use_gpu=use_gpu,
                        distributed=True,
                        client=client,
                    )
        elif use_tiled:
            for z in range(normalized.shape[0]):
                top_hat_stack[z] = _rmp_top_hat_tiled(
                    normalized[z],
                    config=config,
                    use_gpu=use_gpu,
                    distributed=False,
                )
        else:
            for z in range(normalized.shape[0]):
                top_hat_stack[z] = _compute_top_hat(normalized[z], config)

        threshold = (
            threshold_otsu(top_hat_stack)
            if config.auto_threshold
            else config.manual_threshold
        )
        binary_stack = img_as_ubyte(top_hat_stack > threshold)
        labels = _watershed_instances(
            top_hat_stack,
            binary_stack > 0,
            min_distance=max(1, config.extraction_se_length // 2),
        )
        return {"mask": labels}
