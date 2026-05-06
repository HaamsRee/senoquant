"""Configuration constants for the RMP spot detector."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


Array2D = np.ndarray
KernelShape = tuple[int, int]

# Numeric stability guard used in divisions/variance computations.
EPS = 1e-6

# Robust normalization controls for top-hat response scaling.
# Larger NOISE_FLOOR_SIGMA suppresses more low-level background.
NOISE_FLOOR_SIGMA = 1.5
# Lower bound on dynamic-range scaling relative to estimated noise.
MIN_SCALE_SIGMA = 4.5
# High percentile used to set bright-signal scale for [0, 1] normalization.
SIGNAL_SCALE_QUANTILE = 99.9

# If True, maxima are extracted from Laplacian response instead of raw enhanced image.
USE_LAPLACE_FOR_PEAKS = False

# Peak quality gates before watershed seeding.
# Relative to robust high-intensity scale; higher => fewer weak peaks.
PEAK_RELATIVE_INTENSITY_MIN = 0.1
# Relative local prominence (vs 3x3 local minimum); higher => fewer plateau peaks.
PEAK_RELATIVE_PROMINENCE_MIN = 0.1
# Center-bias multiplier in distance-weighted response.
# Higher => prefer component-center peaks over boundary peaks.
PEAK_COMPONENT_DISTANCE_WEIGHT = 1.0
# Hard center-distance gate (0..1 in each component).
# Higher => keep only deeper interior peaks.
PEAK_MIN_COMPONENT_DISTANCE_RATIO = 0.4

# Fixed sigma passed to BayesShrink wavelet denoising.
# Set to None for automatic sigma estimation.
WAVELET_SIGMA = None

# Tile size used by tiled top-hat execution.
RMP_TILE_CHUNK_SIZE: tuple[int, int] = (512, 512)

# Anisotropy detection and correction knobs (3D only).
# Peak sampling percentile for candidate spots used in anisotropy estimation.
ANISO_DETECT_PERCENTILE = 99.2
# Minimum accepted number of valid spot patches for a stable anisotropy estimate.
ANISO_MIN_SPOTS = 12
# Max number of brightest local maxima evaluated for anisotropy estimation.
ANISO_MAX_SPOTS = 256
# Half-size of local patch in z around each candidate spot.
ANISO_PATCH_RADIUS_Z = 3
# Half-size of local patch in y/x around each candidate spot.
ANISO_PATCH_RADIUS_XY = 3
# Ratio bounds around isotropy (sigma_z / sigma_xy) where no correction is applied.
ANISO_RATIO_LOW = 0.8
ANISO_RATIO_HIGH = 1.2
# Maximum IQR of per-spot anisotropy ratios; larger IQR => estimate considered unreliable.
ANISO_RATIO_IQR_MAX = 0.6
# Clamp bounds for z resampling factor during isotropization.
ANISO_Z_SCALE_MIN = 0.2
ANISO_Z_SCALE_MAX = 2


@dataclass(slots=True)
class RMPSettings:
    """Configuration for the RMP detector."""

    extraction_se_length: int = 10
    angle_spacing: int = 10
    auto_threshold: bool = True
    manual_threshold: float = 0.50
    enable_denoising: bool = True
