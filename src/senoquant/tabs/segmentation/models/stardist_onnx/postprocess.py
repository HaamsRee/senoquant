"""Post-processing helpers for StarDist ONNX outputs."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from skimage.draw import polygon


def ray_angles(n_rays: int) -> np.ndarray:
    """Return ray angles in radians."""
    return np.linspace(0, 2 * np.pi, n_rays, endpoint=False)


def dist_to_coord(
    dist: np.ndarray,
    points: np.ndarray,
    scale_dist: tuple[float, float] = (1.0, 1.0),
) -> np.ndarray:
    """Convert polar distances to polygon coordinates."""
    dist = np.asarray(dist)
    points = np.asarray(points)
    if dist.ndim != 2 or points.ndim != 2 or points.shape[1] != 2:
        raise ValueError("dist must be (N, R) and points must be (N, 2).")
    if len(dist) != len(points):
        raise ValueError("dist and points must have matching lengths.")

    phis = ray_angles(dist.shape[1])
    coord = dist[:, np.newaxis] * np.array([np.sin(phis), np.cos(phis)])
    coord = coord.astype(np.float32)
    coord *= np.asarray(scale_dist).reshape(1, 2, 1)
    coord += points[..., np.newaxis]
    return coord


def polygons_to_label_coord(
    coord: np.ndarray,
    shape: tuple[int, int],
    labels: np.ndarray | None = None,
) -> np.ndarray:
    """Render polygon coordinates into a label image."""
    coord = np.asarray(coord)
    if coord.ndim != 3 or coord.shape[1] != 2:
        raise ValueError("coord must be (N, 2, R).")
    if labels is None:
        labels = np.arange(len(coord))
    labels = np.asarray(labels)
    if len(labels) != len(coord):
        raise ValueError("labels must align with coord length.")

    lbl = np.zeros(shape, np.int32)
    for label, poly in zip(labels, coord):
        rr, cc = polygon(poly[0], poly[1], shape)
        lbl[rr, cc] = label + 1
    return lbl


def polygons_to_label(
    dist: np.ndarray,
    points: np.ndarray,
    shape: tuple[int, int],
    prob: np.ndarray | None = None,
    thr: float = -np.inf,
    scale_dist: tuple[float, float] = (1.0, 1.0),
) -> np.ndarray:
    """Convert polygon distances and points into a label image."""
    dist = np.asarray(dist)
    points = np.asarray(points)
    if prob is None:
        prob = np.full(len(points), np.inf, dtype=np.float32)
    prob = np.asarray(prob)

    if dist.ndim != 2 or points.ndim != 2 or points.shape[1] != 2:
        raise ValueError("dist must be (N, R) and points must be (N, 2).")
    if len(dist) != len(points) or len(points) != len(prob):
        raise ValueError("dist, points, and prob must have matching lengths.")

    keep = prob > thr
    dist = dist[keep]
    points = points[keep]
    prob = prob[keep]

    order = np.argsort(prob, kind="stable")
    dist = dist[order]
    points = points[order]
    labels = order

    coord = dist_to_coord(dist, points, scale_dist=scale_dist)
    return polygons_to_label_coord(coord, shape=shape, labels=labels)


@dataclass(frozen=True)
class _PolygonData:
    mask: np.ndarray
    bbox: tuple[int, int, int, int]
    area: int


def non_maximum_suppression_2d(
    dist: np.ndarray,
    prob: np.ndarray,
    points: np.ndarray,
    nms_thresh: float,
    image_shape: tuple[int, int],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Naive NMS for 2D polygons using rasterized overlap."""
    if len(prob) == 0:
        return dist, prob, points

    order = np.argsort(prob)[::-1]
    dist = dist[order]
    prob = prob[order]
    points = points[order]

    coord = dist_to_coord(dist, points)
    polys = [_polygon_to_mask(poly, image_shape) for poly in coord]

    keep: list[int] = []
    for idx, poly in enumerate(polys):
        if poly.area == 0:
            continue
        suppressed = False
        for kept_idx in keep:
            overlap = _overlap_ratio(poly, polys[kept_idx])
            if overlap > nms_thresh:
                suppressed = True
                break
        if not suppressed:
            keep.append(idx)

    if not keep:
        return dist[:0], prob[:0], points[:0]
    keep_array = np.asarray(keep, dtype=int)
    return dist[keep_array], prob[keep_array], points[keep_array]


