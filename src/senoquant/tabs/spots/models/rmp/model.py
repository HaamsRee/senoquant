"""RMP spot detector implementation."""

from __future__ import annotations

from contextlib import contextmanager
from functools import partial
import logging
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
from senoquant.tabs.spots.models.denoise import wavelet_denoise_input
from senoquant.utils import layer_data_asarray

from .config import (
    ANISO_DETECT_PERCENTILE,
    ANISO_MAX_SPOTS,
    ANISO_MIN_SPOTS,
    ANISO_PATCH_RADIUS_XY,
    ANISO_PATCH_RADIUS_Z,
    ANISO_RATIO_HIGH,
    ANISO_RATIO_IQR_MAX,
    ANISO_RATIO_LOW,
    ANISO_Z_SCALE_MAX,
    ANISO_Z_SCALE_MIN,
    EPS,
    MIN_SCALE_SIGMA,
    NOISE_FLOOR_SIGMA,
    PEAK_COMPONENT_DISTANCE_WEIGHT,
    PEAK_MIN_COMPONENT_DISTANCE_RATIO,
    PEAK_RELATIVE_INTENSITY_MIN,
    PEAK_RELATIVE_PROMINENCE_MIN,
    RMPSettings,
    RMP_TILE_CHUNK_SIZE,
    SIGNAL_SCALE_QUANTILE,
    USE_LAPLACE_FOR_PEAKS,
    WAVELET_SIGMA,
    Array2D,
    KernelShape,
)
from .normalization import (
    _clamp_threshold,
    _normalize_image,
    _normalize_top_hat_unit,
)

try:
    import dask.array as da
except ImportError:  # pragma: no cover - optional dependency
    da = None  # type: ignore[assignment]

try:  # pragma: no cover - optional dependency
    from dask.distributed import Client, LocalCluster
except ImportError:  # pragma: no cover - optional dependency
    Client = None  # type: ignore[assignment]
    LocalCluster = None  # type: ignore[assignment]


logger = logging.getLogger(__name__)


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
    grid = F.affine_grid(theta, tuple(image.shape), align_corners=False)
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


def _markers_from_local_maxima(
    enhanced: np.ndarray,
    threshold: float,
    *,
    reference_image: np.ndarray | None = None,
    use_laplace: bool = USE_LAPLACE_FOR_PEAKS,
) -> np.ndarray:
    """Build marker labels from reference-image local maxima inside enhanced mask."""
    connectivity = max(1, min(2, enhanced.ndim))
    enhanced_float = np.asarray(enhanced, dtype=np.float32)
    reference_float = (
        np.asarray(reference_image, dtype=np.float32)
        if reference_image is not None
        else enhanced_float
    )
    if reference_float.shape != enhanced_float.shape:
        raise ValueError("Reference image shape must match enhanced image shape.")
    response = (
        laplace(reference_float)
        if use_laplace
        else reference_float
    )
    foreground = enhanced_float > threshold
    if not np.any(foreground):
        return np.zeros(enhanced_float.shape, dtype=np.int32)

    structure = ndi.generate_binary_structure(enhanced_float.ndim, 1)
    component_labels, num_components = ndi.label(foreground, structure=structure)
    if num_components == 0:
        return np.zeros(enhanced_float.shape, dtype=np.int32)

    distance_to_boundary = ndi.distance_transform_edt(foreground)
    label_ids = np.arange(num_components + 1, dtype=np.int32)
    max_distance_by_label = np.asarray(
        ndi.maximum(
            distance_to_boundary,
            labels=component_labels,
            index=label_ids,
        ),
        dtype=np.float32,
    )

    component_scale = max_distance_by_label[component_labels]

    normalized_component_distance = np.zeros_like(response, dtype=np.float32)
    valid_component_mask = foreground & np.isfinite(reference_float)
    normalized_component_distance[valid_component_mask] = (
        distance_to_boundary[valid_component_mask]
        / np.maximum(component_scale[valid_component_mask], EPS)
    )

    weighted_response = response * (
        1.0 + (PEAK_COMPONENT_DISTANCE_WEIGHT * normalized_component_distance)
    )
    mask = local_maxima(weighted_response, connectivity=connectivity)
    mask = mask & foreground
    mask = mask & (
        normalized_component_distance >= PEAK_MIN_COMPONENT_DISTANCE_RATIO
    )
    if not np.any(mask):
        return np.zeros(enhanced_float.shape, dtype=np.int32)

    valid = reference_float[valid_component_mask]
    if valid.size == 0:
        return np.zeros(enhanced_float.shape, dtype=np.int32)

    intensity_scale = float(np.nanpercentile(valid, 99.5))
    if (not np.isfinite(intensity_scale)) or intensity_scale <= EPS:
        intensity_scale = float(np.nanmax(valid))
        if (not np.isfinite(intensity_scale)) or intensity_scale <= EPS:
            return np.zeros(enhanced_float.shape, dtype=np.int32)

    relative_intensity = np.zeros_like(reference_float, dtype=np.float32)
    relative_intensity[valid_component_mask] = (
        reference_float[valid_component_mask] / max(intensity_scale, EPS)
    )

    prominence_floor = ndi.minimum_filter(reference_float, size=3, mode="nearest")
    relative_prominence = (reference_float - prominence_floor) / np.maximum(
        reference_float,
        EPS,
    )
    relative_prominence = np.clip(relative_prominence, 0.0, None)

    mask = mask & valid_component_mask
    mask = mask & (relative_intensity >= PEAK_RELATIVE_INTENSITY_MIN)
    mask = mask & (relative_prominence >= PEAK_RELATIVE_PROMINENCE_MIN)
    if not np.any(mask):
        return np.zeros(enhanced_float.shape, dtype=np.int32)

    markers = np.zeros(enhanced_float.shape, dtype=np.int32)
    coords = np.argwhere(mask)
    if coords.size == 0:
        return markers

    max_indices = np.asarray(enhanced_float.shape) - 1
    coords = np.clip(coords, 0, max_indices)
    markers[tuple(coords.T)] = 1

    marker_labels, _num = ndi.label(markers > 0, structure=structure)
    return marker_labels.astype(np.int32, copy=False)


