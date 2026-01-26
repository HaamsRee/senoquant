"""UDWT B3-spline wavelet spot detector.

This module implements an undecimated (a trous) B3-spline wavelet spot detector
for 2D images and 3D volumes.

The core steps are:
1) Build B3-spline smoothing scales using the a trous algorithm.
2) Compute wavelet coefficients as differences between successive scales.
3) Apply a WAT-style threshold per scale (lambda * MAD / sensitivity).
4) Reconstruct a spot-enhanced image from enabled scales.
5) Label connected components as detected spots.

Notes
-----
- "combine_scales" corresponds to the union of enabled scales; if False, the
  reconstruction uses an intersection rule (values must be non-zero across
  enabled scales).
- Sensitivity values are expected in percent (0-100), matching the original UI.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import math

import numpy as np
from scipy import ndimage as ndi
from skimage.measure import label

from ..base import SenoQuantSpotDetector
from senoquant.utils import layer_data_asarray


BASE_KERNEL = np.array(
    [1.0 / 16.0, 1.0 / 4.0, 3.0 / 8.0, 1.0 / 4.0, 1.0 / 16.0],
    dtype=np.float32,
)
MAX_SCALES = 5
EPS = 1e-6


@dataclass(frozen=True)
class _ScaleConfig:
    """Container for scale configuration.

    Attributes
    ----------
    enabled : bool
        Whether the scale participates in reconstruction.
    sensitivity : float
        Scale sensitivity in percent (0-100). Higher values preserve more
        coefficients by lowering the WAT threshold.
    """

    enabled: bool
    sensitivity: float


def _min_size(num_scales: int) -> int:
    """Return the minimum image size required for a given number of scales.

    Parameters
    ----------
    num_scales : int
        Number of wavelet scales.

    Returns
    -------
    int
        Minimum size required along each dimension.
    """

    return 5 + (2 ** (num_scales - 1)) * 4


def _ensure_min_size(shape: tuple[int, ...], num_scales: int) -> None:
    """Validate that all dimensions satisfy the minimum size requirement.

    Parameters
    ----------
    shape : tuple[int, ...]
        Image shape (2D or 3D).
    num_scales : int
        Number of wavelet scales.

    Raises
    ------
    ValueError
        If any dimension is too small for the requested scales.
    """

    min_size = _min_size(num_scales)
    if any(dim < min_size for dim in shape):
        raise ValueError(
            f"UDWT needs each dimension >= {min_size} for {num_scales} scales."
        )


def _lambda_threshold(num_pixels: int, scale_index: int) -> float:
    """Compute the scale-dependent lambda threshold term.

    Parameters
    ----------
    num_pixels : int
        Number of pixels in a 2D slice (Y * X).
    scale_index : int
        Zero-based scale index.

    Returns
    -------
    float
        Lambda term used by the WAT threshold.
    """

    ratio = num_pixels / float(1 << (2 * (scale_index + 1)))
    if ratio <= 1.0:
        return 0.0
    return math.sqrt(2.0 * math.log(ratio))


@lru_cache(maxsize=None)
def _b3_kernel(step: int) -> np.ndarray:
    """Return the a trous B3-spline kernel for a given step size.

    Parameters
    ----------
    step : int
        Step between non-zero kernel taps (2**(scale-1)).

    Returns
    -------
    numpy.ndarray
        1D convolution kernel.

    Raises
    ------
    ValueError
        If ``step`` is not positive.
    """

    if step <= 0:
        raise ValueError("UDWT step must be positive.")
    if step == 1:
        return BASE_KERNEL
    kernel = np.zeros(1 + 4 * step, dtype=np.float32)
    # Insert zeros between taps for the a trous scaling.
    kernel[::step] = BASE_KERNEL
    return kernel


def _b3_spline_scales(image: np.ndarray, num_scales: int) -> list[np.ndarray]:
    """Compute B3-spline smoothing scales using the a trous algorithm.

    Parameters
    ----------
    image : numpy.ndarray
        Input image (2D or 3D) as float32.
    num_scales : int
        Number of scales to compute.

    Returns
    -------
    list[numpy.ndarray]
        Smoothed images for each scale, ordered from finest to coarsest.
    """

    scales = []
    current = image.astype(np.float32, copy=False)
    for scale in range(1, num_scales + 1):
        step = 2 ** (scale - 1)
        kernel = _b3_kernel(step)
        filtered = current
        # Convolve along each axis with mirror padding to match UDWT behavior.
        for axis in range(current.ndim):
            filtered = ndi.convolve1d(filtered, kernel, axis=axis, mode="mirror")
        scales.append(filtered)
        current = filtered
    return scales


def _b3_wavelet_coefficients(
    original: np.ndarray, scales: list[np.ndarray]
) -> list[np.ndarray]:
    """Compute wavelet coefficients from smoothing scales.

    Parameters
    ----------
    original : numpy.ndarray
        Original image (2D or 3D).
    scales : list[numpy.ndarray]
        Smoothing scales from :func:`_b3_spline_scales`.

    Returns
    -------
    list[numpy.ndarray]
        Wavelet coefficients for each scale plus the residual scale.
    """

    coeffs = []
    prev = original
    for scale in scales:
        coeffs.append(prev - scale)
        prev = scale
    coeffs.append(scales[-1])
    return coeffs


def _apply_wat_threshold(
    coeff: np.ndarray,
    scale_index: int,
    sensitivity: float,
    num_pixels: int,
) -> None:
    """Apply WAT thresholding to wavelet coefficients in-place.

    Parameters
    ----------
    coeff : numpy.ndarray
        Wavelet coefficient array (2D or 3D).
    scale_index : int
        Zero-based scale index for lambda selection.
    sensitivity : float
        Sensitivity in percent (0-100). Higher values retain more coefficients.
    num_pixels : int
        Number of pixels per 2D slice (Y * X).
    """

    if sensitivity <= 0:
        coeff[:] = 0
        return
    dcoeff = max(sensitivity, EPS) / 100.0
    lambdac = _lambda_threshold(num_pixels, scale_index)
    if lambdac <= 0:
        return

    if coeff.ndim == 2:
        # Global MAD for 2D.
        mean_val = coeff.mean(dtype=np.float32)
        mad = np.mean(np.abs(coeff - mean_val))
        threshold = (lambdac * mad) / dcoeff
        coeff[coeff < threshold] = 0
        return

    # Per-slice MAD for 3D (shape: Z x (Y*X)).
    flat = coeff.reshape(coeff.shape[0], -1)
    mean_val = flat.mean(axis=1, keepdims=True)
    mad = np.mean(np.abs(flat - mean_val), axis=1)
    threshold = (lambdac * mad) / dcoeff
    flat[flat < threshold[:, None]] = 0
    coeff[:] = flat.reshape(coeff.shape)


def _reconstruct(
    coeffs: list[np.ndarray],
    enabled_indices: list[int],
    combine_scales: bool,
) -> np.ndarray:
    """Reconstruct a spot-enhanced image from enabled wavelet scales.

    Parameters
    ----------
    coeffs : list[numpy.ndarray]
        Wavelet coefficients for each scale plus residual.
    enabled_indices : list[int]
        Indices of enabled scales.
    combine_scales : bool
        If True, use union of enabled scales; if False, enforce intersection
        (all enabled scales must be non-zero at a voxel).

    Returns
    -------
    numpy.ndarray
        Reconstructed image emphasizing candidate spots.
    """

    if not enabled_indices:
        return np.zeros_like(coeffs[0])
    stacked = np.stack([coeffs[i] for i in enabled_indices], axis=0)
    output = np.sum(stacked, axis=0)
    if not combine_scales:
        # Intersection: zero out any voxel missing a contribution.
        zero_mask = np.any(stacked == 0, axis=0)
        output[zero_mask] = 0
    return output


def _detect_2d(
    image: np.ndarray,
    configs: list[_ScaleConfig],
    combine_scales: bool,
    detect_negative: bool,
) -> np.ndarray:
    """Detect spots in a 2D image using UDWT + WAT thresholding.

    Parameters
    ----------
    image : numpy.ndarray
        Input 2D image.
    configs : list[_ScaleConfig]
        Scale enablement and sensitivity configuration.
    combine_scales : bool
        Whether to union enabled scales (True) or intersect them (False).
    detect_negative : bool
        If True, invert coefficients to detect dark spots.

    Returns
    -------
    numpy.ndarray
        Labeled mask of detected spots (int32).
    """

    _ensure_min_size(image.shape, len(configs))
    scales = _b3_spline_scales(image, len(configs))
    coeffs = _b3_wavelet_coefficients(image, scales)
    num_pixels = image.shape[0] * image.shape[1]

    enabled_indices: list[int] = []
    for idx, config in enumerate(configs):
        if not config.enabled:
            coeffs[idx][:] = 0
            continue
        enabled_indices.append(idx)
        if detect_negative:
            coeffs[idx] *= -1
        _apply_wat_threshold(coeffs[idx], idx, config.sensitivity, num_pixels)

    coeffs[-1][:] = 0
    reconstruction = _reconstruct(coeffs, enabled_indices, combine_scales)
    binary = reconstruction > 0
    return label(binary, connectivity=2).astype(np.int32, copy=False)


def _detect_2d_stack(
    stack: np.ndarray,
    configs: list[_ScaleConfig],
    combine_scales: bool,
    detect_negative: bool,
) -> np.ndarray:
    """Detect spots per-slice in a 3D stack using 2D UDWT.

    Parameters
    ----------
    stack : numpy.ndarray
        Input 3D stack (Z, Y, X).
    configs : list[_ScaleConfig]
        Scale enablement and sensitivity configuration.
    combine_scales : bool
        Whether to union enabled scales (True) or intersect them (False).
    detect_negative : bool
        If True, invert coefficients to detect dark spots.

    Returns
    -------
    numpy.ndarray
        3D labeled mask with unique IDs across slices.
    """

    labels = np.zeros(stack.shape, dtype=np.int32)
    next_label = 1
    for z in range(stack.shape[0]):
        slice_labels = _detect_2d(
            stack[z], configs, combine_scales, detect_negative
        )
        if slice_labels.max() > 0:
            # Offset labels so IDs remain unique across slices.
            slice_labels = slice_labels + (next_label - 1)
            next_label = int(slice_labels.max()) + 1
        labels[z] = slice_labels
    return labels


def _detect_3d(
    image: np.ndarray,
    configs: list[_ScaleConfig],
    combine_scales: bool,
    detect_negative: bool,
) -> np.ndarray:
    """Detect spots in a 3D volume using 3D UDWT.

    Parameters
    ----------
    image : numpy.ndarray
        Input 3D volume (Z, Y, X).
    configs : list[_ScaleConfig]
        Scale enablement and sensitivity configuration.
    combine_scales : bool
        Whether to union enabled scales (True) or intersect them (False).
    detect_negative : bool
        If True, invert coefficients to detect dark spots.

    Returns
    -------
    numpy.ndarray
        3D labeled mask (int32).
    """

    _ensure_min_size(image.shape, len(configs))
    scales = _b3_spline_scales(image, len(configs))
    coeffs = _b3_wavelet_coefficients(image, scales)
    num_pixels = image.shape[1] * image.shape[2]

    enabled_indices: list[int] = []
    for idx, config in enumerate(configs):
        if not config.enabled:
            coeffs[idx][:] = 0
            continue
        enabled_indices.append(idx)
        if detect_negative:
            coeffs[idx] *= -1
        _apply_wat_threshold(coeffs[idx], idx, config.sensitivity, num_pixels)

    coeffs[-1][:] = 0
    reconstruction = _reconstruct(coeffs, enabled_indices, combine_scales)
    binary = reconstruction > 0
    return label(binary, connectivity=3).astype(np.int32, copy=False)


class UDWTDetector(SenoQuantSpotDetector):
    """Undecimated B3-spline wavelet spot detector.

    Notes
    -----
    - Supports 2D images and 3D stacks.
    - 3D detection can be forced to 2D per-slice processing.
    - Output is a labeled mask suitable for napari ``Labels`` layers.
    """

    def __init__(self, models_root=None) -> None:
        """Initialize the detector wrapper.

        Parameters
        ----------
        models_root : pathlib.Path or None, optional
            Root folder for detector resources, by default None.
        """

        super().__init__("udwt", models_root=models_root)

    def run(self, **kwargs) -> dict:
        """Run the UDWT detector and return instance labels.

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
            Dictionary containing ``mask`` with instance labels. ``points`` is
            reserved for future extensions.

        Raises
        ------
        ValueError
            If the input is RGB or has unsupported dimensions.
        """

        layer = kwargs.get("layer")
        if layer is None:
            return {"mask": None, "points": None}
        if getattr(layer, "rgb", False):
            raise ValueError("UDWT requires single-channel images.")

        settings = kwargs.get("settings", {})
        num_scales = int(settings.get("num_scales", 3))
        num_scales = max(1, min(MAX_SCALES, num_scales))
        # "combine_scales" matches the union/combination option in the UI.
        combine_scales = bool(settings.get("combine_scales", False))
        detect_negative = bool(settings.get("detect_negative", False))
        force_2d = bool(settings.get("force_2d", False))

        configs: list[_ScaleConfig] = []
        for idx in range(1, MAX_SCALES + 1):
            enabled = bool(settings.get(f"scale_{idx}_enabled", idx <= num_scales))
            sensitivity = float(
                settings.get(f"scale_{idx}_sensitivity", 100.0)
            )
            sensitivity = max(0.0, min(100.0, sensitivity))
            configs.append(_ScaleConfig(enabled=enabled, sensitivity=sensitivity))
        configs = configs[:num_scales]

        data = layer_data_asarray(layer)
        if data.ndim not in (2, 3):
            raise ValueError("UDWT expects 2D images or 3D stacks.")

        image = np.asarray(data, dtype=np.float32)
        if image.ndim == 2:
            labels = _detect_2d(
                image, configs, combine_scales, detect_negative
            )
            return {"mask": labels}

        if force_2d:
            labels = _detect_2d_stack(
                image, configs, combine_scales, detect_negative
            )
            return {"mask": labels}

        labels = _detect_3d(image, configs, combine_scales, detect_negative)
        return {"mask": labels}
