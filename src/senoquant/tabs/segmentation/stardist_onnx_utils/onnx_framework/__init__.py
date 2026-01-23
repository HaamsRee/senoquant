"""ONNX tiling and prediction framework for StarDist."""

__all__ = [
    "normalize",
    "pad_for_tiling",
    "pad_to_multiple",
    "unpad_to_shape",
    "TilingSpec",
    "default_tiling_spec",
    "predict_tiled",
    "instances_from_prediction_2d",
    "instances_from_prediction_3d",
    "DEFAULT_2D_MODEL",
    "DEFAULT_3D_MODEL",
    "convert_model_to_onnx",
    "convert_pretrained_2d",
    "convert_pretrained_3d",
    "infer_div_by",
    "summarize_model_io",
]


def __getattr__(name):
    if name in {"normalize", "pad_for_tiling", "pad_to_multiple", "unpad_to_shape"}:
        from . import pre as _pre
        return getattr(_pre, name)
    if name in {"TilingSpec", "default_tiling_spec", "predict_tiled"}:
        from . import predict as _predict
        return getattr(_predict, name)
    if name in {"instances_from_prediction_2d", "instances_from_prediction_3d"}:
        from . import post as _post
        return getattr(_post, name)
    if name in {
        "DEFAULT_2D_MODEL",
        "DEFAULT_3D_MODEL",
        "convert_model_to_onnx",
        "convert_pretrained_2d",
        "convert_pretrained_3d",
    }:
        from . import convert as _convert
        return getattr(_convert, name)
    if name in {"infer_div_by", "summarize_model_io"}:
        from . import inspect as _inspect
        return getattr(_inspect, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