def _fit_to_shape(array: np.ndarray, target_shape: tuple[int, ...]) -> np.ndarray:
    """Crop/pad array to exactly match target shape."""
    if array.shape == target_shape:
        return array
    src_slices = tuple(slice(0, min(src, tgt)) for src, tgt in zip(array.shape, target_shape))
    cropped = array[src_slices]
    if cropped.shape == target_shape:
        return cropped
    fitted = np.zeros(target_shape, dtype=array.dtype)
    dst_slices = tuple(slice(0, dim) for dim in cropped.shape)
    fitted[dst_slices] = cropped
    return fitted


def _zoom_to_shape(
    array: np.ndarray,
    target_shape: tuple[int, ...],
    *,
    order: int,
) -> np.ndarray:
    """Zoom an ndarray and force exact target shape via crop/pad."""
    if array.shape == target_shape:
        return array
    zoom_factors = tuple(
        (float(t) / float(s)) if s > 0 else 1.0
        for t, s in zip(target_shape, array.shape)
    )
    out = ndi.zoom(
        array,
        zoom=zoom_factors,
        order=order,
        mode="nearest",
        prefilter=order > 1,
    )
    return _fit_to_shape(out, target_shape)


def _estimate_apparent_z_anisotropy_ratio(
    reference_image: np.ndarray,
    valid_mask: np.ndarray | None = None,
) -> float | None:
    """Estimate apparent z-vs-xy spot width ratio from bright local peaks."""
    data = np.asarray(reference_image, dtype=np.float32)
    if data.ndim != 3:
        return None
    if min(data.shape[1:]) < 2 * ANISO_PATCH_RADIUS_XY + 1:
        return None
    if data.shape[0] < 2 * ANISO_PATCH_RADIUS_Z + 1:
        return None

    finite = np.isfinite(data)
    if valid_mask is None:
        sampling_mask = finite
    else:
        sampling_mask = finite & np.asarray(valid_mask, dtype=bool)
        if sampling_mask.shape != data.shape:
            raise ValueError("Anisotropy valid mask shape must match reference image shape.")
    if not np.any(sampling_mask):
        return None

    valid = data[sampling_mask]
    threshold = float(np.nanpercentile(valid, ANISO_DETECT_PERCENTILE))
    peak_candidates = sampling_mask & (data >= threshold)
    if not np.any(peak_candidates):
        return None

    local_max = data >= ndi.maximum_filter(data, size=(3, 3, 3), mode="nearest")
    maxima_mask = peak_candidates & local_max
    coords = np.argwhere(maxima_mask)
    if coords.size == 0:
        return None

    strengths = data[tuple(coords.T)]
    order = np.argsort(strengths)[::-1]
    coords = coords[order[:ANISO_MAX_SPOTS]]

    rz = ANISO_PATCH_RADIUS_Z
    ry = ANISO_PATCH_RADIUS_XY
    rx = ANISO_PATCH_RADIUS_XY
    zz, yy, xx = np.indices((2 * rz + 1, 2 * ry + 1, 2 * rx + 1), dtype=np.float32)
    zz -= rz
    yy -= ry
    xx -= rx

    ratios: list[float] = []
    for z, y, x in coords:
        if (
            z < rz
            or y < ry
            or x < rx
            or z >= data.shape[0] - rz
            or y >= data.shape[1] - ry
            or x >= data.shape[2] - rx
        ):
            continue

        patch = data[
            z - rz : z + rz + 1,
            y - ry : y + ry + 1,
            x - rx : x + rx + 1,
        ]
        patch_sampling_mask = sampling_mask[
            z - rz : z + rz + 1,
            y - ry : y + ry + 1,
            x - rx : x + rx + 1,
        ]
        if patch.shape != patch_sampling_mask.shape:
            continue
        patch_valid = np.isfinite(patch) & patch_sampling_mask
        if not np.any(patch_valid):
            continue

        weights = patch - float(np.median(patch[patch_valid]))
        weights = np.clip(weights, 0.0, None)
        weights = np.where(patch_valid, weights, 0.0)
        total = float(weights.sum())
        if total <= EPS:
            continue

        mz = float((weights * zz).sum() / total)
        my = float((weights * yy).sum() / total)
        mx = float((weights * xx).sum() / total)
        vz = float((weights * (zz - mz) ** 2).sum() / total)
        vy = float((weights * (yy - my) ** 2).sum() / total)
        vx = float((weights * (xx - mx) ** 2).sum() / total)

        sigma_z = float(np.sqrt(max(vz, EPS)))
        sigma_xy = float(np.sqrt(max(0.5 * (vy + vx), EPS)))
        if sigma_xy <= EPS:
            continue

        ratio = sigma_z / sigma_xy
        if np.isfinite(ratio) and 0.25 <= ratio <= 8.0:
            ratios.append(float(ratio))

    if len(ratios) < ANISO_MIN_SPOTS:
        return None

    ratios_arr = np.asarray(ratios, dtype=np.float32)
    q25, q75 = np.percentile(ratios_arr, [25, 75])
    iqr = float(q75 - q25)
    if iqr > ANISO_RATIO_IQR_MAX:
        return None
    return float(np.median(ratios_arr))


