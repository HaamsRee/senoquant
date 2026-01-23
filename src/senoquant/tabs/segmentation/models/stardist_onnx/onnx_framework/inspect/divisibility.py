"""Infer input divisibility constraints from an ONNX graph.

This module inspects ONNX graphs to infer the minimal spatial divisibility
required to run the model without shape mismatches through down/upsampling
paths (e.g., U-Net skip connections).
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable


def infer_div_by(model_path: str | Path, ndim: int | None = None) -> tuple[int, ...]:
    """Infer the spatial divisibility required by an ONNX model.

    This inspects the graph to estimate the cumulative downsampling factor
    along spatial axes. The result is the minimal per-axis multiple that the
    model input should be divisible by to avoid internal shape mismatches
    (e.g., concatenation of encoder/decoder feature maps).

    Parameters
    ----------
    model_path : str or pathlib.Path
        Path to the ONNX model file.
    ndim : int or None, optional
        Number of spatial dimensions (2 or 3). If ``None``, the input rank is
        used to infer dimensionality (rank 4 -> 2D, rank 5 -> 3D).

    Returns
    -------
    tuple[int, ...]
        Per-axis divisibility requirement (e.g., ``(16, 16)`` or
        ``(8, 8, 8)``).

    Notes
    -----
    - The algorithm tracks cumulative scaling factors by propagating
      per-axis scale values through the graph.
    - Downsampling ops (Conv/Pool with stride > 1) increase the scale.
    - Upsampling ops (ConvTranspose/Resize) reduce the scale.
    - The maximum scale observed across the graph is returned.
    """
    # Load the ONNX graph and find the primary input tensor.
    model = _load_onnx(model_path)
    input_name = model.graph.input[0].name if model.graph.input else None
    if input_name is None:
        raise ValueError("ONNX model has no graph inputs.")

    # Determine the number of spatial dimensions if not specified.
    if ndim is None:
        ndim = _infer_ndim(model)

    # Collect initializer tensors so we can read Resize scales, etc.
    init_map = _initializers(model)

    # Map tensor name -> per-axis scale relative to the original input.
    scale_map: dict[str, list[float]] = {input_name: [1.0] * ndim}
    # Track the maximum cumulative downsample per axis across the graph.
    max_scale = [1.0] * ndim

    for node in model.graph.node:
        # Resolve the input scales for this node if we have them.
        input_scales = [scale_map[name] for name in node.input if name in scale_map]
        # Merge multiple inputs by taking the maximum scale per axis.
        base = (
            [max(values) for values in zip(*input_scales)]
            if input_scales
            else [1.0] * ndim
        )
        # Default: node does not change spatial scale.
        factor = [1.0] * ndim

        # Downsampling: increase scale by stride.
        if node.op_type in ("Conv", "MaxPool", "AveragePool"):
            strides = _get_attr_ints(node, "strides")
            if strides:
                factor = [float(s) for s in strides[-ndim:]]
        # Upsampling: reduce scale by stride.
        elif node.op_type == "ConvTranspose":
            strides = _get_attr_ints(node, "strides")
            if strides:
                factor = [1.0 / float(s) if s else 1.0 for s in strides[-ndim:]]
        # Resize/Upsample may carry explicit scales as initializers.
        elif node.op_type in ("Resize", "Upsample"):
            scales = _get_resize_scales(node, init_map)
            if scales is not None and len(scales) >= ndim:
                spatial = scales[-ndim:]
                factor = [
                    1.0 / float(s) if float(s) not in (0.0, 1.0) else 1.0
                    for s in spatial
                ]

        # Propagate the updated scale to all outputs of this node.
        out_scale = [b * f for b, f in zip(base, factor)]
        for output in node.output:
            scale_map[output] = out_scale
        # Record the maximum scale seen so far.
        max_scale = [max(m, s) for m, s in zip(max_scale, out_scale)]

    # Convert to integer divisibility requirements.
    return tuple(int(round(s)) if s >= 1 else 1 for s in max_scale)


def summarize_model_io(model_path: str | Path) -> dict[str, list[list[str]]]:
    """Return a simple summary of model input/output shapes.

    Parameters
    ----------
    model_path : str or pathlib.Path
        Path to the ONNX model file.

    Returns
    -------
    dict
        Dictionary with ``inputs`` and ``outputs`` lists. Each entry is a
        list of dimension labels (e.g., ``"1"``, ``"H (dynamic)"``).
    """
    # Load the graph and format the shapes for user-friendly display.
    model = _load_onnx(model_path)
    inputs = [_format_shape(inp.type.tensor_type.shape) for inp in model.graph.input]
    outputs = [_format_shape(out.type.tensor_type.shape) for out in model.graph.output]
    return {"inputs": inputs, "outputs": outputs}


def _load_onnx(model_path: str | Path):
    """Load an ONNX model, raising a helpful error if onnx is missing."""
    try:
        import onnx
    except Exception as exc:
        # Keep error explicit so users know to install the dependency.
        raise RuntimeError("onnx is required for model inspection.") from exc
    return onnx.load(str(model_path))


def _initializers(model) -> dict[str, Iterable[float]]:
    """Materialize ONNX initializers into a name -> numpy array map."""
    from onnx import numpy_helper

    return {
        init.name: numpy_helper.to_array(init)
        for init in model.graph.initializer
    }


def _infer_ndim(model) -> int:
    """Infer the spatial dimensionality from the model input rank."""
    if not model.graph.input:
        raise ValueError("ONNX model has no graph inputs.")
    shape = model.graph.input[0].type.tensor_type.shape
    rank = len(shape.dim)
    if rank == 4:
        return 2
    if rank == 5:
        return 3
    raise ValueError(f"Unsupported input rank {rank}; pass ndim explicitly.")


def _get_attr_ints(node, name: str) -> list[int] | None:
    """Extract INT/INTS attributes from a node."""
    for attr in node.attribute:
        if attr.name == name:
            if attr.type == attr.INTS:
                return list(attr.ints)
            if attr.type == attr.INT:
                return [attr.i]
    return None


def _get_resize_scales(node, init_map: dict[str, Iterable[float]]):
    """Return resize scales from initializer inputs or node attributes."""
    # Newer ONNX Resize uses a scales tensor input.
    for input_name in reversed(node.input):
        if input_name in init_map:
            return init_map[input_name]
    # Older Resize/Upsample variants may store scales as attributes.
    for attr in node.attribute:
        if attr.name == "scales" and attr.type == attr.FLOATS:
            return list(attr.floats)
    return None


def _format_shape(shape) -> list[str]:
    """Format an ONNX TensorShapeProto into a list of human-readable dims."""
    dims: list[str] = []
    for dim in shape.dim:
        if dim.dim_param:
            dims.append(f"{dim.dim_param} (dynamic)")
        elif dim.dim_value:
            dims.append(str(dim.dim_value))
        else:
            dims.append("? (dynamic)")
    return dims
