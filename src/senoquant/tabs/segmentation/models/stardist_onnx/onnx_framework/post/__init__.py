"""Post-processing utilities for ONNX StarDist inference."""

from .core import instances_from_prediction_2d, instances_from_prediction_3d

__all__ = [
    "instances_from_prediction_2d",
    "instances_from_prediction_3d",
]
