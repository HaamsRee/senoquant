"""Spots feature UI."""

from typing import Callable, Optional

from qtpy.QtWidgets import QComboBox, QFormLayout, QWidget

from ..base import RefreshingComboBox, SenoQuantFeature
from ..roi import ROISection
from .config import SpotsFeatureData


class SpotsFeature(SenoQuantFeature):
    """Spots feature controls."""

    feature_type = "Spots"
    order = 20

    def build(self) -> None:
        """Build the spots feature UI."""
        data = self._state.data
        if isinstance(data, SpotsFeatureData):
            self._build_labels_widget(
                "Spots",
                get_value=lambda: data.labels,
                set_value=lambda text: setattr(data, "labels", text),
            )
            roi_section = ROISection(self._tab, self._context, data.rois)
        else:
            self._build_labels_widget("Spots")
            roi_section = ROISection(self._tab, self._context, [])
        roi_section.build()
        self._ui["roi_section"] = roi_section

    def on_features_changed(self, configs: list) -> None:
        """Update ROI titles when feature ordering changes.

        Parameters
        ----------
        configs : list of FeatureUIContext
            Current feature contexts.
        """
        roi_section = self._ui.get("roi_section")
        if roi_section is not None:
            roi_section.update_titles()

    def _build_labels_widget(
        self,
        label_text: str,
        get_value: Optional[Callable[[], str]] = None,
        set_value: Optional[Callable[[str], None]] = None,
    ) -> None:
        """Build and attach a labels selection widget.

        Parameters
        ----------
        label_text : str
            Label shown for the combo box.
        get_value : callable, optional
            Getter returning the currently selected label name.
        set_value : callable, optional
            Setter called when the selection changes.
        """
        labels_form = QFormLayout()
        labels_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        labels_combo = RefreshingComboBox(
            refresh_callback=lambda combo_ref=None: self._refresh_labels_combo(
                labels_combo
            )
        )
        self._tab._configure_combo(labels_combo)
        if set_value is not None:
            labels_combo.currentTextChanged.connect(set_value)
        labels_form.addRow(label_text, labels_combo)
        labels_widget = QWidget()
        labels_widget.setLayout(labels_form)
        self._context.left_layout.insertWidget(1, labels_widget)
        self._ui["labels_widget"] = labels_widget
        if get_value is not None:
            current = get_value()
            if current:
                labels_combo.setCurrentText(current)

    def _refresh_labels_combo(self, combo: QComboBox) -> None:
        """Refresh the labels combo with available layers.

        Parameters
        ----------
        combo : QComboBox
            Combo box to populate.
        """
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
