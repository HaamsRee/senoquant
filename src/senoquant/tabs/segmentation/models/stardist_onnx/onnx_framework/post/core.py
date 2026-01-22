"""Post-processing helpers using StarDist geometry and NMS."""

from __future__ import annotations

import numpy as np

from .nms import (
    non_maximum_suppression_3d_python,
    non_maximum_suppression_python,
)


def instances_from_prediction_2d(
    prob: np.ndarray,
    dist: np.ndarray,
    *,
    grid: tuple[int, int],
    prob_thresh: float,
    nms_thresh: float,
    nms_backend: str = "compiled",
) -> tuple[np.ndarray, dict]:
    """Create 2D instance labels from StarDist outputs.

    Parameters
    ----------
    prob : numpy.ndarray
        Probability map with shape (Y, X).
    dist : numpy.ndarray
        Distance/ray map with shape (Y, X, R), where R is the number of rays.
    grid : tuple[int, int]
        Subsampling grid of the model (e.g., (1, 1) or (2, 2)).
    prob_thresh : float
        Probability threshold used to filter candidate points before NMS.
    nms_thresh : float
        NMS IoU/overlap threshold for suppressing nearby detections.
    nms_backend : str, optional
        NMS backend to use ("compiled" or "python"). Default is "compiled".

    Returns
    -------
    tuple[numpy.ndarray, dict]
        Label image of shape (Y, X) and a metadata dict with:
        - ``points``: center points used for each instance.
        - ``prob``: per-instance probabilities.
        - ``dist``: per-instance ray distances.

    Notes
    -----
    This function performs non-maximum suppression on the probability map
    and then rasterizes polygons using the selected points and distances.
    """
    if nms_backend == "python":
        points, scores, distances = non_maximum_suppression_python(
            dist,
            prob,
            grid=grid,
            prob_thresh=prob_thresh,
            nms_thresh=nms_thresh,
        )
    else:
        from ..._stardist.nms import non_maximum_suppression
        points, scores, distances = non_maximum_suppression(
            dist,
            prob,
            grid=grid,
            prob_thresh=prob_thresh,
            nms_thresh=nms_thresh,
        )
    from ..._stardist.geometry.geom2d import polygons_to_label
    shape = tuple(s * g for s, g in zip(prob.shape, grid))
    labels = polygons_to_label(distances, points, shape=shape, prob=scores)
    return labels, {"points": points, "prob": scores, "dist": distances}


def instances_from_prediction_3d(
    prob: np.ndarray,
    dist: np.ndarray,
    *,
    grid: tuple[int, int, int],
    prob_thresh: float,
    nms_thresh: float,
    rays,
    nms_backend: str = "compiled",
) -> tuple[np.ndarray, dict]:
    """Create 3D instance labels from StarDist outputs.

    Parameters
    ----------
    prob : numpy.ndarray
        Probability map with shape (Z, Y, X).
    dist : numpy.ndarray
        Distance/ray map with shape (Z, Y, X, R), where R is the number of rays.
    grid : tuple[int, int, int]
        Subsampling grid of the model (e.g., (1, 1, 1) or (2, 2, 2)).
    prob_thresh : float
        Probability threshold used to filter candidate points before NMS.
    nms_thresh : float
        NMS IoU/overlap threshold for suppressing nearby detections.
    rays : object
        StarDist 3D rays object describing ray directions and sampling.
    nms_backend : str, optional
        NMS backend to use ("compiled" or "python"). Default is "compiled".

    Returns
    -------
    tuple[numpy.ndarray, dict]
        Label volume of shape (Z, Y, X) and a metadata dict with:
        - ``points``: center points used for each instance.
        - ``prob``: per-instance probabilities.
        - ``dist``: per-instance ray distances.

    Notes
    -----
    This function performs non-maximum suppression in 3D and then
    rasterizes polyhedra using the selected points and distances. The
    Python backend uses an axis-aligned bounding-box approximation.
    """
    if nms_backend == "python":
        points, scores, distances = non_maximum_suppression_3d_python(
            dist,
            prob,
            rays,
            grid=grid,
            prob_thresh=prob_thresh,
            nms_thresh=nms_thresh,
        )
    else:
        from ..._stardist.nms import non_maximum_suppression_3d
        points, scores, distances = non_maximum_suppression_3d(
            dist,
            prob,
            rays,
            grid=grid,
            prob_thresh=prob_thresh,
            nms_thresh=nms_thresh,
        )
    from ..._stardist.geometry.geom3d import polyhedron_to_label
    shape = tuple(s * g for s, g in zip(prob.shape, grid))
    labels = polyhedron_to_label(
        distances, points, rays=rays, shape=shape, prob=scores, verbose=False
    )
    return labels, {"points": points, "prob": scores, "dist": distances}
