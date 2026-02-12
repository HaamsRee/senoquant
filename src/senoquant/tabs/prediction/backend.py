"""Backend logic for the Prediction tab."""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from senoquant.tabs.prediction.models import SenoQuantPredictionModel
from senoquant.utils import append_run_metadata

try:
    from napari.layers import Image, Labels, Points
except Exception:  # pragma: no cover - optional import for runtime
    Image = None
    Labels = None
    Points = None


class PredictionBackend:
    """Manage prediction models and push outputs into a napari viewer.

    Parameters
    ----------
    models_root : pathlib.Path or None
        Optional root folder for prediction models. Defaults to the local
        ``models`` directory for this tab.
    """

    def __init__(self, models_root: Path | None = None) -> None:
        self._models_root = models_root or (Path(__file__).parent / "models")
        self._models: dict[str, SenoQuantPredictionModel] = {}

    def get_model(self, name: str) -> SenoQuantPredictionModel:
        """Return a prediction model wrapper for the given name."""
        model = self._models.get(name)
        if model is None:
            model_cls = self._load_model_class(name)
            if model_cls is None:
                model = SenoQuantPredictionModel(name, self._models_root)
            else:
                model = model_cls(models_root=self._models_root)
            self._models[name] = model
        return model

    def list_model_names(self) -> list[str]:
        """List available prediction model folders under the models root."""
        if not self._models_root.exists():
            return []

        entries: list[tuple[float, str]] = []
        for path in self._models_root.iterdir():
            if path.is_dir() and not path.name.startswith("__"):
                model = self.get_model(path.name)
                order = model.display_order()
                order_key = order if order is not None else float("inf")
                entries.append((order_key, path.name))

        entries.sort(key=lambda item: (item[0], item[1]))
        return [name for _, name in entries]

    def run_model(
        self,
        model_name: str,
        *,
        viewer=None,
        settings: dict[str, object] | None = None,
        settings_widget=None,
    ) -> dict[str, object]:
        """Run a prediction model and normalize its result payload."""
        model = self.get_model(model_name)
        run_settings: dict[str, object]
        if isinstance(settings, dict):
            run_settings = dict(settings)
        else:
            run_settings = model.collect_widget_settings(settings_widget)

        result = model.run(
            viewer=viewer,
            settings=run_settings,
        )

        if result is None:
            return {"layers": [], "settings": run_settings}

        if isinstance(result, Mapping):
            payload = dict(result)
        elif isinstance(result, Sequence) and not isinstance(result, (str, bytes)):
            payload = {"layers": list(result)}
        else:
            raise ValueError(
                "Prediction models must return a dict or a sequence of layer specs."
            )

        raw_layers = payload.get("layers", [])
        if raw_layers is None:
            payload["layers"] = []
        elif isinstance(raw_layers, Sequence) and not isinstance(raw_layers, (str, bytes)):
            payload["layers"] = list(raw_layers)
        else:
            raise ValueError("Prediction result 'layers' must be a sequence.")

        if not isinstance(payload.get("settings"), dict):
            payload["settings"] = run_settings

        return payload

    def push_layers_to_viewer(
        self,
        viewer,
        model_name: str,
        result: dict[str, object] | None,
        source_layer=None,
    ) -> list[object]:
        """Add model-produced layers into the napari viewer."""
        if viewer is None or not isinstance(result, Mapping):
            return []

        raw_layers = result.get("layers", [])
        if not isinstance(raw_layers, Sequence) or isinstance(raw_layers, (str, bytes)):
            return []

        settings = result.get("settings")
        settings_dict = settings if isinstance(settings, dict) else {}

        source_metadata = {}
        source_name = model_name
        if source_layer is not None:
            source_name = str(getattr(source_layer, "name", "")).strip() or model_name
            maybe_metadata = getattr(source_layer, "metadata", {})
            if isinstance(maybe_metadata, dict):
                source_metadata = dict(maybe_metadata)

        added_layers: list[object] = []
        for index, raw_spec in enumerate(raw_layers, start=1):
            normalized = self._normalize_layer_spec(
                raw_spec=raw_spec,
                source_name=source_name,
                model_name=model_name,
                index=index,
            )
            if normalized is None:
                continue

            data, kwargs, layer_type = normalized
            merged_metadata: dict[str, object] = {}
            merged_metadata.update(source_metadata)

            layer_metadata = kwargs.get("metadata")
            if isinstance(layer_metadata, dict):
                merged_metadata.update(layer_metadata)

            merged_metadata = append_run_metadata(
                merged_metadata,
                task="prediction",
                runner_type="prediction_model",
                runner_name=model_name,
                settings=settings_dict,
            )
            kwargs["metadata"] = merged_metadata

            layer = self._add_layer(viewer, data, layer_type=layer_type, kwargs=kwargs)
            if layer is not None:
                added_layers.append(layer)

        return added_layers

    def _load_model_class(self, name: str) -> type[SenoQuantPredictionModel] | None:
        """Load the model class from a model folder's ``model.py`` file."""
        model_path = self._models_root / name / "model.py"
        if not model_path.exists():
            return None

        module_name = f"senoquant.tabs.prediction.models.{name}.model"
        package_name = f"senoquant.tabs.prediction.models.{name}"
        spec = importlib.util.spec_from_file_location(module_name, model_path)
        if spec is None or spec.loader is None:
            return None

        module = importlib.util.module_from_spec(spec)
        module.__package__ = package_name
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        candidates = [
            obj
            for obj in module.__dict__.values()
            if isinstance(obj, type)
            and issubclass(obj, SenoQuantPredictionModel)
            and obj is not SenoQuantPredictionModel
        ]
        if not candidates:
            return None
        return candidates[0]

    @staticmethod
    def _normalize_layer_spec(
        *,
        raw_spec: object,
        source_name: str,
        model_name: str,
        index: int,
    ) -> tuple[object, dict[str, object], str] | None:
        """Normalize a layer spec to ``(data, kwargs, layer_type)``."""
        kwargs: dict[str, object]

        if isinstance(raw_spec, Mapping):
            if "data" not in raw_spec:
                return None
            data = raw_spec["data"]
            layer_type = str(raw_spec.get("type", "image")).strip().lower() or "image"
            kwargs = {}

            maybe_kwargs = raw_spec.get("kwargs")
            if isinstance(maybe_kwargs, Mapping):
                kwargs.update(dict(maybe_kwargs))

            for key, value in raw_spec.items():
                if key in {"data", "type", "kwargs"}:
                    continue
                kwargs[key] = value
        elif isinstance(raw_spec, Sequence) and not isinstance(raw_spec, (str, bytes)):
            if len(raw_spec) == 0:
                return None
            if len(raw_spec) == 1:
                data = raw_spec[0]
                kwargs = {}
                layer_type = "image"
            elif len(raw_spec) == 2:
                data = raw_spec[0]
                maybe_kwargs = raw_spec[1]
                kwargs = dict(maybe_kwargs) if isinstance(maybe_kwargs, Mapping) else {}
                layer_type = "image"
            else:
                data = raw_spec[0]
                maybe_kwargs = raw_spec[1]
                kwargs = dict(maybe_kwargs) if isinstance(maybe_kwargs, Mapping) else {}
                layer_type = str(raw_spec[2]).strip().lower() or "image"
        else:
            return None

        if "name" not in kwargs:
            kwargs["name"] = f"{source_name}_{model_name}_prediction_{index}"

        return data, kwargs, layer_type

    @staticmethod
    def _add_layer(
        viewer,
        data,
        *,
        layer_type: str,
        kwargs: dict[str, object],
    ):
        """Add a layer to viewer using napari add_* methods when available."""
        add_method = getattr(viewer, f"add_{layer_type}", None)
        if callable(add_method):
            return PredictionBackend._call_add_method(add_method, data, kwargs)

        if hasattr(viewer, "add_layer"):
            layer_obj = PredictionBackend._build_layer_object(
                data,
                layer_type=layer_type,
                kwargs=kwargs,
            )
            if layer_obj is not None:
                added = viewer.add_layer(layer_obj)
                return added if added is not None else layer_obj

        image_method = getattr(viewer, "add_image", None)
        if callable(image_method):
            return PredictionBackend._call_add_method(image_method, data, kwargs)

        return None

    @staticmethod
    def _build_layer_object(
        data,
        *,
        layer_type: str,
        kwargs: dict[str, object],
    ):
        """Build concrete napari layer objects when available."""
        if layer_type == "labels" and Labels is not None:
            try:
                return Labels(data, **kwargs)
            except TypeError:
                pass
        if layer_type == "points" and Points is not None:
            try:
                return Points(data, **kwargs)
            except TypeError:
                pass
        if Image is not None:
            try:
                return Image(data, **kwargs)
            except TypeError:
                pass
        return None

    @staticmethod
    def _call_add_method(add_method, data, kwargs: dict[str, object]):
        """Call a viewer add_* method with conservative fallback signatures."""
        try:
            return add_method(data, **kwargs)
        except TypeError:
            fallback_kwargs = {"name": kwargs.get("name")}
            if "metadata" in kwargs:
                fallback_kwargs["metadata"] = kwargs["metadata"]
            fallback_kwargs = {
                key: value for key, value in fallback_kwargs.items() if value is not None
            }
            try:
                return add_method(data, **fallback_kwargs)
            except TypeError:
                return add_method(data)
