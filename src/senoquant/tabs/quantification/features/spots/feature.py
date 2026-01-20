"""Spots feature UI."""

from typing import Callable, Optional

from qtpy.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QVBoxLayout,
    QWidget,
)

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
        else:
            self._build_labels_widget("Spots")
            data = SpotsFeatureData()
            self._state.data = data
        self._build_channel_widget(data)
        self._build_segmentation_filter(data)
        roi_section = ROISection(self._tab, self._context, data.rois)
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
        labels_form.setContentsMargins(0, 0, 0, 0)
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
        self._context.left_dynamic_layout.insertWidget(0, labels_widget)
        self._ui["labels_widget"] = labels_widget
        if get_value is not None:
            current = get_value()
            if current:
                labels_combo.setCurrentText(current)

    def _build_channel_widget(self, data: SpotsFeatureData) -> None:
        """Build the channel selection widget.

        Parameters
        ----------
        data : SpotsFeatureData
            Feature data storing the selected channel.
        """
        channel_form = QFormLayout()
        channel_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        channel_form.setContentsMargins(0, 0, 0, 0)
        channel_combo = RefreshingComboBox(
            refresh_callback=lambda combo_ref=None: self._refresh_image_combo(
                channel_combo
            )
        )
        self._tab._configure_combo(channel_combo)
        channel_combo.currentTextChanged.connect(
            lambda text: setattr(data, "channel", text)
        )
        channel_form.addRow("Channel", channel_combo)
        channel_widget = QWidget()
        channel_widget.setLayout(channel_form)
        self._context.left_dynamic_layout.insertWidget(1, channel_widget)
        if data.channel:
            channel_combo.setCurrentText(data.channel)
        self._ui["channel_widget"] = channel_widget

    def _build_segmentation_filter(self, data: SpotsFeatureData) -> None:
        """Build segmentation filter controls for spot counting.

        Parameters
        ----------
        data : SpotsFeatureData
            Feature data storing segmentation filter selections.
        """
        container = QWidget()
        container_layout = QVBoxLayout()
        container_layout.setContentsMargins(0, 0, 0, 0)
        container.setLayout(container_layout)

        checkbox = QCheckBox("Count only within segmentation")
        checkbox.setChecked(bool(data.count_within_segmentation))
        checkbox.toggled.connect(
            lambda checked: self._toggle_segmentation_filter(
                checked, data, container
            )
        )
        container_layout.addWidget(checkbox)

        form_layout = QFormLayout()
        form_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form_layout.setContentsMargins(0, 0, 0, 0)
        labels_combo = RefreshingComboBox(
            refresh_callback=lambda combo_ref=None: self._refresh_labels_combo(
                labels_combo
            )
        )
        self._tab._configure_combo(labels_combo)
        labels_combo.currentTextChanged.connect(
            lambda text: setattr(data, "segmentation_label", text)
        )
        form_layout.addRow("Segmentation", labels_combo)
        labels_widget = QWidget()
        labels_widget.setLayout(form_layout)
        labels_widget.setVisible(bool(data.count_within_segmentation))
        container_layout.addWidget(labels_widget)

        if data.segmentation_label:
            labels_combo.setCurrentText(data.segmentation_label)

        self._context.left_dynamic_layout.insertWidget(2, container)
        self._ui["segmentation_filter"] = container
        self._ui["segmentation_labels_widget"] = labels_widget

    def _toggle_segmentation_filter(
        self,
        enabled: bool,
        data: SpotsFeatureData,
        container: QWidget,
    ) -> None:
        """Toggle segmentation filtering controls.

        Parameters
        ----------
        enabled : bool
            Whether segmentation filtering is enabled.
        data : SpotsFeatureData
            Feature data storing segmentation filter state.
        container : QWidget
            Parent container holding the segmentation controls.
        """
        data.count_within_segmentation = enabled
        labels_widget = self._ui.get("segmentation_labels_widget")
        if labels_widget is not None:
            labels_widget.setVisible(enabled)
        container.updateGeometry()

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

    def _refresh_image_combo(self, combo: QComboBox) -> None:
        """Refresh the image combo with available layers.

        Parameters
        ----------
        combo : QComboBox
            Combo box to populate.
        """
        current = combo.currentText()
        combo.clear()
        viewer = self._tab._viewer
        if viewer is None:
            combo.addItem("Select image")
            return
        for layer in viewer.layers:
            if layer.__class__.__name__ == "Image":
                combo.addItem(layer.name)
        if current:
            index = combo.findText(current)
            if index != -1:
                combo.setCurrentIndex(index)
