"""
UDWT (a trous) B3-spline wavelet spot detector.

Implements the Olivo-Marin (2002) workflow: build a trous smoothing scales,
compute wavelet planes, WAT-threshold per scale, multiply planes, and label
connected components. Supports 2D, 3D, and per-slice 2D for 3D stacks.

Algorithm (high level)
----------------------
1) Build smoothing scales A1..AJ with the dilated B3-spline kernel.
2) Form wavelet planes Wi = A_{i-1} - Ai.
3) Apply WAT thresholding per scale (with per-scale sensitivity).
4) Multiply thresholded planes to form the multiscale product PJ.
5) Threshold |PJ| with ld and label connected components.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import numpy as np
from scipy import ndimage as ndi
from skimage.measure import label

from ..base import SenoQuantSpotDetector
from senoquant.utils import layer_data_asarray


BASE_KERNEL = np.array(
    [1.0 / 16.0, 1.0 / 4.0, 3.0 / 8.0, 1.0 / 4.0, 1.0 / 16.0],
    dtype=np.float32,
)
"""numpy.ndarray
Base 1D B3-spline smoothing kernel (separable).

Shape
-----
(5,)
"""

MAX_SCALES = 5
"""int
Maximum number of a trous scales.
"""

EPS = 1e-12
"""float
Small epsilon to avoid zero thresholds.
"""


@dataclass(frozen=True)
class _Params:
    """Internal parameter bundle.

    Parameters
    ----------
    num_scales : int
        Number of a trous scales (J), derived from enabled scales.
    ld : float
        Threshold on the multiscale product magnitude. Higher values reduce
        detections (more conservative).
    force_2d : bool
        For 3D inputs, apply the 2D detector per slice (ignore Z correlations).
    scale_enabled : tuple[bool, ...]
        Per-scale enable flags for scales 1..MAX_SCALES (non-contiguous ok).
    scale_sensitivity : tuple[float, ...]
        Per-scale sensitivity for scales 1..MAX_SCALES (higher is more permissive).
    """

    num_scales: int = 3
    ld: float = 1.0
    force_2d: bool = False
    scale_enabled: tuple[bool, ...] = (True, True, True)
    scale_sensitivity: tuple[float, ...] = (100.0, 100.0, 100.0)


def _min_size(num_scales: int) -> int:
    """Minimum size per dimension for the requested number of scales.

    Parameters
    ----------
    num_scales : int
        Number of a trous scales (J).

    Returns
    -------
    int
        Minimum required size along each dimension.
    """
    # 5 + 4*2^(J-1)
    return 5 + (2 ** (num_scales - 1)) * 4


def _ensure_min_size(shape: tuple[int, ...], num_scales: int) -> None:
    """Raise if any dimension is too small for the requested scales.

    Parameters
    ----------
    shape : tuple[int, ...]
        Image shape (2D or 3D).
    num_scales : int
        Number of a trous scales (J).
    """
    min_size = _min_size(num_scales)
    if any(dim < min_size for dim in shape):
        raise ValueError(
            f"UDWT à trous requires each dimension >= {min_size} "
            f"for {num_scales} scales (got shape={shape})."
        )


@lru_cache(maxsize=None)
def _b3_kernel(step: int) -> np.ndarray:
    """Return the dilated 1D B3-spline kernel for the given step.

    Parameters
    ----------
    step : int
        Step between non-zero taps (2**(j-1) for scale j).

    Returns
    -------
    numpy.ndarray
        1D kernel of length 1 + 4*step (float32).
    """
    if step <= 0:
        raise ValueError("UDWT step must be positive.")
    if step == 1:
        return BASE_KERNEL
    kernel = np.zeros(1 + 4 * step, dtype=np.float32)
    kernel[::step] = BASE_KERNEL
    return kernel


def _atrous_smoothing_scales(image: np.ndarray, J: int) -> list[np.ndarray]:
    """Compute a trous smoothing scales A1..AJ for a 2D/3D array.

    Parameters
    ----------
    image : numpy.ndarray
        Input 2D or 3D array.
    J : int
        Number of scales to compute.

    Returns
    -------
    list[numpy.ndarray]
        Smoothed arrays A1..AJ (float32), same shape as image.
    """
    scales: list[np.ndarray] = []
    current = image.astype(np.float32, copy=False)

    for j in range(1, J + 1):
        step = 2 ** (j - 1)
        kernel = _b3_kernel(step)

        filtered = current
        for axis in range(current.ndim):
            filtered = ndi.convolve1d(filtered, kernel, axis=axis, mode="mirror")

        scales.append(filtered.astype(np.float32, copy=False))
        current = filtered

    return scales


def _wavelet_planes(A0: np.ndarray, scales: list[np.ndarray]) -> list[np.ndarray]:
    """Compute detail planes Wi = A_{i-1} - Ai.

    Parameters
    ----------
    A0 : numpy.ndarray
        Original image.
    scales : list[numpy.ndarray]
        Smoothing scales A1..AJ.

    Returns
    -------
    list[numpy.ndarray]
        Detail planes W1..WJ (float32), same shape as A0.
    """
    W: list[np.ndarray] = []
    prev = A0.astype(np.float32, copy=False)
    for Ai in scales:
        W.append((prev - Ai).astype(np.float32, copy=False))
        prev = Ai
    return W


def _lambda_coeffs(num_scales: int, width: int, height: int) -> np.ndarray:
    """Compute WAT scale-dependent lambda coefficients."""
    lambdac = np.empty(num_scales + 2, dtype=np.float32)
    for i in range(num_scales + 2):
        denom = 1 << (2 * i)
        val = (width * height) / denom
        lambdac[i] = np.sqrt(2 * np.log(val)) if val > 0 else 0.0
    return lambdac


def _mean_abs_dev(data: np.ndarray, axis=None, keepdims: bool = False) -> np.ndarray:
    """Mean absolute deviation from the mean."""
    mean = data.mean(axis=axis, keepdims=True)
    return np.mean(np.abs(data - mean), axis=axis, keepdims=keepdims)


def _wat_threshold_inplace(
    Wi: np.ndarray, scale_index: int, lambdac: np.ndarray, sensitivity: float
) -> None:
    """Apply WAT thresholding in-place for a single scale."""
    dcoeff = max(sensitivity / 100.0, EPS)
    if Wi.ndim == 2:
        mad = _mean_abs_dev(Wi, axis=None, keepdims=False)
        coeff_thr = (lambdac[scale_index + 1] * mad) / dcoeff
        if coeff_thr <= EPS:
            return
        Wi[Wi < coeff_thr] = 0.0
        return

    mad = _mean_abs_dev(Wi, axis=(1, 2), keepdims=True)
    coeff_thr = (lambdac[scale_index + 1] * mad) / dcoeff
    Wi[Wi < coeff_thr] = 0.0


def _multiscale_product(W_planes: list[np.ndarray]) -> np.ndarray:
    """Multiply thresholded planes to form the multiscale product image.

    Parameters
    ----------
    W_planes : list[numpy.ndarray]
        Thresholded wavelet planes, all the same shape.

    Returns
    -------
    numpy.ndarray
        Multiscale product image (float32).
    """
    if not W_planes:
        raise ValueError("W_planes must be a non-empty list.")
    P = np.ones_like(W_planes[0], dtype=np.float32)
    for Wi in W_planes:
        P *= Wi.astype(np.float32, copy=False)
    return P


def _detect_from_product(P: np.ndarray, ld: float) -> np.ndarray:
    """Binary mask where |P| > ld.

    Parameters
    ----------
    P : numpy.ndarray
        Multiscale product image.
    ld : float
        Detection threshold on |P|.

    Returns
    -------
    numpy.ndarray
        Boolean mask of detections.
    """
    return np.abs(P) > ld


def _detect_2d(image: np.ndarray, params: _Params) -> np.ndarray:
    """Detect spots in a 2D image and return labeled instances.

    Parameters
    ----------
    image : numpy.ndarray
        Input 2D image (Y, X).
    params : _Params
        Detector parameters.

    Returns
    -------
    numpy.ndarray
        Labeled instance mask (int32), background 0.
    """
    if params.scale_enabled:
        num_scales = max(
            (i + 1 for i, enabled in enumerate(params.scale_enabled) if enabled),
            default=1,
        )
    else:
        num_scales = max(1, params.num_scales)

    _ensure_min_size(image.shape, num_scales)

    scales = _atrous_smoothing_scales(image, num_scales)
    W = _wavelet_planes(image, scales)
    lambdac = _lambda_coeffs(num_scales, image.shape[1], image.shape[0])

    enabled_indices = [
        i for i, enabled in enumerate(params.scale_enabled) if enabled and i < len(W)
    ]
    if not enabled_indices:
        return np.zeros(image.shape, dtype=np.int32)

    enabled_planes: list[np.ndarray] = []
    for i in enabled_indices:
        sensitivity = (
            params.scale_sensitivity[i]
            if i < len(params.scale_sensitivity)
            else 100.0
        )
        _wat_threshold_inplace(W[i], i, lambdac, sensitivity)
        enabled_planes.append(W[i])

    P = _multiscale_product(enabled_planes)
    binary = _detect_from_product(P, params.ld)
    return label(binary, connectivity=2).astype(np.int32, copy=False)


def _detect_2d_stack(stack: np.ndarray, params: _Params) -> np.ndarray:
    """Apply the 2D detector per Z-slice and keep labels unique.

    Parameters
    ----------
    stack : numpy.ndarray
        Input 3D stack (Z, Y, X).
    params : _Params
        Detector parameters.

    Returns
    -------
    numpy.ndarray
        Labeled mask for each slice (int32).
    """
    labels = np.zeros(stack.shape, dtype=np.int32)
    next_label = 1

    for z in range(stack.shape[0]):
        slice_labels = _detect_2d(stack[z], params)
        m = int(slice_labels.max())
        if m > 0:
            slice_labels = slice_labels + (next_label - 1)
            next_label += m
        labels[z] = slice_labels

    return labels


def _detect_3d(volume: np.ndarray, params: _Params) -> np.ndarray:
    """Detect spots in a 3D volume using the direct 3D extension.

    Parameters
    ----------
    volume : numpy.ndarray
        Input 3D volume (Z, Y, X).
    params : _Params
        Detector parameters.

    Returns
    -------
    numpy.ndarray
        Labeled instance mask (int32).
    """
    if params.scale_enabled:
        num_scales = max(
            (i + 1 for i, enabled in enumerate(params.scale_enabled) if enabled),
            default=1,
        )
    else:
        num_scales = max(1, params.num_scales)

    _ensure_min_size(volume.shape, num_scales)

    scales = _atrous_smoothing_scales(volume, num_scales)
    W = _wavelet_planes(volume, scales)
    lambdac = _lambda_coeffs(num_scales, volume.shape[2], volume.shape[1])

    enabled_indices = [
        i for i, enabled in enumerate(params.scale_enabled) if enabled and i < len(W)
    ]
    if not enabled_indices:
        return np.zeros(volume.shape, dtype=np.int32)

    enabled_planes: list[np.ndarray] = []
    for i in enabled_indices:
        sensitivity = (
            params.scale_sensitivity[i]
            if i < len(params.scale_sensitivity)
            else 100.0
        )
        _wat_threshold_inplace(W[i], i, lambdac, sensitivity)
        enabled_planes.append(W[i])

    P = _multiscale_product(enabled_planes)
    binary = _detect_from_product(P, params.ld)
    return label(binary, connectivity=3).astype(np.int32, copy=False)


class UDWTDetector(SenoQuantSpotDetector):
    """Undecimated B3-spline wavelet spot detector.

    Settings: ld, force_2d, scale_*_enabled, scale_*_sensitivity.

    Higher ld yields fewer detections (stricter thresholds).
    Higher sensitivity yields more detections on that scale.
    """

    def __init__(self, models_root=None) -> None:
        """Initialize the detector.

        Parameters
        ----------
        models_root : pathlib.Path or None, optional
            Root folder for detector resources (unused).
        """
        super().__init__("udwt", models_root=models_root)

    def run(self, **kwargs) -> dict:
        """Run the detector on a napari Image layer.

        Parameters
        ----------
        **kwargs
            layer : napari.layers.Image or None
                Image layer (single-channel).
            settings : dict, optional
                Keys:
                - ld (float): higher is stricter final detection threshold
                - force_2d (bool): for 3D, detect per slice (ignores Z context)
                - scale_N_enabled (bool): include scale N in the product
                - scale_N_sensitivity (float): higher is more permissive

        Returns
        -------
        dict
            Output with keys "mask" (labeled int32 or None) and "points" (None).
        """
        layer = kwargs.get("layer")
        if layer is None:
            return {"mask": None, "points": None}

        if getattr(layer, "rgb", False):
            raise ValueError("UDWT requires single-channel images (rgb=False).")

        settings = kwargs.get("settings", {}) or {}

        ld = float(settings.get("ld", 1.0))
        force_2d = bool(settings.get("force_2d", False))

        default_enabled = (True, True, True, False, False)
        enabled_all: list[bool] = []
        sensitivity_all: list[float] = []
        for i in range(MAX_SCALES):
            enabled_key = f"scale_{i + 1}_enabled"
            sens_key = f"scale_{i + 1}_sensitivity"
            enabled_val = bool(settings.get(enabled_key, default_enabled[i]))
            sens_val = float(settings.get(sens_key, 100.0))
            sens_val = max(1.0, min(100.0, sens_val))
            enabled_all.append(enabled_val)
            sensitivity_all.append(sens_val)

        if any(enabled_all):
            num_scales = max(i + 1 for i, enabled in enumerate(enabled_all) if enabled)
        else:
            num_scales = 1

        params = _Params(
            num_scales=num_scales,
            ld=ld,
            force_2d=force_2d,
            scale_enabled=tuple(enabled_all),
            scale_sensitivity=tuple(sensitivity_all),
        )

        data = layer_data_asarray(layer)
        if data.ndim not in (2, 3):
            raise ValueError("UDWT expects 2D images or 3D stacks.")

        image = np.asarray(data, dtype=np.float32)

        if image.ndim == 2:
            return {"mask": _detect_2d(image, params), "points": None}

        # 3D input
        if params.force_2d:
            return {"mask": _detect_2d_stack(image, params), "points": None}

        return {"mask": _detect_3d(image, params), "points": None}
