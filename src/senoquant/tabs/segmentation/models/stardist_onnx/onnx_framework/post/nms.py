"""Python NMS helpers for StarDist post-processing."""

from __future__ import annotations

import numpy as np
from skimage.draw import polygon


def _normalize_grid(grid, ndim: int) -> tuple[int, ...]:
    if np.isscalar(grid):
        return (int(grid),) * ndim
    grid = tuple(int(g) for g in grid)
    if len(grid) != ndim:
        raise ValueError("Grid must match dimensionality.")
    return grid


def _ind_prob_thresh(prob: np.ndarray, prob_thresh: float, b=2) -> np.ndarray:
    if b is not None and np.isscalar(b):
        b = ((b, b),) * prob.ndim
    ind_thresh = prob > prob_thresh
    if b is not None:
        _ind_thresh = np.zeros_like(ind_thresh, dtype=bool)
        ss = tuple(
            slice(_bs[0] if _bs[0] > 0 else None, -_bs[1] if _bs[1] > 0 else None)
            for _bs in b
        )
        _ind_thresh[ss] = True
        ind_thresh &= _ind_thresh
    return ind_thresh


def _ray_angles(n_rays: int) -> np.ndarray:
    return 2 * np.pi * np.arange(n_rays, dtype=np.float32) / float(n_rays)


def _dist_to_coord(
    dist: np.ndarray,
    points: np.ndarray,
    scale_dist: tuple[float, float] = (1.0, 1.0),
) -> np.ndarray:
    dist = np.asarray(dist)
    points = np.asarray(points)
    n_rays = dist.shape[1]
    phis = _ray_angles(n_rays)
    coord = dist[:, np.newaxis] * np.array(
        [np.sin(phis), np.cos(phis)], dtype=np.float32
    )
    coord *= np.asarray(scale_dist, dtype=np.float32).reshape(1, 2, 1)
    coord += points[..., np.newaxis]
    return coord


def _poly_mask_2d(
    coord: np.ndarray,
    bbox: tuple[int, int, int, int],
) -> np.ndarray:
    y0, y1, x0, x1 = bbox
    shape = (y1 - y0, x1 - x0)
    rr, cc = polygon(coord[0] - y0, coord[1] - x0, shape)
    mask = np.zeros(shape, dtype=bool)
    mask[rr, cc] = True
    return mask


def _bbox_from_coord(coord: np.ndarray, shape: tuple[int, int]) -> tuple[int, int, int, int]:
    y_min = int(np.floor(coord[0].min()))
    y_max = int(np.ceil(coord[0].max())) + 1
    x_min = int(np.floor(coord[1].min()))
    x_max = int(np.ceil(coord[1].max())) + 1
    y0 = max(0, y_min)
    x0 = max(0, x_min)
    y1 = min(shape[0], y_max)
    x1 = min(shape[1], x_max)
    return y0, y1, x0, x1


def non_maximum_suppression_python(
    dist: np.ndarray,
    prob: np.ndarray,
    *,
    grid: tuple[int, int],
    prob_thresh: float,
    nms_thresh: float,
    b: int | None = 2,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Python fallback NMS for 2D StarDist predictions."""
    grid = _normalize_grid(grid, 2)
    mask = _ind_prob_thresh(prob, prob_thresh, b=b)
    if not np.any(mask):
        return (
            np.zeros((0, 2), dtype=np.float32),
            np.zeros((0,), dtype=np.float32),
            np.zeros((0, dist.shape[-1]), dtype=np.float32),
        )

    points = np.stack(np.where(mask), axis=1)
    scores = prob[mask].astype(np.float32, copy=False)
    distances = dist[mask].astype(np.float32, copy=False)

    order = np.argsort(scores)[::-1]
    points = points[order]
    scores = scores[order]
    distances = distances[order]

    points = points * np.array(grid, dtype=np.float32).reshape((1, 2))
    image_shape = (prob.shape[0] * grid[0], prob.shape[1] * grid[1])

    coord = _dist_to_coord(distances, points, scale_dist=(1.0, 1.0))

    bboxes = []
    masks = []
    areas = []
    for c in coord:
        bbox = _bbox_from_coord(c, image_shape)
        if bbox[0] >= bbox[1] or bbox[2] >= bbox[3]:
            bboxes.append(bbox)
            masks.append(None)
            areas.append(0)
            continue
        mask_poly = _poly_mask_2d(c, bbox)
        bboxes.append(bbox)
        masks.append(mask_poly)
        areas.append(int(mask_poly.sum()))

    keep = []
    for i in range(len(scores)):
        if areas[i] == 0:
            continue
        suppress = False
        for j in keep:
            y0 = max(bboxes[i][0], bboxes[j][0])
            y1 = min(bboxes[i][1], bboxes[j][1])
            x0 = max(bboxes[i][2], bboxes[j][2])
            x1 = min(bboxes[i][3], bboxes[j][3])
            if y0 >= y1 or x0 >= x1:
                continue
            mi = masks[i][
                y0 - bboxes[i][0] : y1 - bboxes[i][0],
                x0 - bboxes[i][2] : x1 - bboxes[i][2],
            ]
            mj = masks[j][
                y0 - bboxes[j][0] : y1 - bboxes[j][0],
                x0 - bboxes[j][2] : x1 - bboxes[j][2],
            ]
            inter = np.logical_and(mi, mj).sum()
            if inter / float(min(areas[i], areas[j])) > nms_thresh:
                suppress = True
                break
        if not suppress:
            keep.append(i)

    keep = np.array(keep, dtype=int)
    return points[keep], scores[keep], distances[keep]


def non_maximum_suppression_3d_python(
    dist: np.ndarray,
    prob: np.ndarray,
    rays,
    *,
    grid: tuple[int, int, int],
    prob_thresh: float,
    nms_thresh: float,
    b: int | None = 2,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Approximate Python NMS for 3D StarDist predictions using AABBs."""
    grid = _normalize_grid(grid, 3)
    mask = _ind_prob_thresh(prob, prob_thresh, b=b)
    if not np.any(mask):
        return (
            np.zeros((0, 3), dtype=np.float32),
            np.zeros((0,), dtype=np.float32),
            np.zeros((0, dist.shape[-1]), dtype=np.float32),
        )

    points = np.stack(np.where(mask), axis=1)
    scores = prob[mask].astype(np.float32, copy=False)
    distances = dist[mask].astype(np.float32, copy=False)

    order = np.argsort(scores)[::-1]
    points = points[order]
    scores = scores[order]
    distances = distances[order]

    points = points * np.array(grid, dtype=np.float32).reshape((1, 3))

    rays_vertices = np.asarray(rays.vertices, dtype=np.float32)
    extents = distances[:, :, np.newaxis] * rays_vertices[np.newaxis, :, :]
    mins = extents.min(axis=1)
    maxs = extents.max(axis=1)
    mins += points
    maxs += points

    volumes = np.prod(maxs - mins, axis=1)

    keep = []
    for i in range(len(scores)):
        if volumes[i] <= 0:
            continue
        suppress = False
        for j in keep:
            inter_min = np.maximum(mins[i], mins[j])
            inter_max = np.minimum(maxs[i], maxs[j])
            inter_dims = np.maximum(inter_max - inter_min, 0)
            inter_vol = np.prod(inter_dims)
            if inter_vol / float(min(volumes[i], volumes[j])) > nms_thresh:
                suppress = True
                break
        if not suppress:
            keep.append(i)

    keep = np.array(keep, dtype=int)
    return points[keep], scores[keep], distances[keep]