def _spot_call_with_anisotropy_correction(
    top_hat_normalized: np.ndarray,
    threshold: float,
    *,
    reference_image: np.ndarray | None = None,
) -> np.ndarray:
    """Optionally isotropize in z before spot calling, then restore original shape."""
    reference = (
        np.asarray(reference_image, dtype=np.float32)
        if reference_image is not None
        else np.asarray(top_hat_normalized, dtype=np.float32)
    )
    if reference.shape != top_hat_normalized.shape:
        raise ValueError("Reference image shape must match enhanced image shape.")

    if top_hat_normalized.ndim != 3:
        logger.warning(
            "RMP anisotropy: not applied (non-3D input, ndim=%d).",
            int(top_hat_normalized.ndim),
        )
        markers = _markers_from_local_maxima(
            top_hat_normalized,
            threshold,
            reference_image=reference,
            use_laplace=USE_LAPLACE_FOR_PEAKS,
        )
        return _segment_from_markers(top_hat_normalized, markers, threshold)

    foreground = np.asarray(top_hat_normalized, dtype=np.float32) > threshold
    ratio = _estimate_apparent_z_anisotropy_ratio(reference, valid_mask=foreground)
    if ratio is None:
        logger.warning("RMP anisotropy: ratio unavailable; correction not applied.")
        markers = _markers_from_local_maxima(
            top_hat_normalized,
            threshold,
            reference_image=reference,
            use_laplace=USE_LAPLACE_FOR_PEAKS,
        )
        return _segment_from_markers(top_hat_normalized, markers, threshold)

    logger.warning(
        "RMP anisotropy: estimated ratio sigma_z/sigma_xy=%.3f.",
        float(ratio),
    )
    if not (ratio > ANISO_RATIO_HIGH or ratio < ANISO_RATIO_LOW):
        logger.warning(
            "RMP anisotropy: not applied (ratio %.3f within [%.3f, %.3f]).",
            float(ratio),
            float(ANISO_RATIO_LOW),
            float(ANISO_RATIO_HIGH),
        )
        markers = _markers_from_local_maxima(
            top_hat_normalized,
            threshold,
            reference_image=reference,
            use_laplace=USE_LAPLACE_FOR_PEAKS,
        )
        return _segment_from_markers(top_hat_normalized, markers, threshold)

    z_scale = float(np.clip(1.0 / ratio, ANISO_Z_SCALE_MIN, ANISO_Z_SCALE_MAX))
    if abs(z_scale - 1.0) < 1e-3:
        logger.warning(
            "RMP anisotropy: not applied (computed z_scale=%.3f ~ 1.0 after clamping).",
            z_scale,
        )
        markers = _markers_from_local_maxima(
            top_hat_normalized,
            threshold,
            reference_image=reference,
            use_laplace=USE_LAPLACE_FOR_PEAKS,
        )
        return _segment_from_markers(top_hat_normalized, markers, threshold)

    logger.warning(
        "RMP anisotropy: applied (ratio=%.3f, z_scale=%.3f, shape=%s -> z-resampled).",
        float(ratio),
        z_scale,
        tuple(int(v) for v in top_hat_normalized.shape),
    )
    iso_image = ndi.zoom(
        np.asarray(top_hat_normalized, dtype=np.float32),
        zoom=(z_scale, 1.0, 1.0),
        order=1,
        mode="nearest",
        prefilter=False,
    )
    iso_reference = ndi.zoom(
        reference,
        zoom=(z_scale, 1.0, 1.0),
        order=1,
        mode="nearest",
        prefilter=False,
    )
    markers_iso = _markers_from_local_maxima(
        iso_image,
        threshold,
        reference_image=iso_reference,
        use_laplace=USE_LAPLACE_FOR_PEAKS,
    )
    labels_iso = _segment_from_markers(iso_image, markers_iso, threshold)
    labels = _zoom_to_shape(
        labels_iso.astype(np.int32, copy=False),
        top_hat_normalized.shape,
        order=0,
    )
    return labels.astype(np.int32, copy=False)


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
    extraction_se: KernelShape = (1, config.extraction_se_length)
    rotation_angles = tuple(range(0, 180, config.angle_spacing))
    return _rmp_top_hat(input_image, extraction_se, rotation_angles)


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
    """Derive a suitable overlap from extraction structuring-element size."""
    return max(1, config.extraction_se_length * 2)


