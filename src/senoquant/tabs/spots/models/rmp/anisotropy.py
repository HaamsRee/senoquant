"""Anisotropy detection and correction for RMP spot calling."""

from __future__ import annotations

import logging

import numpy as np
from scipy import ndimage as ndi

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
    USE_LAPLACE_FOR_PEAKS,
)
from .markers import _markers_from_local_maxima, _segment_from_markers
from .shape_utils import _zoom_to_shape

logger = logging.getLogger(__name__)


def _candidate_local_maxima_coords(
    data: np.ndarray,
    candidate_mask: np.ndarray,
) -> np.ndarray:
    """Return candidate coordinates that are not lower than any 3x3x3 neighbor.

    Parameters
    ----------
    data
        3D reference image used for anisotropy peak scoring.
    candidate_mask
        Boolean mask limiting local-maxima evaluation to bright, valid foreground
        candidates.

    Returns
    -------
    np.ndarray
        Integer coordinate array with shape ``(N, 3)``.
    """
    coords = np.argwhere(candidate_mask)
    if coords.size == 0:
        return coords

    candidate_values = data[tuple(coords.T)]
    keep = np.ones(coords.shape[0], dtype=bool)
    for dz in (-1, 0, 1):
        z = np.clip(coords[:, 0] + dz, 0, data.shape[0] - 1)
        for dy in (-1, 0, 1):
            y = np.clip(coords[:, 1] + dy, 0, data.shape[1] - 1)
            for dx in (-1, 0, 1):
                if dz == 0 and dy == 0 and dx == 0:
                    continue
                x = np.clip(coords[:, 2] + dx, 0, data.shape[2] - 1)
                keep &= data[z, y, x] <= candidate_values
                if not np.any(keep):
                    return coords[:0]

    return coords[keep]


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

    coords = _candidate_local_maxima_coords(data, peak_candidates)
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