def instances_from_prediction_2d(
    prob: np.ndarray,
    dist: np.ndarray,
    image_shape: tuple[int, int],
    grid: tuple[int, int],
    prob_thresh: float,
    nms_thresh: float,
    border: int = 2,
) -> tuple[np.ndarray, dict]:
    """Generate instance labels from StarDist probability and distance maps."""
    if prob.ndim != 2 or dist.ndim != 3:
        raise ValueError("prob must be (Y, X) and dist must be (Y, X, R).")
    if prob.shape != dist.shape[:2]:
        raise ValueError("prob and dist shapes are incompatible.")

    mask = _candidate_mask(prob, prob_thresh, border)
    points = np.stack(np.where(mask), axis=1)

    if points.size == 0:
        labels = np.zeros(image_shape, dtype=np.int32)
        empty = np.empty((0, dist.shape[-1]), dtype=np.float32)
        return labels, {"points": np.empty((0, 2), dtype=int), "prob": np.empty(0), "dist": empty}

    scores = prob[mask].astype(np.float32)
    distances = dist[mask].astype(np.float32)
    points = points * np.array(grid)

    distances, scores, points = non_maximum_suppression_2d(
        distances, scores, points, nms_thresh, image_shape
    )
    labels = polygons_to_label(distances, points, shape=image_shape, prob=scores)

    return labels, {"points": points, "prob": scores, "dist": distances}


def instances_from_prediction_3d(
    prob: np.ndarray,
    dist: np.ndarray,
    image_shape: tuple[int, int, int],
    grid: tuple[int, int, int],
    prob_thresh: float,
    nms_thresh: float,
    border: int = 2,
) -> tuple[np.ndarray, dict]:
    """Generate instance labels from 3D StarDist probability and distance maps."""
    if prob.ndim != 3 or dist.ndim != 4:
        raise ValueError("prob must be (Z, Y, X) and dist must be (Z, Y, X, R).")
    if prob.shape != dist.shape[:3]:
        raise ValueError("prob and dist shapes are incompatible.")

    mask = _candidate_mask(prob, prob_thresh, border)
    points = np.stack(np.where(mask), axis=1)

    if points.size == 0:
        labels = np.zeros(image_shape, dtype=np.int32)
        empty = np.empty((0, dist.shape[-1]), dtype=np.float32)
        return labels, {
            "points": np.empty((0, 3), dtype=int),
            "prob": np.empty(0),
            "dist": empty,
            "radii": np.empty(0),
        }

    scores = prob[mask].astype(np.float32)
    distances = dist[mask].astype(np.float32)
    points = points * np.array(grid)

    distances, scores, points, radii = non_maximum_suppression_3d(
        distances, scores, points, nms_thresh, image_shape
    )
    labels = spheres_to_label(points, radii, image_shape, scores)

    return labels, {
        "points": points,
        "prob": scores,
        "dist": distances,
        "radii": radii,
    }


def _candidate_mask(
    prob: np.ndarray, prob_thresh: float, border: int
) -> np.ndarray:
    mask = prob > prob_thresh
    if border > 0:
        inner = np.zeros_like(mask, dtype=bool)
        slices = tuple(
            slice(border, -border if border > 0 else None) for _ in range(mask.ndim)
        )
        inner[slices] = True
        mask &= inner
    return mask


def _polygon_to_mask(
    coord: np.ndarray, shape: tuple[int, int]
) -> _PolygonData:
    min_r = int(np.floor(coord[0].min()))
    max_r = int(np.ceil(coord[0].max())) + 1
    min_c = int(np.floor(coord[1].min()))
    max_c = int(np.ceil(coord[1].max())) + 1

    min_r = max(min_r, 0)
    min_c = max(min_c, 0)
    max_r = min(max_r, shape[0])
    max_c = min(max_c, shape[1])

    if max_r <= min_r or max_c <= min_c:
        empty_mask = np.zeros((0, 0), dtype=bool)
        return _PolygonData(empty_mask, (0, 0, 0, 0), 0)

    bbox_shape = (max_r - min_r, max_c - min_c)
    rr, cc = polygon(coord[0] - min_r, coord[1] - min_c, bbox_shape)
    mask = np.zeros(bbox_shape, dtype=bool)
    mask[rr, cc] = True
    area = int(mask.sum())

    return _PolygonData(mask, (min_r, max_r, min_c, max_c), area)


def _overlap_ratio(poly_a: _PolygonData, poly_b: _PolygonData) -> float:
    if poly_a.area == 0 or poly_b.area == 0:
        return 0.0

    r0 = max(poly_a.bbox[0], poly_b.bbox[0])
    r1 = min(poly_a.bbox[1], poly_b.bbox[1])
    c0 = max(poly_a.bbox[2], poly_b.bbox[2])
    c1 = min(poly_a.bbox[3], poly_b.bbox[3])
    if r1 <= r0 or c1 <= c0:
        return 0.0

    slice_a = (slice(r0 - poly_a.bbox[0], r1 - poly_a.bbox[0]),
               slice(c0 - poly_a.bbox[2], c1 - poly_a.bbox[2]))
    slice_b = (slice(r0 - poly_b.bbox[0], r1 - poly_b.bbox[0]),
               slice(c0 - poly_b.bbox[2], c1 - poly_b.bbox[2]))

    inter = np.logical_and(poly_a.mask[slice_a], poly_b.mask[slice_b]).sum()
    return float(inter) / float(min(poly_a.area, poly_b.area))


