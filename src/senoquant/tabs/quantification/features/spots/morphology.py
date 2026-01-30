"""Morphological descriptor extraction for spots cells table.

This module provides utilities to extract morphological properties
from cell segmentations used in spots analysis. Morphology is only
added to the cells table, not the spots table.

Descriptors include area/volume, shape metrics, and perimeter.
"""

from __future__ import annotations

import warnings

import numpy as np
from skimage.measure import regionprops_table

# Float-valued morphological properties to extract from regionprops.
MORPHOLOGY_PROPERTIES = (
    "area",  # Number of pixels in the region
    "eccentricity",  # Eccentricity of the ellipse fitted to the region
    "extent",  # Ratio of region area to bounding box area
    "feret_diameter_max",  # Maximum Feret diameter
    "major_axis_length",  # Major axis of the ellipse fitted to the region
    "minor_axis_length",  # Minor axis of the ellipse fitted to the region
    "orientation",  # Angle between the major axis and horizontal
    "perimeter",  # Perimeter estimated by the Freeman chain code
    "perimeter_crofton",  # Crofton perimeter (Euclidean-like estimate)
    "solidity",  # Ratio of region area to convex hull area
)

NDIM_2D = 2
NDIM_3D = 3


def _collect_simple_properties(
    props: dict,
    label_ids: np.ndarray,
) -> dict[str, np.ndarray]:
    """Extract simple (non-array) properties from regionprops.

    Parameters
    ----------
    props : dict
        Output from regionprops_table.
    label_ids : numpy.ndarray
        Label ids for indexing.

    Returns
    -------
    dict of str to numpy.ndarray
        Simple property arrays keyed by property name.

    """
    result: dict[str, np.ndarray] = {}
    for prop_name, prop_values in props.items():
        if prop_name == "label":
            continue

        if isinstance(prop_values, list) and prop_values:
            first_val = prop_values[0]
            if isinstance(first_val, (np.ndarray, list, tuple)):
                continue

        try:
            prop_array = np.asarray(prop_values, dtype=float)
            if prop_array.size == len(label_ids):
                result[f"morph_{prop_name}"] = prop_array
        except (ValueError, TypeError):
            continue

    return result


def _compute_derived_metrics(
    result: dict[str, np.ndarray],
) -> None:
    """Compute derived morphological metrics in-place.

    Parameters
    ----------
    result : dict of str to numpy.ndarray
        Morphological properties to augment with derived metrics.

    Notes
    -----
    Circularity is 2D-only: 4*pi*area / perimeter^2. It is only computed
    when perimeter is available (which indicates 2D data).
    Aspect ratio is 2D-only and only computed when major/minor axis lengths
    are present in the result.

    """
    # Get area/volume (whichever exists after dimensionality-based renaming)
    if "morph_area" in result:
        area_or_volume = result["morph_area"]
    elif "morph_volume" in result:
        area_or_volume = result["morph_volume"]
    else:
        return

    # Circularity is 2D-only: 4*pi*area / perimeter^2
    if "morph_perimeter" in result:
        perim = result["morph_perimeter"]
        circularity = np.divide(
            4 * np.pi * area_or_volume,
            perim ** 2,
            out=np.full_like(area_or_volume, np.nan),
            where=perim != 0,
        )
        result["morph_circularity"] = circularity

    # Aspect ratio: only computed if major/minor axis lengths are present (2D only)
    if (
        "morph_major_axis_length" in result
        and "morph_minor_axis_length" in result
    ):
        major = result["morph_major_axis_length"]
        minor = result["morph_minor_axis_length"]
        aspect_ratio = np.divide(
            major,
            minor,
            out=np.full_like(major, np.nan),
            where=minor != 0,
        )
        result["morph_aspect_ratio"] = aspect_ratio


