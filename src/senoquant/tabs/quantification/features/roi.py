"""ROI selection UI helpers for quantification features."""

from __future__ import annotations

from dataclasses import dataclass

from qtpy.QtCore import Qt, QTimer
from qtpy.QtGui import QGuiApplication
from qtpy.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .base import RefreshingComboBox


@dataclass
class ROIConfig:
    """Configuration for a single ROI entry.

    Attributes
    ----------
    name : str
        Display name for the ROI.
    layer : str
        Shapes layer name used for the ROI.
    roi_type : str
        Whether the ROI should be included or excluded.
    """

    name: str = ""
    layer: str = ""
    roi_type: str = "Include"


class ROISection:
    """Reusable ROI controls for marker and spots features."""

    def __init__(
        self,
        tab,
        context,
        rois: list[ROIConfig],
    ) -> None:
        """Initialize the ROI helper for a feature.

        Parameters
        ----------
        tab : QuantificationTab
            Parent quantification tab instance.
        context : FeatureUIContext
            Feature UI context.
        rois : list of ROIConfig
            Feature ROI configuration list.
        """
        self._tab = tab
        self._context = context
        self._rois = rois
        self._checkbox: QCheckBox | None = None
        self._container: QWidget | None = None
        self._layout: QVBoxLayout | None = None
        self._scroll_area: QScrollArea | None = None
        self._items_container: QWidget | None = None
        self._items: list[tuple[QGroupBox, ROIConfig]] = []

    def build(self) -> None:
        """Create the ROI controls and attach to the right column."""
        right_layout = self._context.right_layout

        checkbox = QCheckBox("ROIs")
        checkbox.toggled.connect(self._toggle)

        container = QWidget()
        container.setVisible(False)
        container.setMinimumWidth(240)
        container_layout = QVBoxLayout()
        container_layout.setContentsMargins(0, 0, 0, 0)
        container.setLayout(container_layout)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        scroll_area.setMinimumWidth(240)

        items_container = QWidget()
        items_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSizeConstraint(QVBoxLayout.SetMinAndMaxSize)
        items_container.setLayout(layout)
        scroll_area.setWidget(items_container)

        add_button = QPushButton("Add ROI")
        add_button.clicked.connect(self._add_row)

        container_layout.addWidget(scroll_area)
        container_layout.addWidget(add_button)

        right_layout.addWidget(checkbox)
        right_layout.addWidget(container)

        self._checkbox = checkbox
        self._container = container
        self._layout = layout
        self._scroll_area = scroll_area
        self._items_container = items_container
        self._items = []

        if self._rois:
            checkbox.setChecked(True)
            for roi in self._rois:
                self._add_row(roi)
            self._update_scroll_height()

    def _toggle(self, enabled: bool) -> None:
        """Show or hide ROI controls when toggled.

        Parameters
        ----------
        enabled : bool
            Whether ROI controls should be visible.
        """
        if self._container is None:
            return
        self._container.setVisible(enabled)
        if enabled:
            if not self._items:
                if self._rois:
                    for roi in self._rois:
                        self._add_row(roi)
                else:
                    self._add_row()
        else:
            self.clear()
        self._tab._features_layout.activate()
        self._tab._apply_features_layout()
        if self._tab._features_scroll_area is not None:
            self._tab._features_scroll_area.updateGeometry()
        QTimer.singleShot(0, self._tab._apply_features_layout)
        QTimer.singleShot(0, self._update_scroll_height)

    def _add_row(self, roi: ROIConfig | None = None) -> None:
        """Add a new ROI configuration row.

        Parameters
        ----------
        roi : ROIConfig or None
            Existing ROI configuration to edit, or ``None`` to create one.
        """
        if self._layout is None:
            return
        if isinstance(roi, bool):
            roi = None
        roi_index = len(self._items)
        feature_index = self._tab._feature_index(self._context)
        if roi is None:
            roi = ROIConfig()
            self._rois.append(roi)

        roi_section = QGroupBox(f"Feature {feature_index}: ROI {roi_index}")
        roi_section.setFlat(True)
        roi_section.setStyleSheet(
            "QGroupBox {"
            "  margin-top: 6px;"
            "}"
            "QGroupBox::title {"
            "  subcontrol-origin: margin;"
            "  subcontrol-position: top left;"
            "  padding: 0 6px;"
            "}"
        )

        form_layout = QFormLayout()
        form_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        roi_name = QLineEdit()
        roi_name.setPlaceholderText("ROI name")
        roi_name.setMinimumWidth(120)
        roi_name.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        roi_name.setText(roi.name)
        roi_name.textChanged.connect(lambda text: setattr(roi, "name", text))

        shapes_combo = RefreshingComboBox(
            refresh_callback=lambda combo_ref=None: self._refresh_shapes_combo(
                shapes_combo, roi
            )
        )
        self._tab._configure_combo(shapes_combo)
        shapes_combo.setMinimumWidth(120)
        if roi.layer:
            shapes_combo.setCurrentText(roi.layer)
        shapes_combo.currentTextChanged.connect(
            lambda text: setattr(roi, "layer", text)
        )

        roi_type = QComboBox()
        roi_type.addItems(["Include", "Exclude"])
        self._tab._configure_combo(roi_type)
        roi_type.setMinimumWidth(120)
        if roi.roi_type:
            roi_type.setCurrentText(roi.roi_type)
        roi_type.currentTextChanged.connect(
            lambda text: setattr(roi, "roi_type", text)
        )

        form_layout.addRow("Name", roi_name)
        form_layout.addRow("Layer", shapes_combo)
        form_layout.addRow("Type", roi_type)

        delete_button = QPushButton("Delete")
        delete_button.clicked.connect(
            lambda _checked=False, section=roi_section: self._remove_row(
                section
            )
        )

        roi_layout_inner = QVBoxLayout()
        roi_layout_inner.addLayout(form_layout)
        roi_layout_inner.addWidget(delete_button)
        roi_section.setLayout(roi_layout_inner)
        roi_section.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self._layout.addWidget(roi_section)
        self._items.append((roi_section, roi))
        self.update_titles()
        self._tab._features_layout.activate()
        QTimer.singleShot(0, self._tab._apply_features_layout)
        QTimer.singleShot(0, self._update_scroll_height)

    def _remove_row(self, roi_section: QGroupBox) -> None:
        """Remove an ROI row and update titles.

        Parameters
        ----------
        roi_section : QGroupBox
            ROI section widget to remove.
        """
        if self._layout is None:
            return
        item = next(
            (
                (section, roi)
                for section, roi in self._items
                if section is roi_section
            ),
            None,
        )
        if item is None:
            return
        self._items.remove(item)
        section, roi = item
        if roi in self._rois:
            self._rois.remove(roi)
        self._layout.removeWidget(roi_section)
        roi_section.deleteLater()
        if not self._items and self._checkbox is not None:
            self._checkbox.setChecked(False)
        self.update_titles()
        self._update_scroll_height()
        self._tab._features_layout.activate()
        QTimer.singleShot(0, self._tab._apply_features_layout)

    def update_titles(self) -> None:
        """Refresh ROI section titles based on current feature order."""
        feature_index = self._tab._feature_index(self._context)
        for roi_index, (section, _roi) in enumerate(self._items, start=0):
            section.setTitle(f"Feature {feature_index}: ROI {roi_index}")

    def clear(self) -> None:
        """Remove all ROI rows and reset layout state."""
        if self._layout is None:
            return
        for roi_section, roi in list(self._items):
            self._layout.removeWidget(roi_section)
            roi_section.deleteLater()
            if roi in self._rois:
                self._rois.remove(roi)
        self._items.clear()
        self.update_titles()
        self._update_scroll_height()

    def _update_scroll_height(self) -> None:
        """Resize the ROI scroll area based on content height.

        Notes
        -----
        The scroll area grows with content until a maximum height derived
        from the screen size is reached, after which a scrollbar appears.
        """
        scroll_area = self._scroll_area
        container = self._items_container
        if scroll_area is None or container is None:
            return
        screen = self._tab.window().screen() if self._tab.window() else None
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        screen_height = screen.availableGeometry().height() if screen else 720
        target_height = max(140, int(screen_height * 0.2))
        container.adjustSize()
        content_height = container.sizeHint().height()
        frame = scroll_area.frameWidth() * 2
        height = max(0, min(target_height, content_height + frame))
        scroll_area.setFixedHeight(height)
        if content_height + frame <= target_height:
            scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        else:
            scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

    def _refresh_shapes_combo(
        self, combo: QComboBox, roi: ROIConfig
    ) -> None:
        """Populate the shapes combo with available ROI layers.

        Parameters
        ----------
        combo : QComboBox
            Combo box to populate.
        roi : ROIConfig
            ROI configuration to update.
        """
        current = combo.currentText()
        combo.clear()
        viewer = self._tab._viewer
        if viewer is None:
            combo.addItem("Select shapes")
            return
        for layer in viewer.layers:
            if layer.__class__.__name__ == "Shapes":
                combo.addItem(layer.name)
        if current:
            index = combo.findText(current)
            if index != -1:
                combo.setCurrentIndex(index)
        if roi.layer:
            index = combo.findText(roi.layer)
            if index != -1:
                combo.setCurrentIndex(index)
