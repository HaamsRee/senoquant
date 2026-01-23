"""Convert StarDist Keras models to ONNX."""

from __future__ import annotations

from pathlib import Path
import re
import sys
import types
import importlib
import tempfile


DEFAULT_2D_MODEL = "2D_versatile_fluo"
DEFAULT_3D_MODEL = "3D_demo"


def convert_pretrained_2d(
    model_name: str = DEFAULT_2D_MODEL,
    output: str | Path = ".",
    *,
    opset: int = 18,
) -> Path:
    """Convert a pretrained StarDist2D model to ONNX.

    Parameters
    ----------
    model_name : str, optional
        Pretrained model name or alias. Defaults to ``2D_versatile_fluo``.
    output : str or pathlib.Path, optional
        Output directory or ONNX file path. Defaults to the current directory.
    opset : int, optional
        ONNX opset version to export. Defaults to 13.

    Returns
    -------
    pathlib.Path
        Path to the saved ONNX model.
    """
    model = _load_stardist_model(2, model_name)
    output_path = _resolve_output_path(output, f"stardist2d_{_safe_name(model_name)}.onnx")
    return convert_model_to_onnx(model, output_path, opset=opset)


def convert_pretrained_3d(
    model_name: str = DEFAULT_3D_MODEL,
    output: str | Path = ".",
    *,
    opset: int = 18,
) -> Path:
    """Convert a pretrained StarDist3D model to ONNX.

    Parameters
    ----------
    model_name : str, optional
        Pretrained model name or alias. Defaults to ``3D_demo``.
    output : str or pathlib.Path, optional
        Output directory or ONNX file path. Defaults to the current directory.
    opset : int, optional
        ONNX opset version to export. Defaults to 13.

    Returns
    -------
    pathlib.Path
        Path to the saved ONNX model.
    """
    model = _load_stardist_model(3, model_name)
    output_path = _resolve_output_path(output, f"stardist3d_{_safe_name(model_name)}.onnx")
    return convert_model_to_onnx(model, output_path, opset=opset)


def convert_model_to_onnx(model, output_path: str | Path, *, opset: int = 18) -> Path:
    """Convert a StarDist model instance to ONNX.

    Parameters
    ----------
    model : object
        StarDist2D or StarDist3D instance with a ``keras_model`` attribute.
    output_path : str or pathlib.Path
        File path to save the ONNX model.
    opset : int, optional
        ONNX opset version to export. Defaults to 13.

    Returns
    -------
    pathlib.Path
        Path to the saved ONNX model.
    """
    tf = _import_tensorflow()
    tf2onnx = _import_tf2onnx()

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    keras_model = model.keras_model
    keras_model.trainable = False

    input_tensor = keras_model.inputs[0]
    input_name = input_tensor.name.split(":")[0]
    input_shape = list(input_tensor.shape)
    if input_shape and input_shape[0] is None:
        input_shape[0] = 1
    input_signature = (tf.TensorSpec(tuple(input_shape), input_tensor.dtype, name=input_name),)
    try:
        _convert_via_saved_model(tf2onnx, keras_model, input_signature, opset, output_path)
    except Exception:
        try:
            output_names = [out.name.split(":")[0] for out in keras_model.outputs]
            tf2onnx.convert.from_keras(
                keras_model,
                input_signature=input_signature,
                opset=opset,
                output_path=str(output_path),
                output_names=output_names,
            )
        except TypeError:
            try:
                tf2onnx.convert.from_keras(
                    keras_model,
                    input_signature=input_signature,
                    opset=opset,
                    output_path=str(output_path),
                )
            except ValueError as exc:
                if "explicit_paddings" not in str(exc):
                    raise
                _convert_via_frozen_graph(
                    tf2onnx, tf, keras_model, input_signature, opset, output_path
                )
    return output_path


def _load_stardist_model(ndim: int, name_or_path: str):
    _ensure_csbdeep_on_path()
    _ensure_stardist_stub()
    if ndim == 2:
        module = importlib.import_module(
            "senoquant.tabs.segmentation.stardist_onnx_utils._stardist.models"
        )
        model_cls = module.StarDist2D
    elif ndim == 3:
        module = importlib.import_module(
            "senoquant.tabs.segmentation.stardist_onnx_utils._stardist.models"
        )
        model_cls = module.StarDist3D
    else:
        raise ValueError("ndim must be 2 or 3.")

    model_path = Path(name_or_path)
    if model_path.is_dir():
        return model_cls(None, name=model_path.name, basedir=str(model_path.parent))
    model = model_cls.from_pretrained(name_or_path)
    if model is None:
        raise ValueError(f"Unknown pretrained model: {name_or_path}")
    return model