def _compute_physical_area(
    result: dict[str, np.ndarray],
    pixel_sizes: np.ndarray,
) -> None:
    """Add physical area/volume measurements to result in-place.

    Parameters
    ----------
    result : dict of str to numpy.ndarray
        Morphological properties to augment.
    pixel_sizes : numpy.ndarray
        Per-axis pixel sizes in micrometers.

    """
    # Determine if we have area (2D) or volume (3D)
    if "morph_area" in result:
        area_or_volume = result["morph_area"]
        is_volume = False
    elif "morph_volume" in result:
        area_or_volume = result["morph_volume"]
        is_volume = True
    else:
        return

    pixels = area_or_volume
    ndim = len(pixel_sizes)

    try:
        if ndim == NDIM_2D and not is_volume:
            area_phys = pixels * (pixel_sizes[0] * pixel_sizes[1])
            result["morph_area_um2"] = area_phys
        elif ndim == NDIM_3D and is_volume:
            volume_phys = pixels * (
                pixel_sizes[0] * pixel_sizes[1] * pixel_sizes[2]
            )
            result["morph_volume_um3"] = volume_phys
    except (TypeError, ValueError):
        pass


def extract_morphology(
    labels: np.ndarray,
    label_ids: np.ndarray,
    pixel_sizes: np.ndarray | None = None,
) -> dict[str, np.ndarray]:
    """Extract morphological descriptors for each labeled region.

    Parameters
    ----------
    labels : numpy.ndarray
        Label image with integer ids.
    label_ids : numpy.ndarray
        Specific label ids to extract properties for.
    pixel_sizes : numpy.ndarray or None, optional
        Per-axis pixel sizes in micrometers. When provided, physical
        measurements are computed.

    Returns
    -------
    dict of str to numpy.ndarray
        Morphological descriptors. Keys are property names and values are
        arrays with one entry per label id.

    Notes
    -----
    Properties that depend on regionprops (e.g., eccentricity, solidity)
    are only available for 2D images. For 3D, only simple properties like
    volume are available.

    The "area" property is renamed to "volume" for 3D images.

    Some properties may not be available depending on the scikit-image
    version. Missing properties are silently skipped.

    """
    # For 3D, some properties are not available. Try with all properties first,
    # and fall back to basic properties if it fails.
    try:
        props = regionprops_table(
            labels,
            properties=MORPHOLOGY_PROPERTIES,
        )
    except (ValueError, RuntimeError):
        # Fall back to basic properties for 3D
        try:
            props = regionprops_table(
                labels,
                properties=("area",),
            )
        except (ValueError, RuntimeError) as exc:
            warnings.warn(
                f"Failed to extract morphological properties: {exc}",
                RuntimeWarning,
                stacklevel=2,
            )
            return {}

    result = _collect_simple_properties(props, label_ids)

    # For 3D images, rename "area" to "volume"
    if labels.ndim == NDIM_3D and "morph_area" in result:
        result["morph_volume"] = result.pop("morph_area")

    _compute_derived_metrics(result)

    if pixel_sizes is not None:
        _compute_physical_area(result, pixel_sizes)

    return result


def add_morphology_columns(
    rows: list[dict],
    labels: np.ndarray,
    label_ids: np.ndarray,
    pixel_sizes: np.ndarray | None = None,
) -> list[str]:
    """Add morphological descriptor columns to output rows.

    Parameters
    ----------
    rows : list of dict
        Output row dictionaries to update in-place.
    labels : numpy.ndarray
        Label image with integer ids.
    label_ids : numpy.ndarray
        Label ids corresponding to the output rows.
    pixel_sizes : numpy.ndarray or None, optional
        Per-axis pixel sizes in micrometers.

    Returns
    -------
    list of str
        List of column names added to the rows.

    Notes
    -----
    This function modifies ``rows`` in-place and returns the list of new
    column names that were added for header generation.

    """
    morphology_data = extract_morphology(labels, label_ids, pixel_sizes)

    if not morphology_data or not rows:
        return []

    column_names: list[str] = []
    for col_name, col_values in morphology_data.items():
        column_names.append(col_name)
        for row, value in zip(rows, col_values, strict=True):
            row[col_name] = float(value) if not np.isnan(value) else value

    return column_names
