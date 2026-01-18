"""Feature UI base classes for quantification."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qtpy.QtWidgets import QComboBox, QFormLayout, QWidget

if TYPE_CHECKING:
    from ..frontend import QuantificationTab


class SenoQuantFeature:
    """Base class for quantification feature UI."""

    feature_type: str = ""
    order: int = 0

    def __init__(self, tab: "QuantificationTab", config: dict) -> None:
        self._tab = tab
        self._config = config

    def build(self) -> None:
        """Build the UI for this feature."""
        raise NotImplementedError

    def on_features_changed(self, configs: list[dict]) -> None:
        """Handle updates when the feature list changes."""
        return

    @classmethod
    def update_type_options(cls, tab: "QuantificationTab", configs: list[dict]) -> None:
        """Update type availability in feature selectors."""
        return

    def build_labels_widget(self, label_text: str) -> None:
        """Build and attach a labels selection widget.

        Parameters
        ----------
        label_text : str
            Label shown for the combo box.
        """
        labels_form = QFormLayout()
        labels_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        labels_combo = RefreshingComboBox(
            refresh_callback=lambda combo_ref=None: self._refresh_labels_combo(
                labels_combo
            )
        )
        self._tab._configure_combo(labels_combo)
        labels_form.addRow(label_text, labels_combo)
        labels_widget = QWidget()
        labels_widget.setLayout(labels_form)
        left_layout = self._config.get("left_layout")
        if left_layout is not None:
            left_layout.insertWidget(1, labels_widget)
        self._config["labels_widget"] = labels_widget

    def _refresh_labels_combo(self, combo: QComboBox) -> None:
        current = combo.currentText()
        combo.clear()
        viewer = self._tab._viewer
        if viewer is None:
            combo.addItem("Select labels")
            return
        for layer in viewer.layers:
            if layer.__class__.__name__ == "Labels":
                combo.addItem(layer.name)
        if current:
            index = combo.findText(current)
            if index != -1:
                combo.setCurrentIndex(index)


class RefreshingComboBox(QComboBox):
    """Combo box that refreshes its items when opened."""

    def __init__(self, refresh_callback=None, parent=None) -> None:
        super().__init__(parent)
        self._refresh_callback = refresh_callback

    def showPopup(self) -> None:
        if self._refresh_callback is not None:
            self._refresh_callback()
        super().showPopup()
