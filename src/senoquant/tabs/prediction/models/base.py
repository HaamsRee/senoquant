"""Base class for prediction model implementations."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qtpy.QtWidgets import QWidget


class SenoQuantPredictionModel:
    """Handle per-model storage paths and runtime hooks for prediction models.

    Parameters
    ----------
    name : str
        Model identifier used for folder creation.
    models_root : pathlib.Path or None
        Optional root folder for model storage.
    """

    def __init__(self, name: str, models_root: Path | None = None) -> None:
        """Initialize the model wrapper and ensure its folder exists."""
        if not name:
            raise ValueError("Prediction model name must be non-empty.")

        self.name = name
        self.models_root = models_root or Path(__file__).parent
        self.model_dir = self.models_root / name
        self.model_dir.mkdir(parents=True, exist_ok=True)

    @property
    def class_path(self) -> Path:
        """Return the path to the model class file."""
        return self.model_dir / "model.py"

    def display_order(self) -> float | None:
        """Return optional UI ordering for the model selector.

        Returns
        -------
        float or None
            Lower values are shown first. ``None`` means no explicit priority.
        """
        return None

    def build_widget(
        self,
        parent: "QWidget | None" = None,
        viewer=None,
    ) -> "QWidget | None":
        """Create and return a model-specific Qt widget.

        Parameters
        ----------
        parent : QWidget or None
            Optional widget parent.
        viewer : object or None
            Optional napari viewer passed by the prediction tab.

        Returns
        -------
        QWidget or None
            Custom configuration widget for this model.
        """
        return None

    def collect_widget_settings(
        self,
        settings_widget: "QWidget | None" = None,
    ) -> dict[str, object]:
        """Collect a serializable settings dictionary from a widget.

        Parameters
        ----------
        settings_widget : QWidget or None
            Widget previously created by :meth:`build_widget`.

        Returns
        -------
        dict[str, object]
            Settings payload passed into :meth:`run`.
        """
        return {}

    def run(self, **kwargs) -> dict:
        """Run the model with provided inputs and return layer payloads.

        Parameters
        ----------
        **kwargs
            Model-specific run payload, typically including ``viewer`` and
            ``settings``.

        Returns
        -------
        dict
            Mapping with a ``layers`` entry compatible with napari-style
            layer-data tuples.
        """
        raise NotImplementedError("Prediction model run not implemented.")