def _pad_xy_to_chunk_multiple(
    image: np.ndarray,
    *,
    chunk_size: tuple[int, int],
) -> tuple[np.ndarray, tuple[slice, ...]]:
    """Pad trailing Y/X axes so tiled execution avoids tiny edge chunks."""
    data = np.asarray(image, dtype=np.float32)
    if data.ndim not in (2, 3):
        raise ValueError("Expected a 2D image or 3D stack for tiled padding.")

    chunk_y = max(1, int(chunk_size[0]))
    chunk_x = max(1, int(chunk_size[1]))
    pad_y = (-int(data.shape[-2])) % chunk_y
    pad_x = (-int(data.shape[-1])) % chunk_x
    crop_slices = tuple(slice(0, int(size)) for size in data.shape)
    if pad_y == 0 and pad_x == 0:
        return data, crop_slices

    pad_width = [(0, 0)] * data.ndim
    pad_width[-2] = (0, pad_y)
    pad_width[-1] = (0, pad_x)
    padded = np.pad(data, pad_width=tuple(pad_width), mode="reflect")
    return padded.astype(np.float32, copy=False), crop_slices


@contextmanager
def _cluster_client():
    """Yield a connected Dask client backed by a local cluster."""
    _ensure_distributed_available()
    with LocalCluster() as cluster:
        with Client(cluster) as client:
            yield client


