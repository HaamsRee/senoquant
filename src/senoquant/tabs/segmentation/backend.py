"""Backend logic for the Segmentation tab."""

from __future__ import annotations

from pathlib import Path

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
            model = SenoQuantSegmentationModel(name, self._models_root)
            self._models[name] = model
        return model

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

        names = []
        for path in self._models_root.iterdir():
            if path.is_dir() and not path.name.startswith("__"):
                if task is None:
                    names.append(path.name)
                else:
                    model = self.get_model(path.name)
                    if model.supports_task(task):
                        names.append(path.name)
        return sorted(names)
