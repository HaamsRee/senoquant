"""Geometry-based ROI centroid membership helpers."""

from __future__ import annotations

from dataclasses import dataclass

from matplotlib.path import Path as MplPath
import numpy as np

PLANE_TOLERANCE = 1e-6
BOUNDARY_RADIUS = 1e-9


@dataclass(frozen=True)
class ROIGeometry:
    """Projected ROI geometry used for centroid membership checks.

    Attributes
    ----------
    plane_axes : tuple of int
        Axes in centroid space used by this geometry.
    path : matplotlib.path.Path
        Polygon path in the projected plane.
    """

    plane_axes: tuple[int, int]
    path: MplPath


def build_layer_geometries(layer: object, ndim: int) -> list[ROIGeometry] | None:
    """Build projected ROI geometries from a napari Shapes layer.

    Parameters
    ----------
    layer : object
        napari Shapes-like layer exposing ``data`` and optional ``shape_type``.
    ndim : int
        Number of spatial dimensions in centroid coordinates.

    Returns
    -------
    list of ROIGeometry or None
        Geometries extracted from the layer, or ``None`` when geometry
        extraction is not possible.
    """
    data = getattr(layer, "data", None)
    if data is None:
        return None
    try:
        shapes = list(data)
    except Exception:
        return None
    shape_types = _shape_types(layer, len(shapes))
    geometries: list[ROIGeometry] = []
    for vertices, shape_type in zip(shapes, shape_types):
        if _ignored_shape_type(shape_type):
            continue
        geometry = _geometry_from_vertices(np.asarray(vertices, dtype=float), ndim)
        if geometry is not None:
            geometries.append(geometry)
    return geometries


def membership_from_layer(
    layer: object, centroids: np.ndarray
) -> np.ndarray | None:
    """Return ROI membership values for centroid coordinates.

    Parameters
    ----------
    layer : object
        napari Shapes-like layer.
    centroids : numpy.ndarray
        Centroid coordinates in pixel units.

    Returns
    -------
    numpy.ndarray or None
        Boolean membership for each centroid, or ``None`` if layer geometry
        cannot be evaluated.
    """
    points = np.asarray(centroids, dtype=float)
    if points.ndim != 2:
        return None
    geometries = build_layer_geometries(layer, points.shape[1])
    if geometries is None:
        return None
    return membership_from_geometries(points, geometries)


def membership_from_geometries(
    centroids: np.ndarray, geometries: list[ROIGeometry]
) -> np.ndarray:
    """Evaluate centroid membership against prebuilt ROI geometries.

    Parameters
    ----------
    centroids : numpy.ndarray
        Centroid coordinates in pixel units.
    geometries : list of ROIGeometry
        ROI geometries projected to centroid axes.

    Returns
    -------
    numpy.ndarray
        Boolean membership for each centroid.
    """
    points = np.asarray(centroids, dtype=float)
    if points.ndim != 2:
        return np.zeros((0,), dtype=bool)
    if points.size == 0:
        return np.zeros((0,), dtype=bool)
    included = np.zeros((points.shape[0],), dtype=bool)
    for geometry in geometries:
        projected_points = points[:, geometry.plane_axes]
        included |= geometry.path.contains_points(
            projected_points,
            radius=BOUNDARY_RADIUS,
        )
    return included


def _shape_types(layer: object, count: int) -> list[str | None]:
    """Normalize layer shape-type metadata to ``count`` entries."""
    if count <= 0:
        return []
    raw_shape_types = getattr(layer, "shape_type", None)
    if raw_shape_types is None:
        return [None] * count
    if isinstance(raw_shape_types, str):
        return [raw_shape_types] * count
    try:
        values = list(raw_shape_types)
    except Exception:
        return [None] * count
    types = [
        str(value).strip().lower() if value is not None else None for value in values
    ]
    if len(types) < count:
        pad = types[-1] if types else None
        types.extend([pad] * (count - len(types)))
    return types[:count]


def _ignored_shape_type(shape_type: str | None) -> bool:
    """Return whether a shape type should be ignored for ROI membership."""
    if shape_type is None:
        return False
    return shape_type in {"line", "path"}


def _geometry_from_vertices(
    vertices: np.ndarray, ndim: int
) -> ROIGeometry | None:
    """Build a projected ROI geometry from one shape vertex array."""
    if ndim < 2:
        return None
    if vertices.ndim != 2 or vertices.shape[0] < 3:
        return None
    if not np.all(np.isfinite(vertices)):
        return None

    vertex_dims = int(vertices.shape[1])
    if vertex_dims < 2:
        return None

    if vertex_dims <= ndim:
        offset = ndim - vertex_dims
        ranges = np.ptp(vertices, axis=0)
        varying = np.flatnonzero(ranges > PLANE_TOLERANCE)
        if varying.size != 2:
            return None
        projected = vertices[:, varying]
        plane_axes = (int(varying[0] + offset), int(varying[1] + offset))
    else:
        reduced = vertices[:, :ndim]
        ranges = np.ptp(reduced, axis=0)
        varying = np.flatnonzero(ranges > PLANE_TOLERANCE)
        if varying.size != 2:
            return None
        projected = reduced[:, varying]
        plane_axes = (int(varying[0]), int(varying[1]))

    unique_points = np.unique(np.round(projected, decimals=8), axis=0)
    if unique_points.shape[0] < 3:
        return None
    return ROIGeometry(
        plane_axes=plane_axes,
        path=MplPath(projected),
    )
