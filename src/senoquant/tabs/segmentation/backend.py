"""Backend logic for the Segmentation tab."""

from __future__ import annotations

from pathlib import Path

import importlib.util
import sys

from .models import SenoQuantSegmentationModel


class SegmentationBackend:
    """Manage segmentation models and their storage locations.

    Parameters
    ----------
    models_root : pathlib.Path or None
        Optional root folder for model storage. Defaults to the local models
        directory for this tab.
    """

    def __init__(self, models_root: Path | None = None) -> None:
        self._models_root = models_root or (Path(__file__).parent / "models")
        self._models: dict[str, SenoQuantSegmentationModel] = {}
        self._preloaded = False

    def get_model(self, name: str) -> SenoQuantSegmentationModel:
        """Return a model wrapper for the given name.

        Parameters
        ----------
        name : str
            Model name used to locate or create the model folder.

        Returns
        -------
        SenoQuantSegmentationModel
            Model wrapper instance.
        """
        model = self._models.get(name)
        if model is None:
            model_cls = self._load_model_class(name)
            if model_cls is None:
                model = SenoQuantSegmentationModel(name, self._models_root)
            else:
                model = model_cls(models_root=self._models_root)
            self._models[name] = model
        return model

    def _load_model_class(self, name: str) -> type[SenoQuantSegmentationModel] | None:
        """Load the model class from a model folder's model.py.

        Parameters
        ----------
        name : str
            Model folder name under the models root.

        Returns
        -------
        type[SenoQuantSegmentationModel]
            Concrete model class to instantiate.
        """
        model_path = self._models_root / name / "model.py"
        if not model_path.exists():
            return None

        module_name = f"senoquant.tabs.segmentation.models.{name}.model"
        package_name = f"senoquant.tabs.segmentation.models.{name}"
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
            and issubclass(obj, SenoQuantSegmentationModel)
            and obj is not SenoQuantSegmentationModel
        ]
        if not candidates:
            return None
        return candidates[0]

    def list_model_names(self, task: str | None = None) -> list[str]:
        """List available model folders under the models root.

        Parameters
        ----------
        task : str or None
            Optional task filter such as "nuclear" or "cytoplasmic".

        Returns
        -------
        list[str]
            Sorted model folder names.
        """
        if not self._models_root.exists():
            return []

        entries: list[tuple[float, str]] = []
        for path in self._models_root.iterdir():
            if path.is_dir() and not path.name.startswith("__"):
                model = self.get_model(path.name)
                if task is not None and not model.supports_task(task):
                    continue
                order = model.display_order()
                order_key = order if order is not None else float("inf")
                entries.append((order_key, path.name))
        entries.sort(key=lambda item: (item[0], item[1]))
        return [name for _, name in entries]

    def get_preloaded_model(self, name: str) -> SenoQuantSegmentationModel:
        """Return a preloaded model instance by name."""
        model = self._models.get(name)
        if model is None:
            model = self.get_model(name)
        return model

    def preload_models(self) -> None:
        """Instantiate all discovered models once."""
        if self._preloaded:
            return
        for name in self.list_model_names():
            self.get_model(name)
        self._preloaded = True
