"""StarDist ONNX wrapper that reuses upstream StarDist prediction code."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from senoquant.utils import layer_data_asarray
from ..base import SenoQuantSegmentationModel
from ._stardist.models import StarDist2D, StarDist3D


class StarDistOnnxModel(SenoQuantSegmentationModel):
    """StarDist ONNX model wrapper using upstream StarDist tiling/postprocess."""

    def __init__(self, models_root=None) -> None:
        super().__init__("stardist_onnx", models_root=models_root)
        self._sessions: dict[Path, object] = {}
        self._models: dict[int, object] = {}

    def run(self, **kwargs) -> dict:
        task = kwargs.get("task")
        if task != "nuclear":
            raise ValueError("StarDist ONNX currently supports only nuclear mode.")

        layer = kwargs.get("layer")
        image = self._extract_layer_data(layer)
        settings = kwargs.get("settings", {})

        prob_thresh = float(settings.get("prob_thresh", 0.5))
        nms_thresh = float(settings.get("nms_thresh", 0.4))
        n_tiles = int(settings.get("n_tiles", 1))
        n_tiles_tuple = None if n_tiles <= 1 else (n_tiles,) * image.ndim

        stardist_model = self._get_stardist_model(image.ndim)
        onnx_path = self._resolve_onnx_path(image.ndim)
        self._attach_onnx_predictor(stardist_model, onnx_path)

        labels, metadata = stardist_model.predict_instances(
            image,
            n_tiles=n_tiles_tuple,
            prob_thresh=prob_thresh,
            nms_thresh=nms_thresh,
            normalizer=None,
        )

        return {"masks": labels, "metadata": metadata}

    def _extract_layer_data(self, layer) -> np.ndarray:
        if layer is None:
            raise ValueError("Layer is required for StarDist ONNX.")
        return layer_data_asarray(layer)

    def _resolve_onnx_path(self, ndim: int) -> Path:
        if ndim == 2:
            candidate = self.model_dir / "model_2d.onnx"
        elif ndim == 3:
            candidate = self.model_dir / "model_3d.onnx"
        else:
            raise ValueError("StarDist ONNX supports only 2D or 3D images.")
        return candidate if candidate.exists() else (self.model_dir / "model.onnx")

    def _get_stardist_model(self, ndim: int):
        cached = self._models.get(ndim)
        if cached is not None:
            return cached

        config_path = self.model_dir / "config.json"
        if not config_path.exists():
            raise FileNotFoundError(
                f"Missing StarDist config at {config_path}."
            )

        if ndim == 2:
            model = StarDist2D(
                config=None,
                name=self.model_dir.name,
                basedir=str(self.model_dir.parent),
            )
        elif ndim == 3:
            model = StarDist3D(
                config=None,
                name=self.model_dir.name,
                basedir=str(self.model_dir.parent),
            )
        else:
            raise ValueError("StarDist ONNX supports only 2D or 3D images.")

        self._models[ndim] = model
        return model

    def _attach_onnx_predictor(self, model, onnx_path: Path) -> None:
        session = self._get_session(onnx_path)
        input_name = session.get_inputs()[0].name
        output_names = [out.name for out in session.get_outputs()]

        expected_outputs = 3 if model.config.n_classes is not None else 2
        if len(output_names) < expected_outputs:
            raise RuntimeError(
                f"ONNX model must provide {expected_outputs} outputs."
            )
        output_names = output_names[:expected_outputs]

        model.keras_model = _OnnxPredictor(session, input_name, output_names)

    def _get_session(self, onnx_path: Path):
        if not onnx_path.exists():
            raise FileNotFoundError(f"Missing ONNX model at {onnx_path}.")
        session = self._sessions.get(onnx_path)
        if session is None:
            try:
                import onnxruntime as ort
            except ImportError as exc:
                raise RuntimeError(
                    "onnxruntime is required to run StarDist ONNX."
                ) from exc
            session = ort.InferenceSession(
                str(onnx_path),
                providers=["CPUExecutionProvider"],
            )
            self._sessions[onnx_path] = session
        return session


class _OnnxPredictor:
    """Proxy that mimics Keras model predict using ONNX Runtime."""

    def __init__(self, session, input_name: str, output_names: list[str]) -> None:
        self._session = session
        self._input_name = input_name
        self._output_names = output_names

    def predict(self, batch, **_kwargs):
        outputs = self._session.run(
            self._output_names, {self._input_name: batch}
        )
        return outputs
