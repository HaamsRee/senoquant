"""ROI selection UI helpers for quantification features."""

from __future__ import annotations

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


class ROISection:
    """Reusable ROI controls for marker and spots features."""

    def __init__(self, tab, config: dict) -> None:
        """Initialize the ROI helper for a feature.

        Parameters
        ----------
        tab : QuantificationTab
            Parent quantification tab instance.
        config : dict
            Feature configuration dictionary.
        """
        self._tab = tab
        self._config = config
        self._data = config.setdefault("feature_data", {})
        self._checkbox: QCheckBox | None = None
        self._container: QWidget | None = None
        self._layout: QVBoxLayout | None = None
        self._scroll_area: QScrollArea | None = None
        self._items_container: QWidget | None = None
        self._items: list[QGroupBox] = []

    def build(self) -> None:
        """Create the ROI controls and attach to the right column."""
        right_layout = self._config.get("right_layout")
        if right_layout is None:
            return

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

        self._data["roi_checkbox"] = checkbox
        self._data["roi_container"] = container
        self._data["roi_layout"] = layout
        self._data["roi_scroll_area"] = scroll_area
        self._data["roi_items_container"] = items_container
        self._data["roi_items"] = self._items
        self._data["roi_section"] = self

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
                self._add_row()
        else:
            self.clear()
        self._tab._features_layout.activate()
        self._tab._apply_features_layout()
        if self._tab._features_scroll_area is not None:
            self._tab._features_scroll_area.updateGeometry()
        QTimer.singleShot(0, self._tab._apply_features_layout)
        QTimer.singleShot(0, self._update_scroll_height)

    def _add_row(self) -> None:
        """Add a new ROI configuration row."""
        if self._layout is None:
            return
        roi_index = len(self._items) + 1
        feature_index = self._tab._feature_index(self._config)

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

        shapes_combo = RefreshingComboBox(
            refresh_callback=lambda combo_ref=None: self._refresh_shapes_combo(
                shapes_combo
            )
        )
        self._tab._configure_combo(shapes_combo)
        shapes_combo.setMinimumWidth(120)

        roi_type = QComboBox()
        roi_type.addItems(["Include", "Exclude"])
        self._tab._configure_combo(roi_type)
        roi_type.setMinimumWidth(120)

        form_layout.addRow("Name", roi_name)
        form_layout.addRow("Layer", shapes_combo)
        form_layout.addRow("Type", roi_type)

        delete_button = QPushButton("Delete")
        delete_button.clicked.connect(
            lambda _checked=False, section=roi_section: self._remove_row(section)
        )

        roi_layout_inner = QVBoxLayout()
        roi_layout_inner.addLayout(form_layout)
        roi_layout_inner.addWidget(delete_button)
        roi_section.setLayout(roi_layout_inner)
        roi_section.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self._layout.addWidget(roi_section)
        self._items.append(roi_section)
        self._data["roi_items"] = self._items
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
        if self._layout is None or roi_section not in self._items:
            return
        self._items.remove(roi_section)
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
        feature_index = self._tab._feature_index(self._config)
        for roi_index, section in enumerate(self._items, start=1):
            section.setTitle(f"Feature {feature_index}: ROI {roi_index}")

    def clear(self) -> None:
        """Remove all ROI rows and reset layout state."""
        if self._layout is None:
            return
        for roi_section in list(self._items):
            self._layout.removeWidget(roi_section)
            roi_section.deleteLater()
        self._items.clear()
        self._data["roi_items"] = self._items
        self.update_titles()
        self._update_scroll_height()

    def _update_scroll_height(self) -> None:
        """Resize the ROI scroll area based on content height."""
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

    def _refresh_shapes_combo(self, combo: QComboBox) -> None:
        """Populate the shapes combo with available ROI layers.

        Parameters
        ----------
        combo : QComboBox
            Combo box to populate.
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
