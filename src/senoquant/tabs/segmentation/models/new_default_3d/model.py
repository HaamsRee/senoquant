"""TitanCell 3D segmentation model implementation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from senoquant.utils import layer_data_asarray
from ..base import SenoQuantSegmentationModel
from .config import PipelineConfig
from .inference import InferenceEngine
from .postprocess import InstanceEngine


class TitanCellModel(SenoQuantSegmentationModel):
    """TitanCell 3D segmentation model wrapper."""

    _SUPPORTED_TASKS = {"nuclear"}

    def __init__(self, models_root=None) -> None:
        super().__init__("new_default_3d", models_root=models_root)

        model_path = Path(__file__).parent / "best_model_v18.pth"
        if not model_path.exists():
            raise FileNotFoundError(
                f"TitanCell model weights not found at {model_path}. "
                "Place best_model_v18.pth in the same directory as this file."
            )

        self._model_path = str(model_path)
        self._inference: InferenceEngine | None = None
        self._instance: InstanceEngine | None = None

    def supports_task(self, task: str) -> bool:
        return task in self._SUPPORTED_TASKS

    def display_order(self) -> float | None:
        return 10.0

    def run(self, **kwargs) -> dict[str, Any]:
        layer = kwargs.get("layer")
        settings = kwargs.get("settings", {})

        image = self._extract_layer_data(layer)
        config = self._build_config(settings)
        self._ensure_loaded(config)

        raw_outputs = self._inference.predict(image)
        seg_result = self._instance.process(raw_outputs)

        return {
            "masks": seg_result["instances"],
            "instances": seg_result["instances"],
            "mask": seg_result["mask"],
            "cell_info": seg_result["cell_info"],
            "statistics": seg_result["statistics"],
            "outputs": raw_outputs,
            "quality_map": seg_result.get("quality_map"),
            "intermediates": seg_result.get("intermediates", {}),
        }

    @staticmethod
    def get_derived_params(cell_diameter_px: float) -> dict[str, Any]:
        """Return the internally derived settings for a given diameter."""
        return PipelineConfig.derive_defaults(cell_diameter_px)

    def _extract_layer_data(self, layer) -> np.ndarray:
        if layer is None:
            raise ValueError("A valid image layer is required for TitanCell.")

        data = layer_data_asarray(layer)
        if data.ndim == 2:
            data = data[np.newaxis]
        if data.ndim != 3:
            raise ValueError(f"TitanCell expects a 3-D volume, got shape {data.shape}.")

        return data.astype(np.float32)

    def _build_config(self, settings: dict[str, Any]) -> PipelineConfig:
        """Build PipelineConfig from the reduced UI surface."""
        kwargs: dict[str, Any] = {"model_path": self._model_path}

        diameter = settings.get("cell_diameter_px")
        if diameter is None or diameter <= 0:
            kwargs["cell_diameter_px"] = None
        else:
            kwargs["cell_diameter_px"] = float(diameter)

        for field_name in ("mask_threshold", "high_mask_threshold", "min_high_mask_fraction"):
            if field_name in settings:
                kwargs[field_name] = settings[field_name]

        return PipelineConfig(**kwargs)

    def _ensure_loaded(self, config: PipelineConfig) -> None:
        if self._inference is None:
            self._inference = InferenceEngine(config)
        else:
            self._inference.cfg = config

        self._instance = InstanceEngine(config)
