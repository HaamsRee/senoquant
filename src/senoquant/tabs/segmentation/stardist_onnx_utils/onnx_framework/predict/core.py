"""Tiled ONNX prediction helpers for StarDist.

This module provides ONNX-based prediction with optional tiling. It mirrors
the structure of StarDist's Keras/CSBDeep prediction flow but is specialized
for single-channel 2D (YX) and 3D (ZYX) inputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product

import numpy as np

from ..pre import pad_for_tiling, unpad_to_shape, validate_image


@dataclass(frozen=True)
class TilingSpec:
    """Tiling configuration for prediction.

    Attributes
    ----------
    tile_shape : tuple[int, ...]
        Tile size per spatial axis in input pixels.
    overlap : tuple[int, ...]
        Overlap per spatial axis in input pixels.
    """

    tile_shape: tuple[int, ...]
    overlap: tuple[int, ...]


def default_tiling_spec(
    shape: tuple[int, ...],
    tile_shape: tuple[int, ...] | None = None,
    overlap: tuple[int, ...] | None = None,
) -> TilingSpec:
    """Create a default tiling configuration for a given shape.

    Parameters
    ----------
    shape : tuple[int, ...]
        Spatial shape of the input image.
    tile_shape : tuple[int, ...] or None, optional
        Tile size per axis. Defaults to the full ``shape``.
    overlap : tuple[int, ...] or None, optional
        Overlap per axis in input pixels. Defaults to zero overlap.

    Returns
    -------
    TilingSpec
        Tiling specification with validated defaults.

    Raises
    ------
    ValueError
        If provided shapes do not match dimensionality.
    """
    if tile_shape is None:
        tile_shape = shape
    if overlap is None:
        overlap = (0,) * len(shape)
    if len(tile_shape) != len(shape):
        raise ValueError("tile_shape must match input dimensionality.")
    if len(overlap) != len(shape):
        raise ValueError("overlap must match input dimensionality.")
    return TilingSpec(tile_shape=tile_shape, overlap=overlap)


def predict_tiled(
    image: np.ndarray,
    session,
    *,
    input_name: str,
    output_names: list[str],
    grid: tuple[int, ...],
    input_layout: str,
    prob_layout: str,
    dist_layout: str,
    tile_shape: tuple[int, ...] | None = None,
    overlap: tuple[int, ...] | None = None,
    div_by: tuple[int, ...] | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Run ONNX prediction with optional tiling.

    Parameters
    ----------
    image : numpy.ndarray
        Input image array. Must be 2D (YX) or 3D (ZYX) and single-channel.
    session : object
        ONNX Runtime session instance.
    input_name : str
        Input tensor name for the ONNX model.
    output_names : list[str]
        Output tensor names for the ONNX model. The first is interpreted as
        probability, the second as distances.
    grid : tuple[int, ...]
        Subsampling grid of the model (e.g., (1, 1) or (2, 2, 2)).
    input_layout : str
        Input tensor layout. Supported values:
        - 2D: "NCHW" or "NHWC"
        - 3D: "NCDHW" or "NDHWC"
    prob_layout : str
        Probability output layout. Supported values:
        - 2D: "NCHW" or "NHWC"
        - 3D: "NCDHW" or "NDHWC"
    dist_layout : str
        Distance output layout. Supported values:
        - 2D: "NRYX" or "NYXR"
        - 3D: "NRZYX" or "NZYXR"
    tile_shape : tuple[int, ...] or None, optional
        Tile size per spatial axis in input pixels. If None, the full padded
        image is used.
    overlap : tuple[int, ...] or None, optional
        Overlap per spatial axis in input pixels. Defaults to zero.
        Padding is computed so each axis aligns with the tiling grid, i.e.,
        the padded size is ``tile_shape + k * (tile_shape - overlap)`` and
        divisible by the model grid/divisibility constraints.
    div_by : tuple[int, ...] or None, optional
        Additional per-axis divisibility constraint (e.g., from ONNX graph
        inspection). If provided, padding is also aligned to these multiples.

    Returns
    -------
    tuple[numpy.ndarray, numpy.ndarray]
        Probability map and distance map with padding removed and grid
        accounted for. The probability output has shape (Y, X) or (Z, Y, X),
        and the distance output has shape (Y, X, R) or (Z, Y, X, R).

    Raises
    ------
    ValueError
        If input dimensionality or layout parameters are invalid.
    RuntimeError
        If the ONNX model outputs do not include prob and dist outputs.
    """
    validate_image(image)
    if len(grid) != image.ndim:
        raise ValueError("Grid must match image dimensionality.")

    tiling = default_tiling_spec(
        image.shape, tile_shape=tile_shape, overlap=overlap
    )
    tile_shape = tiling.tile_shape
    overlap = tiling.overlap

    if div_by is None:
        div_by = grid
    if len(div_by) != image.ndim:
        raise ValueError("div_by must match image dimensionality.")

    padded, pads = pad_for_tiling(
        image, grid, tile_shape, overlap, div_by=div_by, mode="reflect"
    )

    tiles = _iter_tiles(padded.shape, tile_shape, overlap)
    prob_out = None
    dist_out = None

    for read_slice, crop_slice, write_slice in tiles:
        tile = padded[read_slice]
        prob_tile, dist_tile = _run_onnx(
            session,
            input_name,
            output_names,
            _prepare_input(tile, input_layout),
            prob_layout,
            dist_layout,
        )

        if prob_out is None:
            out_shape = tuple(s // g for s, g in zip(padded.shape, grid))
            prob_out = np.zeros(out_shape, dtype=np.float32)
            dist_out = np.zeros(out_shape + (dist_tile.shape[-1],), dtype=np.float32)

        prob_write, crop_write = _tile_write_slices(
            crop_slice, write_slice, grid
        )
        prob_out[prob_write] = prob_tile[crop_write]
        dist_out[prob_write + (slice(None),)] = dist_tile[crop_write + (slice(None),)]

    prob_out = unpad_to_shape(prob_out, pads, scale=grid)
    dist_out = unpad_to_shape(dist_out, pads, scale=grid)
    return prob_out, dist_out


def _run_onnx(
    session,
    input_name: str,
    output_names: list[str],
    input_tensor: np.ndarray,
    prob_layout: str,
    dist_layout: str,
) -> tuple[np.ndarray, np.ndarray]:
    """Run the ONNX session and parse prob/dist outputs.

    Parameters
    ----------
    session : object
        ONNX Runtime session instance.
    input_name : str
        Input tensor name.
    output_names : list[str]
        Output tensor names (prob, dist).
    input_tensor : numpy.ndarray
        Input tensor ready for ONNX execution.
    prob_layout : str
        Layout of the prob output.
    dist_layout : str
        Layout of the dist output.

    Returns
    -------
    tuple[numpy.ndarray, numpy.ndarray]
        Probability map and distance map in image layout.
    """
    outputs = session.run(output_names, {input_name: input_tensor})
    if len(outputs) < 2:
        raise RuntimeError("ONNX model must return prob and dist outputs.")
    prob = _parse_prob(outputs[0], prob_layout, input_tensor.ndim - 2)
    dist = _parse_dist(outputs[1], dist_layout, input_tensor.ndim - 2)
    return prob, dist


def _prepare_input(image: np.ndarray, layout: str) -> np.ndarray:
    """Prepare a single-channel image for ONNX input.

    Parameters
    ----------
    image : numpy.ndarray
        Input image array (2D or 3D).
    layout : str
        Desired input layout (NCHW/NHWC or NCDHW/NDHWC).

    Returns
    -------
    numpy.ndarray
        Batched input tensor with explicit channel axis.
    """
    if image.ndim == 2:
        if layout == "NCHW":
            return image[np.newaxis, np.newaxis, ...]
        if layout == "NHWC":
            return image[np.newaxis, ..., np.newaxis]
    if image.ndim == 3:
        if layout == "NCDHW":
            return image[np.newaxis, np.newaxis, ...]
        if layout == "NDHWC":
            return image[np.newaxis, ..., np.newaxis]
    raise ValueError(f"Unsupported input layout {layout} for ndim={image.ndim}.")


def _parse_prob(prob: np.ndarray, layout: str, ndim: int) -> np.ndarray:
    """Parse probability output into image layout.

    Parameters
    ----------
    prob : numpy.ndarray
        Raw probability output from ONNX.
    layout : str
        Layout of the prob output tensor.
    ndim : int
        Spatial dimensionality (2 or 3).

    Returns
    -------
    numpy.ndarray
        Probability map in spatial layout.
    """
    if ndim == 2:
        if layout == "NCHW":
            return prob[0, 0]
        if layout == "NHWC":
            return prob[0, ..., 0]
    if ndim == 3:
        if layout == "NCDHW":
            return prob[0, 0]
        if layout == "NDHWC":
            return prob[0, ..., 0]
    raise ValueError(f"Unsupported prob layout {layout} for ndim={ndim}.")


def _parse_dist(dist: np.ndarray, layout: str, ndim: int) -> np.ndarray:
    """Parse distance output into image layout.

    Parameters
    ----------
    dist : numpy.ndarray
        Raw distance output from ONNX.
    layout : str
        Layout of the dist output tensor.
    ndim : int
        Spatial dimensionality (2 or 3).

    Returns
    -------
    numpy.ndarray
        Distance map with rays as the last axis.
    """
    if ndim == 2:
        if layout == "NRYX":
            return dist[0].transpose(1, 2, 0)
        if layout == "NYXR":
            return dist[0]
    if ndim == 3:
        if layout == "NRZYX":
            return dist[0].transpose(1, 2, 3, 0)
        if layout == "NZYXR":
            return dist[0]
    raise ValueError(f"Unsupported dist layout {layout} for ndim={ndim}.")


def _iter_tiles(shape: tuple[int, ...], tile_shape: tuple[int, ...], overlap: tuple[int, ...]):
    """Yield read/crop/write slices for tiled prediction.

    Parameters
    ----------
    shape : tuple[int, ...]
        Shape of the padded input image.
    tile_shape : tuple[int, ...]
        Spatial size of each tile.
    overlap : tuple[int, ...]
        Overlap per axis in input pixels.

    Yields
    ------
    tuple[tuple[slice, ...], tuple[slice, ...], tuple[slice, ...]]
        Read slices, crop slices, and write slices per tile.
    """
    tile_ranges = []
    # Build per-axis start positions and overlap metadata.
    for dim, size, ov in zip(shape, tile_shape, overlap):
        if size <= 0:
            raise ValueError("tile_shape entries must be positive.")
        if ov >= size:
            raise ValueError("overlap must be smaller than tile size.")
        # Step is the non-overlapping stride between consecutive tiles.
        step = size - ov
        max_start = max(0, dim - size)
        starts = list(range(0, max_start + 1, step))
        if not starts:
            starts = [0]
        # Ensure the last tile reaches the end even if step doesn't align.
        if starts[-1] != max_start:
            starts.append(max_start)
        tile_ranges.append((starts, size, ov))

    # Iterate all coordinate combinations across axes.
    for starts in product(*[r[0] for r in tile_ranges]):
        read_slices = []
        crop_slices = []
        write_slices = []
        # Compute read/crop/write slices for each axis.
        for axis, (start, (_, size, ov)) in enumerate(zip(starts, tile_ranges)):
            end = min(start + size, shape[axis])
            # Read the full tile region from the padded input.
            read_slices.append(slice(start, end))

            ov_before = ov // 2
            ov_after = ov - ov_before
            # Crop overlap from interior tiles, keep full extent at borders.
            crop_start = 0 if start == 0 else ov_before
            crop_end = (end - start) if end == shape[axis] else (end - start - ov_after)
            crop_slices.append(slice(crop_start, crop_end))
            # Write the cropped region back into the global output frame.
            write_slices.append(slice(start + crop_start, start + crop_end))

        yield tuple(read_slices), tuple(crop_slices), tuple(write_slices)


def _tile_write_slices(
    crop_slice: tuple[slice, ...],
    write_slice: tuple[slice, ...],
    grid: tuple[int, ...],
) -> tuple[tuple[slice, ...], tuple[slice, ...]]:
    """Compute output-write and crop slices for prob/dist outputs.

    Parameters
    ----------
    crop_slice : tuple[slice, ...]
        Crop slices applied to the tile predictions.
    write_slice : tuple[slice, ...]
        Write slices in input pixel coordinates.
    grid : tuple[int, ...]
        Subsampling grid for the model outputs.

    Returns
    -------
    tuple[tuple[slice, ...], tuple[slice, ...]]
        Output write slices (in output coordinates) and crop slices
        (in tile output coordinates).
    """
    prob_write = []
    crop_write = []
    for crop, write, g in zip(crop_slice, write_slice, grid):
        prob_write.append(slice(write.start // g, write.stop // g))
        crop_write.append(slice(crop.start // g, crop.stop // g))
    prob_write = tuple(prob_write)
    crop_write = tuple(crop_write)
    return prob_write, crop_write
