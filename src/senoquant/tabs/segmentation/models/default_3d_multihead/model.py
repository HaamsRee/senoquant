"""Multi-head PyTorch 3D segmentation model implementation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from senoquant.tabs.segmentation.models.base import SenoQuantSegmentationModel
from senoquant.tabs.segmentation.models.default_3d_multihead.config import (
    PipelineConfig,
)
from senoquant.tabs.segmentation.models.default_3d_multihead.inference import (
    InferenceEngine,
)
from senoquant.tabs.segmentation.models.default_3d_multihead.postprocess import (
    InstanceEngine,
)
from senoquant.tabs.segmentation.models.hf import DEFAULT_REPO_ID, ensure_hf_model
from senoquant.utils import layer_data_asarray


class MultiHead3DModel(SenoQuantSegmentationModel):
    """Multi-head PyTorch 3D segmentation model wrapper."""

    def __init__(self, models_root=None) -> None:
        super().__init__("default_3d_multihead", models_root=models_root)

        model_path = Path(self.model_dir) / "best_model_v18.pth"
        self._model_path = str(model_path)
        self._inference: InferenceEngine | None = None
        self._instance: InstanceEngine | None = None

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
    def get_derived_params(object_diameter_px: float) -> dict[str, Any]:
        """Return the internally derived settings for a given diameter."""
        return PipelineConfig.derive_defaults(object_diameter_px)

    def _extract_layer_data(self, layer) -> np.ndarray:
        if layer is None:
            raise ValueError("A valid image layer is required for the multi-head model.")

        data = layer_data_asarray(layer)
        if data.ndim == 2:
            data = data[np.newaxis]
        if data.ndim != 3:
            raise ValueError(
                f"The multi-head model expects a 3-D volume, got shape {data.shape}."
            )

        return data.astype(np.float32)

    def _build_config(self, settings: dict[str, Any]) -> PipelineConfig:
        """Build PipelineConfig from the reduced UI surface."""
        return PipelineConfig(
            model_path=self._model_path,
            object_diameter_px=float(settings["object_diameter_px"]),
            mask_threshold=float(settings["mask_threshold"]),
            high_mask_threshold=float(settings["high_mask_threshold"]),
            min_high_mask_fraction=float(settings["min_high_mask_fraction"]),
        )

    def _ensure_loaded(self, config: PipelineConfig) -> None:
        if self._inference is None:
            model_path = Path(self._model_path)
            if not model_path.exists():
                model_path = ensure_hf_model(
                    "best_model_v18.pth",
                    self.model_dir,
                    repo_id=DEFAULT_REPO_ID,
                )
                self._model_path = str(model_path)
                config.model_path = self._model_path
            self._inference = InferenceEngine(config)
        else:
            self._inference.cfg = config

        self._instance = InstanceEngine(config)
