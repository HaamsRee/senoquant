"""StarDist ONNX model skeleton."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

import numpy as np

from senoquant.utils import layer_data_asarray
from ..base import SenoQuantSegmentationModel
from .processing import (
    add_axes,
    drop_axes,
    infer_image_axes,
    normalize_percentile,
    squeeze_batch,
)
from .postprocess import instances_from_prediction_2d, instances_from_prediction_3d


@dataclass(frozen=True)
class StarDistOnnxConfig:
    """Configuration needed to run StarDist ONNX inference."""

    axes: str
    input_axes: str
    prob_axes: str
    dist_axes: str
    n_rays: int
    grid: tuple[int, ...]
    input_name: str | None = None
    prob_output: str | None = None
    dist_output: str | None = None

    @classmethod
    def default_for_ndim(cls, ndim: int) -> "StarDistOnnxConfig":
        if ndim == 2:
            return cls(
                axes="YX",
                input_axes="CYX",
                prob_axes="CYX",
                dist_axes="RYX",
                n_rays=32,
                grid=(1, 1),
            )
        if ndim == 3:
            return cls(
                axes="ZYX",
                input_axes="CZYX",
                prob_axes="CZYX",
                dist_axes="RZYX",
                n_rays=64,
                grid=(1, 1, 1),
            )
        raise ValueError("StarDist ONNX supports only 2D or 3D models.")

    @classmethod
    def from_json(cls, path: Path, ndim: int) -> "StarDistOnnxConfig":
        defaults = cls.default_for_ndim(ndim)
        if not path.exists():
            return defaults
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        grid = data.get("grid", defaults.grid)
        return cls(
            axes=str(data.get("axes", defaults.axes)),
            input_axes=str(data.get("input_axes", defaults.input_axes)),
            prob_axes=str(data.get("prob_axes", defaults.prob_axes)),
            dist_axes=str(data.get("dist_axes", defaults.dist_axes)),
            n_rays=int(data.get("n_rays", defaults.n_rays)),
            grid=tuple(grid),
            input_name=data.get("input_name"),
            prob_output=data.get("prob_output"),
            dist_output=data.get("dist_output"),
        )


class StarDistOnnxModel(SenoQuantSegmentationModel):
    """StarDist ONNX model implementation."""

    def __init__(self, models_root=None) -> None:
        super().__init__("stardist_onnx", models_root=models_root)
        self._session = None
        self._session_path: Path | None = None

    def run(self, **kwargs) -> dict:
        """Run StarDist ONNX inference and post-processing."""
        task = kwargs.get("task")
        if task != "nuclear":
            raise ValueError("StarDist ONNX currently supports only nuclear mode.")

        layer = kwargs.get("layer")
        image = self._extract_layer_data(layer)
        onnx_path, config_path = self._resolve_paths(image.ndim)
        config = self._load_config(image, config_path)
        settings = kwargs.get("settings", {})

        normalize = bool(settings.get("normalize", True))
        pmin = float(settings.get("pmin", 1.0))
        pmax = float(settings.get("pmax", 99.8))
        prob_thresh = float(settings.get("prob_thresh", 0.5))
        nms_thresh = float(settings.get("nms_thresh", 0.4))

        image = image.astype(np.float32, copy=False)
        if normalize:
            image = normalize_percentile(image, pmin=pmin, pmax=pmax)

        input_tensor = self._prepare_input(image, config)
        prob, dist = self._run_onnx(input_tensor, config, onnx_path)
        prob, dist = self._format_outputs(prob, dist, config)

        if image.ndim == 2:
            labels, metadata = instances_from_prediction_2d(
                prob,
                dist,
                image_shape=image.shape,
                grid=config.grid,
                prob_thresh=prob_thresh,
                nms_thresh=nms_thresh,
            )
        else:
            labels, metadata = instances_from_prediction_3d(
                prob,
                dist,
                image_shape=image.shape,
                grid=config.grid,
                prob_thresh=prob_thresh,
                nms_thresh=nms_thresh,
            )

        return {
            "masks": labels,
            "prob": prob,
            "dist": dist,
            "metadata": metadata,
        }

    def _extract_layer_data(self, layer) -> np.ndarray:
        if layer is None:
            raise ValueError("Layer is required for StarDist ONNX.")
        return layer_data_asarray(layer)

    def _resolve_paths(self, ndim: int) -> tuple[Path, Path]:
        if ndim == 2:
            onnx_path = self.model_dir / "model_2d.onnx"
            if not onnx_path.exists():
                onnx_path = self.model_dir / "model.onnx"
            config_path = self.model_dir / "config_2d.json"
            if not config_path.exists():
                config_path = self.model_dir / "config.json"
            return onnx_path, config_path
        if ndim == 3:
            onnx_path = self.model_dir / "model_3d.onnx"
            if not onnx_path.exists():
                onnx_path = self.model_dir / "model.onnx"
            config_path = self.model_dir / "config_3d.json"
            if not config_path.exists():
                config_path = self.model_dir / "config.json"
            return onnx_path, config_path
        raise ValueError("StarDist ONNX supports only 2D or 3D models.")

    def _load_config(
        self, image: np.ndarray, config_path: Path
    ) -> StarDistOnnxConfig:
        config = StarDistOnnxConfig.from_json(config_path, image.ndim)
        inferred_axes = infer_image_axes(image)
        if config.axes != inferred_axes:
            raise ValueError(
                f"Config axes {config.axes} do not match image axes {inferred_axes}."
            )
        if len(config.grid) != image.ndim:
            raise ValueError("Config grid does not match image dimensionality.")
        return config

    def _prepare_input(
        self, image: np.ndarray, config: StarDistOnnxConfig
    ) -> np.ndarray:
        input_tensor = add_axes(image, config.axes, config.input_axes)
        return np.expand_dims(input_tensor, axis=0)

    def _run_onnx(
        self,
        input_tensor: np.ndarray,
        config: StarDistOnnxConfig,
        onnx_path: Path,
    ) -> tuple[np.ndarray, np.ndarray]:
        session = self._get_session(onnx_path)
        input_name = config.input_name or session.get_inputs()[0].name
        if config.prob_output and config.dist_output:
            output_names = [config.prob_output, config.dist_output]
        else:
            outputs = session.get_outputs()
            if len(outputs) < 2:
                raise RuntimeError("ONNX model must provide at least two outputs.")
            output_names = [outputs[0].name, outputs[1].name]
        prob, dist = session.run(output_names, {input_name: input_tensor})
        return prob, dist

    def _format_outputs(
        self,
        prob: np.ndarray,
        dist: np.ndarray,
        config: StarDistOnnxConfig,
    ) -> tuple[np.ndarray, np.ndarray]:
        prob = squeeze_batch(np.asarray(prob))
        dist = squeeze_batch(np.asarray(dist))

        prob = drop_axes(prob, config.prob_axes, config.axes)
        dist = drop_axes(dist, config.dist_axes, config.axes + "R")

        if dist.shape[-1] != config.n_rays:
            raise ValueError(
                f"Expected {config.n_rays} rays, got {dist.shape[-1]}."
            )
        dist = np.maximum(dist, 1e-3)
        return prob.astype(np.float32), dist.astype(np.float32)

    def _get_session(self, onnx_path: Path):
        if not onnx_path.exists():
            raise FileNotFoundError(f"Missing ONNX model at {onnx_path}.")
        if self._session is None or self._session_path != onnx_path:
            try:
                import onnxruntime as ort
            except ImportError as exc:
                raise RuntimeError(
                    "onnxruntime is required to run StarDist ONNX."
                ) from exc
            self._session = ort.InferenceSession(
                str(onnx_path),
                providers=["CPUExecutionProvider"],
            )
            self._session_path = onnx_path
        return self._session
