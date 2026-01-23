"""Post-processing helpers using StarDist geometry and NMS."""

from __future__ import annotations

import numpy as np


def instances_from_prediction_2d(
    prob: np.ndarray,
    dist: np.ndarray,
    *,
    grid: tuple[int, int],
    prob_thresh: float,
    nms_thresh: float,
    scale: dict[str, float] | None = None,
    img_shape: tuple[int, int] | None = None,
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
    scale : dict[str, float], optional
        Scale factors applied to the input image before inference. If
        provided, must include ``"X"`` and ``"Y"`` so that points and
        distances can be rescaled back to the original image space.
    img_shape : tuple[int, int], optional
        Original image shape (Y, X). If provided, the output label image
        is generated in this shape instead of the scaled prediction shape.
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
    from ..._stardist.nms import non_maximum_suppression
    points, scores, distances = non_maximum_suppression(
        dist,
        prob,
        grid=grid,
        prob_thresh=prob_thresh,
        nms_thresh=nms_thresh,
    )
    if scale is not None:
        if not (isinstance(scale, dict) and "X" in scale and "Y" in scale):
            raise ValueError("scale must be a dictionary with entries for 'X' and 'Y'")
        rescale = (1 / scale["Y"], 1 / scale["X"])
        points = points * np.array(rescale).reshape(1, 2)
    else:
        rescale = (1, 1)
    from ..._stardist.geometry.geom2d import polygons_to_label
    shape = img_shape if img_shape is not None else tuple(
        s * g for s, g in zip(prob.shape, grid)
    )
    labels = polygons_to_label(
        distances, points, shape=shape, prob=scores, scale_dist=rescale
    )
    return labels, {"points": points, "prob": scores, "dist": distances}


def instances_from_prediction_3d(
    prob: np.ndarray,
    dist: np.ndarray,
    *,
    grid: tuple[int, int, int],
    prob_thresh: float,
    nms_thresh: float,
    rays,
    scale: dict[str, float] | None = None,
    img_shape: tuple[int, int, int] | None = None,
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
    scale : dict[str, float], optional
        Scale factors applied to the input image before inference. If
        provided, must include ``"X"``, ``"Y"``, and ``"Z"`` so that points
        and rays can be rescaled back to the original image space.
    img_shape : tuple[int, int, int], optional
        Original image shape (Z, Y, X). If provided, the output label
        volume is generated in this shape instead of the scaled prediction
        shape.
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
    from ..._stardist.nms import non_maximum_suppression_3d
    points, scores, distances = non_maximum_suppression_3d(
        dist,
        prob,
        rays,
        grid=grid,
        prob_thresh=prob_thresh,
        nms_thresh=nms_thresh,
    )
    if scale is not None:
        if not (
            isinstance(scale, dict)
            and "X" in scale
            and "Y" in scale
            and "Z" in scale
        ):
            raise ValueError(
                "scale must be a dictionary with entries for 'X', 'Y', and 'Z'"
            )
        rescale = (1 / scale["Z"], 1 / scale["Y"], 1 / scale["X"])
        points = points * np.array(rescale).reshape(1, 3)
        rays = rays.copy(scale=rescale)
    else:
        rescale = (1, 1, 1)
    from ..._stardist.geometry.geom3d import polyhedron_to_label
    shape = img_shape if img_shape is not None else tuple(
        s * g for s, g in zip(prob.shape, grid)
    )
    labels = polyhedron_to_label(
        distances, points, rays=rays, shape=shape, prob=scores, verbose=False
    )
    return labels, {"points": points, "prob": scores, "dist": distances}