def _rmp_top_hat_block(block: np.ndarray, config: "RMPSettings") -> np.ndarray:
    """Return background-subtracted tile via the RMP top-hat pipeline."""
    extraction_se: KernelShape = (1, config.extraction_se_length)
    rotation_angles = tuple(range(0, 180, config.angle_spacing))
    top_hat = block - _rmp_opening(block, extraction_se, rotation_angles)
    return np.asarray(top_hat, dtype=np.float32)


def _rmp_top_hat_block_mapped(
    block: np.ndarray,
    *,
    config: "RMPSettings",
    block_info=None,
) -> np.ndarray:
    """Top-level map_overlap callable for picklable tiled execution."""
    del block_info
    return _rmp_top_hat_block(block, config)


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
    *,
    reference_image: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Apply normalization, thresholding, marker extraction, and watershed."""
    top_hat_normalized = _normalize_top_hat_unit(top_hat)
    reference = (
        np.asarray(reference_image, dtype=np.float32)
        if reference_image is not None
        else top_hat_normalized
    )
    if reference.shape != top_hat_normalized.shape:
        raise ValueError("Reference image shape must match top-hat shape.")
    threshold = (
        _clamp_threshold(float(threshold_otsu(top_hat_normalized)))
        if config.auto_threshold
        else config.manual_threshold
    )
    labels = _spot_call_with_anisotropy_correction(
        top_hat_normalized,
        threshold,
        reference_image=reference,
    )
    return labels, top_hat_normalized


def _rmp_top_hat_tiled(
    image: np.ndarray,
    config: "RMPSettings",
    chunk_size: tuple[int, int] = RMP_TILE_CHUNK_SIZE,
    overlap: int | None = None,
    distributed: bool = False,
    client: "Client | None" = None,
) -> np.ndarray:
    """Return the RMP top-hat image using tiled execution."""
    _ensure_dask_available()

    effective_overlap = _recommended_overlap(config) if overlap is None else overlap
    block_fn = partial(_rmp_top_hat_block_mapped, config=config)

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

    return result.compute(scheduler="single-threaded")


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
            extraction_se_length=int(settings.get("extraction_kernel_length", 10)),
            angle_spacing=5,
            auto_threshold=bool(settings.get("auto_threshold", True)),
            manual_threshold=manual_threshold,
            enable_denoising=True,
        )

        if config.angle_spacing <= 0:
            raise ValueError("Angle spacing must be positive.")
        if config.extraction_se_length <= 0:
            raise ValueError("Structuring element lengths must be positive.")

        data = layer_data_asarray(layer)
        if data.ndim not in (2, 3):
            raise ValueError("RMP expects 2D images or 3D stacks.")

        normalized = _normalize_image(data)
        denoised = wavelet_denoise_input(
            normalized,
            enabled=config.enable_denoising,
            sigma=WAVELET_SIGMA,
        )

        use_distributed = _distributed_available()
        use_tiled = _dask_available()
        top_hat_input = denoised
        top_hat_crop_slices: tuple[slice, ...] | None = None
        if use_tiled:
            top_hat_input, top_hat_crop_slices = _pad_xy_to_chunk_multiple(
                denoised,
                chunk_size=RMP_TILE_CHUNK_SIZE,
            )
        try:
            top_hat = _compute_top_hat_nd(
                top_hat_input,
                config,
                use_tiled=use_tiled,
                use_distributed=use_distributed,
            )
        except Exception:
            if not use_distributed:
                raise
            logger.warning(
                "RMP distributed tiled execution failed; retrying with single-threaded local execution.",
                exc_info=False,
            )
            top_hat = _compute_top_hat_nd(
                top_hat_input,
                config,
                use_tiled=use_tiled,
                use_distributed=False,
            )
        if top_hat_crop_slices is not None:
            top_hat = np.asarray(top_hat[top_hat_crop_slices], dtype=np.float32)
        denoised_top_hat = wavelet_denoise_input(
            top_hat,
            enabled=config.enable_denoising,
            sigma=WAVELET_SIGMA,
        )
        labels, _top_hat_normalized = _postprocess_top_hat(
            denoised_top_hat,
            config,
            reference_image=denoised,
        )
        return {
            "mask": labels,
            # "debug_images": {
            #     "debug_top_hat_before_threshold": _top_hat_normalized.astype(
            #         np.float32,
            #         copy=False,
            #     ),
            # },
        }