def non_maximum_suppression_3d(
    dist: np.ndarray,
    prob: np.ndarray,
    points: np.ndarray,
    nms_thresh: float,
    image_shape: tuple[int, int, int],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Naive NMS for 3D candidates using axis-aligned bounding boxes."""
    if len(prob) == 0:
        empty = np.empty((0, dist.shape[-1]), dtype=np.float32)
        return empty, np.empty(0), np.empty((0, 3), dtype=int), np.empty(0)

    order = np.argsort(prob)[::-1]
    dist = dist[order]
    prob = prob[order]
    points = points[order]

    radii = np.median(dist, axis=1)
    boxes = _bounding_boxes(points, radii, image_shape)

    keep: list[int] = []
    for idx, bbox in enumerate(boxes):
        suppressed = False
        for kept_idx in keep:
            overlap = _bbox_overlap_ratio(bbox, boxes[kept_idx])
            if overlap > nms_thresh:
                suppressed = True
                break
        if not suppressed:
            keep.append(idx)

    if not keep:
        empty = np.empty((0, dist.shape[-1]), dtype=np.float32)
        return empty, np.empty(0), np.empty((0, 3), dtype=int), np.empty(0)

    keep_array = np.asarray(keep, dtype=int)
    return (
        dist[keep_array],
        prob[keep_array],
        points[keep_array],
        radii[keep_array],
    )


def spheres_to_label(
    points: np.ndarray,
    radii: np.ndarray,
    shape: tuple[int, int, int],
    prob: np.ndarray | None = None,
) -> np.ndarray:
    """Render spheres around points into a label volume."""
    labels = np.zeros(shape, dtype=np.int32)
    if len(points) == 0:
        return labels

    order = np.argsort(prob) if prob is not None else np.arange(len(points))

    label_id = 1
    for idx in order:
        radius = float(radii[idx])
        if radius <= 0:
            continue
        center = points[idx].astype(float)
        z0 = max(int(np.floor(center[0] - radius)), 0)
        y0 = max(int(np.floor(center[1] - radius)), 0)
        x0 = max(int(np.floor(center[2] - radius)), 0)
        z1 = min(int(np.ceil(center[0] + radius)) + 1, shape[0])
        y1 = min(int(np.ceil(center[1] + radius)) + 1, shape[1])
        x1 = min(int(np.ceil(center[2] + radius)) + 1, shape[2])
        if z1 <= z0 or y1 <= y0 or x1 <= x0:
            continue

        zz, yy, xx = np.ogrid[z0:z1, y0:y1, x0:x1]
        mask = (
            (zz - center[0]) ** 2
            + (yy - center[1]) ** 2
            + (xx - center[2]) ** 2
            <= radius**2
        )
        labels[z0:z1, y0:y1, x0:x1][mask] = label_id
        label_id += 1

    return labels


def _bounding_boxes(
    points: np.ndarray,
    radii: np.ndarray,
    shape: tuple[int, int, int],
) -> list[tuple[int, int, int, int, int, int]]:
    boxes: list[tuple[int, int, int, int, int, int]] = []
    for center, radius in zip(points, radii):
        radius = max(float(radius), 0.0)
        z0 = max(int(np.floor(center[0] - radius)), 0)
        y0 = max(int(np.floor(center[1] - radius)), 0)
        x0 = max(int(np.floor(center[2] - radius)), 0)
        z1 = min(int(np.ceil(center[0] + radius)) + 1, shape[0])
        y1 = min(int(np.ceil(center[1] + radius)) + 1, shape[1])
        x1 = min(int(np.ceil(center[2] + radius)) + 1, shape[2])
        boxes.append((z0, z1, y0, y1, x0, x1))
    return boxes


def _bbox_overlap_ratio(
    bbox_a: tuple[int, int, int, int, int, int],
    bbox_b: tuple[int, int, int, int, int, int],
) -> float:
    z0 = max(bbox_a[0], bbox_b[0])
    z1 = min(bbox_a[1], bbox_b[1])
    y0 = max(bbox_a[2], bbox_b[2])
    y1 = min(bbox_a[3], bbox_b[3])
    x0 = max(bbox_a[4], bbox_b[4])
    x1 = min(bbox_a[5], bbox_b[5])
    if z1 <= z0 or y1 <= y0 or x1 <= x0:
        return 0.0

    inter = (z1 - z0) * (y1 - y0) * (x1 - x0)
    vol_a = (bbox_a[1] - bbox_a[0]) * (bbox_a[3] - bbox_a[2]) * (
        bbox_a[5] - bbox_a[4]
    )
    vol_b = (bbox_b[1] - bbox_b[0]) * (bbox_b[3] - bbox_b[2]) * (
        bbox_b[5] - bbox_b[4]
    )
    if vol_a == 0 or vol_b == 0:
        return 0.0
    return float(inter) / float(min(vol_a, vol_b))
