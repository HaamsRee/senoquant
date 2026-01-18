"""Frontend widget for the Quantification tab."""

import numpy as np

from qtpy.QtCore import Qt, QTimer
from qtpy.QtGui import QGuiApplication
from qtpy.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QDoubleSpinBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .backend import QuantificationBackend

try:
    from superqt import QDoubleRangeSlider as RangeSlider
except ImportError:  # pragma: no cover - fallback when superqt is unavailable
    try:
        from superqt import QRangeSlider as RangeSlider
    except ImportError:  # pragma: no cover
        RangeSlider = None


class RefreshingComboBox(QComboBox):
    """Combo box that refreshes its items when opened."""

    def __init__(self, refresh_callback=None, parent=None) -> None:
        """Create a combo box that refreshes on popup.

        Parameters
        ----------
        refresh_callback : callable or None
            Function invoked before showing the popup.
        parent : QWidget or None
            Optional parent widget.
        """
        super().__init__(parent)
        self._refresh_callback = refresh_callback

    def showPopup(self) -> None:
        """Refresh items before showing the popup."""
        if self._refresh_callback is not None:
            self._refresh_callback()
        super().showPopup()


class QuantificationTab(QWidget):
    """Quantification tab UI for configuring feature extraction.

    Parameters
    ----------
    backend : QuantificationBackend or None
        Backend instance for quantification workflows.
    napari_viewer : object or None
        Napari viewer used to populate layer dropdowns.
    """
    def __init__(
        self,
        backend: QuantificationBackend | None = None,
        napari_viewer=None,
    ) -> None:
        super().__init__()
        self._backend = backend or QuantificationBackend()
        self._viewer = napari_viewer
        self._feature_configs: list[dict] = []

        layout = QVBoxLayout()
        layout.addWidget(self._make_output_section())
        layout.addWidget(self._make_features_section())
        layout.addStretch(1)
        self.setLayout(layout)

    def _make_output_section(self) -> QGroupBox:
        """Build the output configuration section.

        Returns
        -------
        QGroupBox
            Group box containing output settings.
        """
        section = QGroupBox("Output")
        section_layout = QVBoxLayout()

        form_layout = QFormLayout()
        form_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self._save_name_input = QLineEdit()
        self._save_name_input.setPlaceholderText("Output name")
        self._save_name_input.setMinimumWidth(180)
        self._save_name_input.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Fixed
        )

        self._format_combo = QComboBox()
        self._format_combo.addItems(["csv", "xlsx"])
        self._configure_combo(self._format_combo)

        form_layout.addRow("Save name", self._save_name_input)
        form_layout.addRow("Format", self._format_combo)

        section_layout.addLayout(form_layout)
        section.setLayout(section_layout)
        return section

    def _make_features_section(self) -> QGroupBox:
        """Build the features configuration section.

        Returns
        -------
        QGroupBox
            Group box containing feature inputs.
        """
        section = QGroupBox("Features")
        section.setFlat(True)
        section.setStyleSheet(
            "QGroupBox {"
            "  margin-top: 8px;"
            "}"
            "QGroupBox::title {"
            "  subcontrol-origin: margin;"
            "  subcontrol-position: top left;"
            "  padding: 0 6px;"
            "}"
        )

        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)
        frame.setFrameShadow(QFrame.Plain)
        frame.setObjectName("features-section-frame")
        frame.setStyleSheet(
            "QFrame#features-section-frame {"
            "  border: 1px solid palette(mid);"
            "  border-radius: 4px;"
            "}"
        )

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._features_scroll_area = scroll_area

        features_container = QWidget()
        self._features_container = features_container
        features_container.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Fixed
        )
        features_container.setMinimumWidth(200)
        self._features_min_width = 200
        self._features_layout = QVBoxLayout()
        self._features_layout.setContentsMargins(0, 0, 0, 0)
        self._features_layout.setSpacing(8)
        self._features_layout.setSizeConstraint(QVBoxLayout.SetMinAndMaxSize)
        features_container.setLayout(self._features_layout)
        scroll_area.setWidget(features_container)

        frame_layout = QVBoxLayout()
        frame_layout.setContentsMargins(10, 12, 10, 10)
        frame_layout.addWidget(scroll_area)
        frame.setLayout(frame_layout)

        section_layout = QVBoxLayout()
        section_layout.setContentsMargins(8, 12, 8, 4)
        section_layout.addWidget(frame)

        self._add_feature_button = QPushButton("Add feature")
        self._add_feature_button.clicked.connect(self._add_feature_row)
        section_layout.addWidget(self._add_feature_button)
        section.setLayout(section_layout)

        self._add_feature_row()
        self._update_features_scroll_height()
        return section

    def showEvent(self, event) -> None:
        """Ensure the features list resizes on initial show."""
        super().showEvent(event)
        self._update_features_scroll_height()

    def resizeEvent(self, event) -> None:
        """Resize handler to keep the features list at a capped height.

        Parameters
        ----------
        event : QResizeEvent
            Qt resize event passed by the widget.
        """
        super().resizeEvent(event)
        self._update_features_scroll_height()

    def _update_features_scroll_height(self) -> None:
        """Update the features scroll area height based on the screen size.

        The features list grows with its contents until it reaches a maximum
        height (25% of the screen height), at which point vertical scrolling
        is enabled.
        """
        if not hasattr(self, "_features_scroll_area"):
            return
        screen = self.window().screen() if self.window() is not None else None
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        screen_height = screen.availableGeometry().height() if screen else 720
        target_height = max(180, int(screen_height * 0.25))
        content_height = 0
        if hasattr(self, "_features_container"):
            self._features_container.adjustSize()
            content_height = self._features_container.sizeHint().height()
        frame = self._features_scroll_area.frameWidth() * 2
        height = max(0, min(target_height, content_height + frame))
        self._features_scroll_area.setUpdatesEnabled(False)
        if content_height + frame <= target_height:
            self._features_scroll_area.setVerticalScrollBarPolicy(
                Qt.ScrollBarAlwaysOff
            )
        else:
            self._features_scroll_area.setVerticalScrollBarPolicy(
                Qt.ScrollBarAsNeeded
            )
        self._features_scroll_area.setFixedHeight(height)
        self._features_scroll_area.setUpdatesEnabled(True)
        self._update_feature_columns_width()

    def _update_feature_columns_width(self) -> None:
        """Update column minimum widths from the features container width."""
        if not hasattr(self, "_features_container"):
            return
        total_min = getattr(self, "_features_min_width", 0)
        if total_min <= 0:
            total_min = self._features_container.minimumWidth()
        left_hint = 0
        right_hint = 0
        if hasattr(self, "_left_container") and self._left_container is not None:
            try:
                left_hint = self._left_container.sizeHint().width()
            except RuntimeError:
                self._left_container = None
        if hasattr(self, "_right_container") and self._right_container is not None:
            try:
                right_hint = self._right_container.sizeHint().width()
            except RuntimeError:
                self._right_container = None
        left_min = max(int(total_min * 0.6), left_hint)
        right_min = max(int(total_min * 0.4), right_hint)
        if self._left_container is not None:
            try:
                self._left_container.setMinimumWidth(left_min)
            except RuntimeError:
                self._left_container = None
        if self._right_container is not None:
            try:
                self._right_container.setMinimumWidth(right_min)
            except RuntimeError:
                self._right_container = None
        self._update_features_container_width()

    def _update_features_container_width(self) -> None:
        """Ensure the features container can scroll to the widest feature."""
        if not hasattr(self, "_features_container") or not hasattr(
            self, "_features_layout"
        ):
            return
        max_width = getattr(self, "_features_min_width", 0)
        self._features_layout.invalidate()
        layout_width = self._features_layout.sizeHint().width()
        max_width = max(max_width, layout_width)
        for index in range(self._features_layout.count()):
            item = self._features_layout.itemAt(index)
            widget = item.widget()
            if widget is None:
                continue
            widget.adjustSize()
            max_width = max(
                max_width,
                widget.sizeHint().width(),
                widget.minimumSizeHint().width(),
            )
        max_width = max(
            max_width,
            self._features_container.sizeHint().width(),
            self._features_container.minimumSizeHint().width(),
        )
        self._features_container.setMinimumWidth(max_width)
        self._features_container.updateGeometry()

    def _add_feature_row(self) -> None:
        """Add a new feature input row."""
        index = len(self._feature_configs) + 1
        feature_section = QGroupBox(f"Feature {index}")
        feature_section.setFlat(True)
        feature_section.setStyleSheet(
            "QGroupBox {"
            "  margin-top: 6px;"
            "}"
            "QGroupBox::title {"
            "  subcontrol-origin: margin;"
            "  subcontrol-position: top left;"
            "  padding: 0 6px;"
            "}"
        )

        section_layout = QVBoxLayout()

        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)
        content_layout.setAlignment(Qt.AlignTop)
        left_layout = QVBoxLayout()
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)
        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        form_layout = QFormLayout()
        form_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        name_input = QLineEdit()
        name_input.setPlaceholderText("Feature name")
        name_input.setMinimumWidth(180)
        name_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        type_combo = QComboBox()
        type_combo.addItems(["Marker", "Spots", "Colocalization"])
        self._configure_combo(type_combo)

        form_layout.addRow("Name", name_input)
        form_layout.addRow("Type", type_combo)
        left_layout.addLayout(form_layout)

        delete_button = QPushButton("Delete")
        delete_button.clicked.connect(
            lambda _checked=False, section=feature_section: self._remove_feature(
                section
            )
        )

        left_dynamic_container = QWidget()
        left_dynamic_container.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Fixed
        )
        left_dynamic_layout = QVBoxLayout()
        left_dynamic_layout.setContentsMargins(0, 0, 0, 0)
        left_dynamic_layout.setSpacing(6)
        left_dynamic_container.setLayout(left_dynamic_layout)
        left_layout.addWidget(left_dynamic_container)
        left_layout.addWidget(delete_button)

        left_container = QWidget()
        left_container.setLayout(left_layout)
        left_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        right_container = QWidget()
        right_container.setLayout(right_layout)
        right_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self._left_container = left_container
        self._right_container = right_container

        content_layout.addWidget(left_container, 3)
        content_layout.addWidget(right_container, 2)
        section_layout.addLayout(content_layout)
        self._update_feature_columns_width()
        feature_section.setLayout(section_layout)
        feature_section.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Fixed
        )

        self._features_layout.addWidget(feature_section)
        config = {
            "section": feature_section,
            "name_input": name_input,
            "type_combo": type_combo,
            "left_dynamic_layout": left_dynamic_layout,
            "roi_checkbox": None,
            "roi_container": None,
            "roi_layout": None,
            "roi_scroll_area": None,
            "roi_items_container": None,
            "roi_items": [],
            "coloc_a_combo": None,
            "coloc_b_combo": None,
            "right_layout": right_layout,
            "left_layout": left_layout,
            "labels_widget": None,
            "channel_combo": None,
            "threshold_checkbox": None,
            "threshold_slider": None,
            "threshold_container": None,
            "threshold_min_spin": None,
            "threshold_max_spin": None,
            "threshold_updating": False,
        }
        self._feature_configs.append(config)
        name_input.textChanged.connect(self._update_colocalization_options)
        type_combo.currentTextChanged.connect(
            lambda _text, cfg=config: self._on_feature_type_changed(cfg)
        )
        self._on_feature_type_changed(config)
        self._update_colocalization_options()
        self._features_layout.activate()
        QTimer.singleShot(0, self._update_features_scroll_height)

    def _on_feature_type_changed(self, config: dict) -> None:
        """Update a feature section when its type changes.

        Parameters
        ----------
        config : dict
            Feature configuration dictionary.
        """
        left_dynamic_layout = config["left_dynamic_layout"]
        self._clear_layout(left_dynamic_layout)
        right_layout = config.get("right_layout")
        if right_layout is not None:
            self._clear_layout(right_layout)
        labels_widget = config.get("labels_widget")
        if labels_widget is not None:
            left_layout = config.get("left_layout")
            if left_layout is not None:
                left_layout.removeWidget(labels_widget)
            labels_widget.deleteLater()
            config["labels_widget"] = None
        config["roi_checkbox"] = None
        config["roi_container"] = None
        config["roi_layout"] = None
        config["roi_scroll_area"] = None
        config["roi_items_container"] = None
        config["roi_items"] = []
        config["coloc_a_combo"] = None
        config["coloc_b_combo"] = None
        config["channel_combo"] = None
        config["threshold_checkbox"] = None
        config["threshold_slider"] = None
        config["threshold_container"] = None
        config["threshold_min_spin"] = None
        config["threshold_max_spin"] = None
        config["threshold_updating"] = False

        feature_type = config["type_combo"].currentText()
        if feature_type in ("Marker", "Spots"):
            label_text = "Segmentation labels" if feature_type == "Marker" else "Spots"
            labels_form = QFormLayout()
            labels_form.setFieldGrowthPolicy(
                QFormLayout.AllNonFixedFieldsGrow
            )

            labels_combo = RefreshingComboBox(
                refresh_callback=lambda combo_ref=None: self._refresh_labels_combo(
                    labels_combo
                )
            )
            self._configure_combo(labels_combo)
            labels_form.addRow(label_text, labels_combo)
            labels_widget = QWidget()
            labels_widget.setLayout(labels_form)
            left_layout = config.get("left_layout")
            if left_layout is not None:
                left_layout.insertWidget(1, labels_widget)
            config["labels_widget"] = labels_widget

        if feature_type == "Marker":
            channel_form = QFormLayout()
            channel_form.setFieldGrowthPolicy(
                QFormLayout.AllNonFixedFieldsGrow
            )
            channel_combo = RefreshingComboBox(
                refresh_callback=lambda combo_ref=None: self._refresh_image_combo(
                    channel_combo
                )
            )
            self._configure_combo(channel_combo)
            channel_combo.currentTextChanged.connect(
                lambda _text, cfg=config: self._on_channel_changed(cfg)
            )
            channel_form.addRow("Channel", channel_combo)
            left_dynamic_layout.addLayout(channel_form)

            threshold_checkbox = QCheckBox("Set threshold")
            threshold_checkbox.setEnabled(False)
            threshold_checkbox.toggled.connect(
                lambda checked, cfg=config: self._toggle_threshold(cfg, checked)
            )
            left_dynamic_layout.addWidget(threshold_checkbox)

            threshold_container = QWidget()
            threshold_layout = QHBoxLayout()
            threshold_layout.setContentsMargins(0, 0, 0, 0)
            threshold_slider = self._make_range_slider()
            if hasattr(threshold_slider, "valueChanged"):
                threshold_slider.valueChanged.connect(
                    lambda values, cfg=config: self._on_threshold_slider_changed(
                        cfg, values
                    )
                )
            threshold_min_spin = QDoubleSpinBox()
            threshold_min_spin.setDecimals(2)
            threshold_min_spin.setMinimumWidth(80)
            threshold_min_spin.setSizePolicy(
                QSizePolicy.Fixed, QSizePolicy.Fixed
            )
            threshold_min_spin.valueChanged.connect(
                lambda value, cfg=config: self._on_threshold_spin_changed(
                    cfg, "min", value
                )
            )

            threshold_max_spin = QDoubleSpinBox()
            threshold_max_spin.setDecimals(2)
            threshold_max_spin.setMinimumWidth(80)
            threshold_max_spin.setSizePolicy(
                QSizePolicy.Fixed, QSizePolicy.Fixed
            )
            threshold_max_spin.valueChanged.connect(
                lambda value, cfg=config: self._on_threshold_spin_changed(
                    cfg, "max", value
                )
            )

            threshold_slider.setEnabled(False)
            threshold_slider.setVisible(False)
            threshold_min_spin.setEnabled(False)
            threshold_max_spin.setEnabled(False)
            threshold_layout.addWidget(threshold_min_spin)
            threshold_layout.addWidget(threshold_slider, 1)
            threshold_layout.addWidget(threshold_max_spin)
            threshold_container.setLayout(threshold_layout)
            threshold_container.setVisible(False)
            left_dynamic_layout.addWidget(threshold_container)

            config["channel_combo"] = channel_combo
            config["threshold_checkbox"] = threshold_checkbox
            config["threshold_slider"] = threshold_slider
            config["threshold_container"] = threshold_container
            config["threshold_min_spin"] = threshold_min_spin
            config["threshold_max_spin"] = threshold_max_spin
            self._on_channel_changed(config)
        elif feature_type == "Spots":
            pass
        if feature_type in ("Marker", "Spots"):
            roi_checkbox = QCheckBox("ROIs")
            roi_checkbox.toggled.connect(
                lambda checked, cfg=config: self._toggle_roi_section(cfg, checked)
            )

            roi_container = QWidget()
            roi_container.setVisible(False)
            roi_container.setMinimumWidth(240)
            roi_container_layout = QVBoxLayout()
            roi_container_layout.setContentsMargins(0, 0, 0, 0)
            roi_container.setLayout(roi_container_layout)

            roi_scroll_area = QScrollArea()
            roi_scroll_area.setWidgetResizable(True)
            roi_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            roi_scroll_area.setSizePolicy(
                QSizePolicy.Expanding, QSizePolicy.Fixed
            )
            roi_scroll_area.setMinimumWidth(240)

            roi_items_container = QWidget()
            roi_items_container.setSizePolicy(
                QSizePolicy.Expanding, QSizePolicy.Fixed
            )
            roi_layout = QVBoxLayout()
            roi_layout.setContentsMargins(0, 0, 0, 0)
            roi_layout.setSizeConstraint(QVBoxLayout.SetMinAndMaxSize)
            roi_items_container.setLayout(roi_layout)
            roi_scroll_area.setWidget(roi_items_container)

            add_roi_button = QPushButton("Add ROI")
            add_roi_button.clicked.connect(
                lambda _checked=False, cfg=config: self._add_roi_row(cfg)
            )

            roi_container_layout.addWidget(roi_scroll_area)
            roi_container_layout.addWidget(add_roi_button)

            if right_layout is not None:
                right_layout.addWidget(roi_checkbox)
                right_layout.addWidget(roi_container)

            config["roi_checkbox"] = roi_checkbox
            config["roi_container"] = roi_container
            config["roi_layout"] = roi_layout
            config["roi_scroll_area"] = roi_scroll_area
            config["roi_items_container"] = roi_items_container
            config["roi_items"] = []
        elif feature_type == "Colocalization":
            form_layout = QFormLayout()
            form_layout.setFieldGrowthPolicy(
                QFormLayout.AllNonFixedFieldsGrow
            )
            coloc_a = QComboBox()
            coloc_b = QComboBox()
            self._configure_combo(coloc_a)
            self._configure_combo(coloc_b)
            coloc_a.currentTextChanged.connect(
                lambda _text, cfg=config: self._sync_coloc_choices(cfg)
            )
            coloc_b.currentTextChanged.connect(
                lambda _text, cfg=config: self._sync_coloc_choices(cfg)
            )
            form_layout.addRow("Labels A", coloc_a)
            form_layout.addRow("Labels B", coloc_b)
            left_dynamic_layout.addLayout(form_layout)
            config["coloc_a_combo"] = coloc_a
            config["coloc_b_combo"] = coloc_b
            self._update_colocalization_options()

    def _toggle_roi_section(self, config: dict, enabled: bool) -> None:
        """Toggle the ROI section for a feature.

        Parameters
        ----------
        config : dict
            Feature configuration dictionary.
        enabled : bool
            Whether ROI controls should be visible.
        """
        roi_container = config.get("roi_container")
        if roi_container is None:
            return
        roi_container.setVisible(enabled)
        if enabled:
            if not config.get("roi_items"):
                self._add_roi_row(config)
        else:
            self._clear_rois(config)
        self._features_layout.activate()
        self._update_feature_columns_width()
        self._update_features_container_width()
        if hasattr(self, "_features_scroll_area"):
            self._features_scroll_area.updateGeometry()
        QTimer.singleShot(0, self._update_features_scroll_height)
        QTimer.singleShot(0, lambda cfg=config: self._update_roi_scroll_height(cfg))

    def _add_roi_row(self, config: dict) -> None:
        """Add a new ROI row to a feature.

        Parameters
        ----------
        config : dict
            Feature configuration dictionary.
        """
        roi_layout = config.get("roi_layout")
        if roi_layout is None:
            return
        roi_index = len(config["roi_items"]) + 1
        feature_index = self._feature_index(config)

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
        self._configure_combo(shapes_combo)
        shapes_combo.setMinimumWidth(120)

        roi_type = QComboBox()
        roi_type.addItems(["Include", "Exclude"])
        self._configure_combo(roi_type)
        roi_type.setMinimumWidth(120)

        form_layout.addRow("Name", roi_name)
        form_layout.addRow("Layer", shapes_combo)
        form_layout.addRow("Type", roi_type)

        delete_button = QPushButton("Delete")
        delete_button.clicked.connect(
            lambda _checked=False, section=roi_section, cfg=config: self._remove_roi(
                cfg, section
            )
        )

        roi_layout_inner = QVBoxLayout()
        roi_layout_inner.addLayout(form_layout)
        roi_layout_inner.addWidget(delete_button)
        roi_section.setLayout(roi_layout_inner)
        roi_section.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        roi_layout.addWidget(roi_section)
        config["roi_items"].append(roi_section)
        self._update_roi_titles(config)
        self._features_layout.activate()
        QTimer.singleShot(0, self._update_features_scroll_height)
        QTimer.singleShot(0, lambda cfg=config: self._update_roi_scroll_height(cfg))

    def _remove_roi(self, config: dict, roi_section: QGroupBox) -> None:
        """Remove an ROI row and disable ROI selection if empty.

        Parameters
        ----------
        config : dict
            Feature configuration dictionary.
        roi_section : QGroupBox
            ROI section widget to remove.
        """
        roi_layout = config.get("roi_layout")
        if roi_layout is None or roi_section not in config.get("roi_items", []):
            return
        config["roi_items"].remove(roi_section)
        roi_layout.removeWidget(roi_section)
        roi_section.deleteLater()

        for index, section in enumerate(config["roi_items"], start=1):
            section.setTitle(str(index))

        if not config["roi_items"]:
            checkbox = config.get("roi_checkbox")
            if checkbox is not None:
                checkbox.setChecked(False)
        self._update_roi_titles(config)
        self._update_roi_scroll_height(config)
        self._features_layout.activate()
        QTimer.singleShot(0, self._update_features_scroll_height)

    def _remove_feature(self, feature_section: QGroupBox) -> None:
        """Remove a feature section and renumber remaining entries.

        Parameters
        ----------
        feature_section : QGroupBox
            Feature section widget to remove.
        """
        config = next(
            (cfg for cfg in self._feature_configs if cfg["section"] is feature_section),
            None,
        )
        if config is None:
            return
        self._feature_configs.remove(config)
        self._features_layout.removeWidget(feature_section)
        feature_section.deleteLater()
        self._renumber_features()
        self._update_colocalization_options()
        self._features_layout.activate()
        QTimer.singleShot(0, self._update_features_scroll_height)

    def _renumber_features(self) -> None:
        """Renumber feature sections after insertions/removals."""
        for index, config in enumerate(self._feature_configs, start=1):
            config["section"].setTitle(f"Feature {index}")
            self._update_roi_titles(config)

    def _update_colocalization_options(self) -> None:
        """Enable colocalization when at least two spot features exist."""
        spot_choices = self._spot_feature_choices()
        allow_coloc = len(spot_choices) >= 2
        for config in self._feature_configs:
            combo = config["type_combo"]
            idx = combo.findText("Colocalization")
            if idx != -1:
                combo.model().item(idx).setEnabled(allow_coloc)
            if combo.currentText() == "Colocalization" and not allow_coloc:
                combo.setCurrentText("Marker")

            if combo.currentText() == "Colocalization":
                self._update_coloc_feature_choices(config, spot_choices)

    def _spot_feature_choices(self) -> list[str]:
        """Return display strings for spot features."""
        choices = []
        for index, config in enumerate(self._feature_configs, start=1):
            if config["type_combo"].currentText() == "Spots":
                name = config["name_input"].text().strip()
                label = name if name else f"Feature {index}"
                choices.append(f"{index}: {label}")
        return choices

    def _update_coloc_feature_choices(
        self,
        config: dict,
        choices: list[str],
    ) -> None:
        """Update colocalization feature dropdown options.

        Parameters
        ----------
        config : dict
            Feature configuration dictionary.
        choices : list[str]
            Available spot feature choices.
        """
        combos = []
        for key in ("coloc_a_combo", "coloc_b_combo"):
            combo = config.get(key)
            if combo is None:
                continue
            combos.append(combo)
            current = combo.currentText()
            combo.clear()
            if choices:
                combo.addItems(choices)
            else:
                combo.addItem("No spots features")
            if current:
                index = combo.findText(current)
                if index != -1:
                    combo.setCurrentIndex(index)
        if len(choices) >= 2 and len(combos) == 2:
            a_combo, b_combo = combos
            if a_combo.currentText() == b_combo.currentText():
                a_combo.setCurrentIndex(0)
                b_combo.setCurrentIndex(1)
        self._sync_coloc_choices(config)

    def _sync_coloc_choices(self, config: dict) -> None:
        """Disable selecting the same feature for A/B colocalization.

        Parameters
        ----------
        config : dict
            Feature configuration dictionary.
        """
        coloc_a = config.get("coloc_a_combo")
        coloc_b = config.get("coloc_b_combo")
        if coloc_a is None or coloc_b is None:
            return
        self._disable_combo_choice(coloc_a, coloc_b.currentText())
        self._disable_combo_choice(coloc_b, coloc_a.currentText())

    def _disable_combo_choice(self, combo: QComboBox, value: str) -> None:
        """Disable a matching option in a combo box.

        Parameters
        ----------
        combo : QComboBox
            Combo box to update.
        value : str
            Value to disable in the combo.
        """
        model = combo.model()
        for index in range(combo.count()):
            item = model.item(index)
            if item is None:
                continue
            item.setEnabled(combo.itemText(index) != value)

    def _make_range_slider(self):
        """Create a horizontal range slider or a placeholder label."""
        if RangeSlider is None:
            return QLabel("Range slider unavailable")
        try:
            return RangeSlider(Qt.Horizontal)
        except TypeError:
            slider = RangeSlider()
            slider.setOrientation(Qt.Horizontal)
            return slider

    def _get_slider_values(self, slider):
        """Return the current min/max values from a range slider."""
        if hasattr(slider, "value"):
            return slider.value()
        if hasattr(slider, "values"):
            return slider.values()
        return None

    def _set_slider_values(self, slider, values) -> None:
        """Set the min/max values on a range slider."""
        if hasattr(slider, "setValue"):
            try:
                slider.setValue(values)
                return
            except TypeError:
                pass
        if hasattr(slider, "setValues"):
            slider.setValues(values)

    def _configure_combo(self, combo: QComboBox) -> None:
        """Apply sizing defaults to combo boxes.

        Parameters
        ----------
        combo : QComboBox
            Combo box to configure.
        """
        combo.setSizeAdjustPolicy(
            QComboBox.AdjustToMinimumContentsLengthWithIcon
        )
        combo.setMinimumContentsLength(8)
        combo.setMinimumWidth(140)
        combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def _clear_layout(self, layout: QVBoxLayout) -> None:
        """Remove all widgets and layouts from a layout.

        Parameters
        ----------
        layout : QVBoxLayout
            Layout to clear.
        """
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            child_layout = item.layout()
            if child_layout is not None:
                self._clear_layout(child_layout)

    def _on_channel_changed(self, config: dict) -> None:
        """Update threshold controls when the channel selection changes.

        Parameters
        ----------
        config : dict
            Feature configuration dictionary.
        """
        combo = config.get("channel_combo")
        checkbox = config.get("threshold_checkbox")
        slider = config.get("threshold_slider")
        min_spin = config.get("threshold_min_spin")
        max_spin = config.get("threshold_max_spin")
        if combo is None or checkbox is None or slider is None:
            return
        container = config.get("threshold_container")
        layer = self._get_image_layer_by_name(combo.currentText())
        if layer is None:
            checkbox.setChecked(False)
            checkbox.setEnabled(False)
            slider.setEnabled(False)
            slider.setVisible(False)
            if min_spin is not None:
                min_spin.setEnabled(False)
            if max_spin is not None:
                max_spin.setEnabled(False)
            if container is not None:
                container.setVisible(False)
            return
        checkbox.setEnabled(True)
        self._set_threshold_range(slider, layer, config)
        self._toggle_threshold(config, checkbox.isChecked())

    def _toggle_threshold(self, config: dict, enabled: bool) -> None:
        """Toggle the threshold range slider visibility.

        Parameters
        ----------
        config : dict
            Feature configuration dictionary.
        enabled : bool
            Whether threshold controls should be visible.
        """
        slider = config.get("threshold_slider")
        container = config.get("threshold_container")
        min_spin = config.get("threshold_min_spin")
        max_spin = config.get("threshold_max_spin")
        if slider is None or container is None:
            return
        slider.setEnabled(enabled)
        slider.setVisible(enabled)
        if min_spin is not None:
            min_spin.setEnabled(enabled)
        if max_spin is not None:
            max_spin.setEnabled(enabled)
        container.setVisible(enabled)

    def _set_threshold_range(self, slider, layer, config: dict | None = None) -> None:
        """Set slider bounds to match the selected image layer.

        Parameters
        ----------
        slider : QWidget
            Range slider widget.
        layer : object
            Napari image layer used to derive min/max values.
        config : dict or None
            Feature configuration dictionary used to update spin boxes.
        """
        if not hasattr(slider, "setMinimum"):
            return
        data = layer.data
        min_val = float(np.nanmin(data))
        max_val = float(np.nanmax(data))
        if min_val == max_val:
            max_val = min_val + 1.0
        if hasattr(slider, "setRange"):
            slider.setRange(min_val, max_val)
        else:
            slider.setMinimum(min_val)
            slider.setMaximum(max_val)
        self._set_slider_values(slider, (min_val, max_val))
        if config is not None:
            min_spin = config.get("threshold_min_spin")
            max_spin = config.get("threshold_max_spin")
            if min_spin is not None:
                min_spin.blockSignals(True)
                min_spin.setRange(min_val, max_val)
                min_spin.setValue(min_val)
                min_spin.blockSignals(False)
            if max_spin is not None:
                max_spin.blockSignals(True)
                max_spin.setRange(min_val, max_val)
                max_spin.setValue(max_val)
                max_spin.blockSignals(False)

    def _on_threshold_slider_changed(self, config: dict, values) -> None:
        """Sync spin boxes when the slider range changes.

        Parameters
        ----------
        config : dict
            Feature configuration dictionary.
        values : tuple
            Range slider values.
        """
        if values is None:
            return
        min_spin = config.get("threshold_min_spin")
        max_spin = config.get("threshold_max_spin")
        if min_spin is None or max_spin is None:
            return
        config["threshold_updating"] = True
        min_spin.blockSignals(True)
        max_spin.blockSignals(True)
        min_spin.setValue(values[0])
        max_spin.setValue(values[1])
        min_spin.blockSignals(False)
        max_spin.blockSignals(False)
        config["threshold_updating"] = False

    def _on_threshold_spin_changed(self, config: dict, which: str, value: float) -> None:
        """Sync the range slider when a spin box changes.

        Parameters
        ----------
        config : dict
            Feature configuration dictionary.
        which : str
            Identifier for the spin box ("min" or "max").
        value : float
            New value for the spin box.
        """
        if config.get("threshold_updating"):
            return
        slider = config.get("threshold_slider")
        min_spin = config.get("threshold_min_spin")
        max_spin = config.get("threshold_max_spin")
        if slider is None or min_spin is None or max_spin is None:
            return
        min_val = min_spin.value()
        max_val = max_spin.value()
        if min_val > max_val:
            if which == "min":
                max_val = min_val
                max_spin.blockSignals(True)
                max_spin.setValue(max_val)
                max_spin.blockSignals(False)
            else:
                min_val = max_val
                min_spin.blockSignals(True)
                min_spin.setValue(min_val)
                min_spin.blockSignals(False)
        config["threshold_updating"] = True
        self._set_slider_values(slider, (min_val, max_val))
        config["threshold_updating"] = False

    def _feature_index(self, config: dict) -> int:
        """Return the 1-based index for a feature config.

        Parameters
        ----------
        config : dict
            Feature configuration dictionary.

        Returns
        -------
        int
            1-based index of the feature.
        """
        return self._feature_configs.index(config) + 1

    def _update_roi_titles(self, config: dict) -> None:
        """Update ROI titles with the current feature index.

        Parameters
        ----------
        config : dict
            Feature configuration dictionary.
        """
        feature_index = self._feature_index(config)
        for roi_index, section in enumerate(config.get("roi_items", []), start=1):
            section.setTitle(f"Feature {feature_index}: ROI {roi_index}")

    def _clear_rois(self, config: dict) -> None:
        """Remove all ROI rows from a feature config.

        Parameters
        ----------
        config : dict
            Feature configuration dictionary.
        """
        roi_layout = config.get("roi_layout")
        if roi_layout is None:
            return
        for roi_section in list(config.get("roi_items", [])):
            roi_layout.removeWidget(roi_section)
            roi_section.deleteLater()
        config["roi_items"].clear()
        self._update_roi_titles(config)
        QTimer.singleShot(0, self._update_features_scroll_height)

    def _update_roi_scroll_height(self, config: dict) -> None:
        """Update ROI scroll area height based on content.

        Parameters
        ----------
        config : dict
            Feature configuration dictionary.
        """
        scroll_area = config.get("roi_scroll_area")
        container = config.get("roi_items_container")
        if scroll_area is None or container is None:
            return
        screen = self.window().screen() if self.window() is not None else None
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

    def _refresh_labels_combo(self, combo: QComboBox) -> None:
        """Populate a labels-layer combo.

        Parameters
        ----------
        combo : QComboBox
            Combo box to populate.
        """
        current = combo.currentText()
        combo.clear()
        if self._viewer is None:
            combo.addItem("Select labels")
            return
        for layer in self._iter_label_layers():
            combo.addItem(layer.name)
        if current:
            index = combo.findText(current)
            if index != -1:
                combo.setCurrentIndex(index)

    def _refresh_shapes_combo(self, combo: QComboBox) -> None:
        """Populate a shapes-layer combo.

        Parameters
        ----------
        combo : QComboBox
            Combo box to populate.
        """
        current = combo.currentText()
        combo.clear()
        if self._viewer is None:
            combo.addItem("Select shapes")
            return
        for layer in self._iter_shapes_layers():
            combo.addItem(layer.name)
        if current:
            index = combo.findText(current)
            if index != -1:
                combo.setCurrentIndex(index)

    def _refresh_image_combo(self, combo: QComboBox) -> None:
        """Populate an image-layer combo.

        Parameters
        ----------
        combo : QComboBox
            Combo box to populate.
        """
        current = combo.currentText()
        combo.clear()
        if self._viewer is None:
            combo.addItem("Select image")
            return
        for layer in self._iter_image_layers():
            combo.addItem(layer.name)
        if current:
            index = combo.findText(current)
            if index != -1:
                combo.setCurrentIndex(index)

    def _iter_label_layers(self) -> list:
        """Return label layers from the viewer."""
        if self._viewer is None:
            return []

        label_layers = []
        for layer in self._viewer.layers:
            if layer.__class__.__name__ == "Labels":
                label_layers.append(layer)
        return label_layers

    def _iter_shapes_layers(self) -> list:
        """Return shapes layers from the viewer."""
        if self._viewer is None:
            return []

        shape_layers = []
        for layer in self._viewer.layers:
            if layer.__class__.__name__ == "Shapes":
                shape_layers.append(layer)
        return shape_layers

    def _iter_image_layers(self) -> list:
        """Return image layers from the viewer."""
        if self._viewer is None:
            return []

        image_layers = []
        for layer in self._viewer.layers:
            if layer.__class__.__name__ == "Image":
                image_layers.append(layer)
        return image_layers

    def _get_image_layer_by_name(self, name: str):
        """Return an image layer by name."""
        if self._viewer is None or not name:
            return None
        for layer in self._iter_image_layers():
            if layer.name == name:
                return layer
        return None
