"""RMP spot detector implementation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
from skimage.filters import threshold_otsu
from skimage.measure import label, regionprops
from skimage.morphology import opening, rectangle
from skimage.transform import rotate
from skimage.util import img_as_ubyte

from ..model import SenoQuantSpotDetector


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


def _rmp(
    input_image: Array2D,
    denoising_se_length: int,
    extraction_se_length: int,
    angle_spacing: int,
    auto_threshold: bool,
    manual_threshold: float,
    enable_denoising: bool,
) -> Array2D:
    """Run the full RMP pipeline and return a binary mask."""
    denoising_se = rectangle(1, denoising_se_length)
    extraction_se = rectangle(1, extraction_se_length)
    rotation_angles = tuple(range(0, 180, angle_spacing))

    working_image = (
        _rmp_opening(input_image, denoising_se, rotation_angles)
        if enable_denoising
        else input_image
    )
    top_hat_image = _rmp_top_hat(working_image, extraction_se, rotation_angles)

    threshold = threshold_otsu(top_hat_image) if auto_threshold else manual_threshold
    binary_image = img_as_ubyte(top_hat_image > threshold)
    return binary_image


def _mask_to_points(mask: np.ndarray, z_index: int | None = None) -> list[tuple[float, ...]]:
    """Extract centroid points from a binary mask."""
    labels = label(mask > 0)
    points = []
    for region in regionprops(labels):
        cy, cx = region.centroid
        if z_index is None:
            points.append((float(cy), float(cx)))
        else:
            points.append((float(z_index), float(cy), float(cx)))
    return points


@dataclass(slots=True)
class RMPSettings:
    """Configuration for the RMP detector."""

    denoising_se_length: int = 2
    extraction_se_length: int = 10
    angle_spacing: int = 5
    auto_threshold: bool = True
    manual_threshold: float = 0.5
    enable_denoising: bool = True
    use_3d: bool = False

class RMPDetector(SenoQuantSpotDetector):
    """RMP spot detector implementation."""

    def __init__(self, models_root=None) -> None:
        super().__init__("rmp", models_root=models_root)

    def run(self, **kwargs) -> dict:
        """Run the RMP detector and return mask + points.

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
            Dictionary with ``mask`` and ``points`` keys.
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

        data = np.asarray(layer.data)
        if data.ndim not in (2, 3):
            raise ValueError("RMP expects 2D images or 3D stacks.")

        normalized = _normalize_image(data)
        if normalized.ndim == 3 and not config.use_3d:
            raise ValueError("Enable 3D to process stacks.")

        if normalized.ndim == 2:
            image_2d = normalized
            mask = _rmp(
                image_2d,
                config.denoising_se_length,
                config.extraction_se_length,
                config.angle_spacing,
                config.auto_threshold,
                config.manual_threshold,
                config.enable_denoising,
            )
            points = _mask_to_points(mask)
            points_array = np.asarray(points, dtype=float)
            if points_array.size == 0:
                points_array = np.empty((0, 2), dtype=float)
            return {"mask": mask, "points": points_array}

        mask_stack = np.zeros_like(normalized, dtype=np.uint8)
        points: list[tuple[float, ...]] = []
        for z in range(normalized.shape[0]):
            slice_mask = _rmp(
                normalized[z],
                config.denoising_se_length,
                config.extraction_se_length,
                config.angle_spacing,
                config.auto_threshold,
                config.manual_threshold,
                config.enable_denoising,
            )
            mask_stack[z] = slice_mask
            points.extend(_mask_to_points(slice_mask, z_index=z))

        points_array = np.asarray(points, dtype=float)
        if points_array.size == 0:
            points_array = np.empty((0, 3), dtype=float)
        return {"mask": mask_stack, "points": points_array}