def _resolve_output_path(output: str | Path, default_name: str) -> Path:
    output_path = Path(output)
    if output_path.suffix.lower() != ".onnx":
        output_path = output_path / default_name
    return output_path


def _safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_")


def _ensure_csbdeep_on_path() -> None:
    root = Path(__file__).resolve().parents[2]
    csbdeep_root = root / "_csbdeep"
    if csbdeep_root.exists():
        csbdeep_path = str(csbdeep_root)
        if csbdeep_path not in sys.path:
            sys.path.insert(0, csbdeep_path)


def _ensure_stardist_stub() -> None:
    base_pkg = "senoquant.tabs.segmentation.stardist_onnx_utils._stardist"
    root = Path(__file__).resolve().parents[2] / "_stardist"
    if base_pkg not in sys.modules:
        pkg = types.ModuleType(base_pkg)
        pkg.__path__ = [str(root)]
        sys.modules[base_pkg] = pkg
    geom_name = f"{base_pkg}.geometry"
    if geom_name not in sys.modules:
        geom = types.ModuleType(geom_name)

        def _stub(*_args, **_kwargs):
            raise RuntimeError("StarDist geometry helpers are unavailable in converter.")

        geom.star_dist = _stub
        geom.dist_to_coord = _stub
        geom.polygons_to_label = _stub
        geom.star_dist3D = _stub
        geom.polyhedron_to_label = _stub
        sys.modules[geom_name] = geom


def _import_tensorflow():
    try:
        import tensorflow as tf
    except ImportError as exc:
        raise RuntimeError("TensorFlow is required to export StarDist models.") from exc
    return tf


def _import_tf2onnx():
    try:
        import numpy as np
        # tf2onnx still references deprecated numpy aliases in some versions.
        for alias, value in {
            "bool": np.bool_,
            "object": np.object_,
        }.items():
            if not hasattr(np, alias):
                setattr(np, alias, value)
        import tf2onnx
    except ImportError as exc:
        raise RuntimeError("tf2onnx is required to export StarDist models.") from exc
    return tf2onnx


def _convert_via_frozen_graph(tf2onnx, tf, keras_model, input_signature, opset, output_path):
    @tf.function
    def _model_fn(*args):
        return keras_model(*args, training=False)

    concrete = _model_fn.get_concrete_function(*input_signature)

    try:
        from tensorflow.python.framework.convert_to_constants import (
            convert_variables_to_constants_v2,
        )
    except ImportError as exc:
        raise RuntimeError("TensorFlow constants converter is unavailable.") from exc

    frozen_func = convert_variables_to_constants_v2(concrete)
    graph_def = frozen_func.graph.as_graph_def()
    inputs = [tensor.name for tensor in frozen_func.inputs]
    outputs = [tensor.name for tensor in frozen_func.outputs]

    _strip_empty_explicit_paddings(graph_def)

    try:
        tf2onnx.convert.from_graph_def(
            graph_def,
            input_names=inputs,
            output_names=outputs,
            opset=opset,
            output_path=str(output_path),
        )
    except TypeError:
        tf2onnx.convert.from_graph_def(
            graph_def,
            inputs,
            outputs,
            opset=opset,
            output_path=str(output_path),
        )


def _convert_via_saved_model(tf2onnx, keras_model, input_signature, opset, output_path):
    if not hasattr(keras_model, "export"):
        raise RuntimeError("Keras model does not support export().")
    export_dir = Path(tempfile.mkdtemp(prefix="stardist_saved_model_"))
    keras_model.export(
        str(export_dir),
        format="tf_saved_model",
        input_signature=input_signature,
    )
    if hasattr(tf2onnx.convert, "from_saved_model"):
        tf2onnx.convert.from_saved_model(
            str(export_dir),
            output_path=str(output_path),
            opset=opset,
        )
    else:
        raise RuntimeError("tf2onnx does not support from_saved_model.")


def _strip_empty_explicit_paddings(graph_def):
    for node in graph_def.node:
        attr = node.attr.get("explicit_paddings")
        if attr is not None and len(attr.list.i) == 0:
            del node.attr["explicit_paddings"]
