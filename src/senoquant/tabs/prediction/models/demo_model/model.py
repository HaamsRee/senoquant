"""Basic placeholder prediction model with layer selection and scaling."""

from __future__ import annotations

import numpy as np
from qtpy.QtWidgets import QComboBox, QDoubleSpinBox, QFormLayout, QWidget

from senoquant.tabs.prediction.models.base import SenoQuantPredictionModel
from senoquant.utils import layer_data_asarray


class _RefreshingComboBox(QComboBox):
    """Combo box that refreshes items when opened."""

    def __init__(self, refresh_callback=None, parent=None) -> None:
        super().__init__(parent)
        self._refresh_callback = refresh_callback

    def showPopup(self) -> None:
        if self._refresh_callback is not None:
            self._refresh_callback()
        super().showPopup()


class DemoModelWidget(QWidget):
    """Minimal controls for selecting input image and multiplier."""

    def __init__(self, viewer, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._viewer = viewer

        layout = QFormLayout()
        layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self.layer_combo = _RefreshingComboBox(refresh_callback=self.refresh_layers)
        self.multiplier_spin = QDoubleSpinBox()
        self.multiplier_spin.setDecimals(3)
        self.multiplier_spin.setRange(-1_000_000.0, 1_000_000.0)
        self.multiplier_spin.setValue(1.0)

        layout.addRow("Image layer", self.layer_combo)
        layout.addRow("Multiplier", self.multiplier_spin)
        self.setLayout(layout)

        self.refresh_layers()

    def refresh_layers(self) -> None:
        """Refresh image-layer choices from the viewer."""
        current = self.layer_combo.currentText()
        self.layer_combo.clear()

        names = [layer.name for layer in _iter_image_layers(self._viewer)]
        if not names:
            self.layer_combo.addItem("Select a layer")
            return

        self.layer_combo.addItems(names)
        index = self.layer_combo.findText(current)
        if index != -1:
            self.layer_combo.setCurrentIndex(index)

    def values(self) -> dict[str, object]:
        """Return current user settings."""
        return {
            "layer_name": self.layer_combo.currentText(),
            "multiplier": float(self.multiplier_spin.value()),
        }


class DemoModel(SenoQuantPredictionModel):
    """Simple demo model that scales one selected image layer."""

    def __init__(self, models_root=None) -> None:
        super().__init__("demo_model", models_root=models_root)

    def display_order(self) -> float | None:
        return 1.0

    def build_widget(
        self,
        parent: QWidget | None = None,
        viewer=None,
    ) -> QWidget | None:
        return DemoModelWidget(viewer=viewer, parent=parent)

    def collect_widget_settings(
        self,
        settings_widget: QWidget | None = None,
    ) -> dict[str, object]:
        if isinstance(settings_widget, DemoModelWidget):
            return settings_widget.values()
        return {
            "layer_name": "",
            "multiplier": 1.0,
        }

    def run(self, **kwargs) -> dict:
        viewer = kwargs.get("viewer")
        settings = kwargs.get("settings", {}) or {}
        layer_name = str(settings.get("layer_name", "")).strip()
        multiplier = float(settings.get("multiplier", 1.0))

        layer = _get_image_layer_by_name(viewer, layer_name)
        if layer is None:
            raise ValueError("Selected image layer is not available.")

        image = layer_data_asarray(layer, squeeze=False)
        scaled = _multiply_with_dtype_clip(image, multiplier)
        output_name = f"{layer.name}_demo_model"

        return {
            "layers": [
                {
                    "data": scaled,
                    "type": "image",
                    "name": output_name,
                }
            ]
        }


def _iter_image_layers(viewer) -> list:
    """Return image-like layers from viewer."""
    if viewer is None:
        return []

    image_layers = []
    for layer in getattr(viewer, "layers", []):
        if layer.__class__.__name__ == "Image":
            image_layers.append(layer)
    return image_layers


def _get_image_layer_by_name(viewer, name: str):
    """Return an image-like layer by name from viewer."""
    if not name:
        return None

    for layer in _iter_image_layers(viewer):
        if layer.name == name:
            return layer
    return None


def _multiply_with_dtype_clip(data, multiplier: float):
    """Multiply values and clip to source dtype limits."""
    array = np.asarray(data)
    dtype = array.dtype
    scaled = np.asarray(array, dtype=np.float64) * float(multiplier)

    if np.issubdtype(dtype, np.bool_):
        scaled = np.clip(scaled, 0.0, 1.0)
        return scaled.astype(np.bool_)

    if np.issubdtype(dtype, np.integer):
        limits = np.iinfo(dtype)
        scaled = np.clip(scaled, limits.min, limits.max)
        return scaled.astype(dtype)

    if np.issubdtype(dtype, np.floating):
        limits = np.finfo(dtype)
        scaled = np.clip(scaled, limits.min, limits.max)
        return scaled.astype(dtype)

    return scaled
