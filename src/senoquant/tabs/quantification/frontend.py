"""Frontend widget for the Quantification tab."""

from qtpy.QtCore import Qt, QTimer
from qtpy.QtGui import QGuiApplication
from qtpy.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .backend import QuantificationBackend


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
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._features_scroll_area = scroll_area

        features_container = QWidget()
        self._features_container = features_container
        features_container.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Fixed
        )
        self._features_layout = QVBoxLayout()
        self._features_layout.setContentsMargins(0, 0, 0, 0)
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
        """Resize handler to keep the features list at half the window height."""
        super().resizeEvent(event)
        self._update_features_scroll_height()

    def _update_features_scroll_height(self) -> None:
        """Update the features scroll area height based on the window size."""
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
        left_layout = QVBoxLayout()
        right_layout = QVBoxLayout()

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

        dynamic_container = QWidget()
        dynamic_layout = QVBoxLayout()
        dynamic_layout.setContentsMargins(0, 0, 0, 0)
        dynamic_container.setLayout(dynamic_layout)
        left_layout.addWidget(dynamic_container)

        content_layout.addLayout(left_layout, 2)
        content_layout.addLayout(right_layout, 1)
        section_layout.addLayout(content_layout)

        delete_button = QPushButton("Delete")
        delete_button.clicked.connect(
            lambda _checked=False, section=feature_section: self._remove_feature(
                section
            )
        )
        section_layout.addWidget(delete_button)
        feature_section.setLayout(section_layout)
        feature_section.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Fixed
        )

        self._features_layout.addWidget(feature_section)
        config = {
            "section": feature_section,
            "name_input": name_input,
            "type_combo": type_combo,
            "dynamic_layout": dynamic_layout,
            "roi_checkbox": None,
            "roi_container": None,
            "roi_layout": None,
            "roi_scroll_area": None,
            "roi_items_container": None,
            "roi_items": [],
            "coloc_a_combo": None,
            "coloc_b_combo": None,
            "right_layout": right_layout,
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
        """Update a feature section when its type changes."""
        dynamic_layout = config["dynamic_layout"]
        self._clear_layout(dynamic_layout)
        right_layout = config.get("right_layout")
        if right_layout is not None:
            self._clear_layout(right_layout)
        config["roi_checkbox"] = None
        config["roi_container"] = None
        config["roi_layout"] = None
        config["roi_scroll_area"] = None
        config["roi_items_container"] = None
        config["roi_items"] = []
        config["coloc_a_combo"] = None
        config["coloc_b_combo"] = None

        feature_type = config["type_combo"].currentText()
        if feature_type in ("Marker", "Spots"):
            label_text = "Segmentation labels" if feature_type == "Marker" else "Spots"
            form_layout = QFormLayout()
            form_layout.setFieldGrowthPolicy(
                QFormLayout.AllNonFixedFieldsGrow
            )

            labels_combo = RefreshingComboBox(
                refresh_callback=lambda combo_ref=None: self._refresh_labels_combo(
                    labels_combo
                )
            )
            self._configure_combo(labels_combo)
            form_layout.addRow(label_text, labels_combo)
            dynamic_layout.addLayout(form_layout)

            roi_checkbox = QCheckBox("ROIs")
            roi_checkbox.toggled.connect(
                lambda checked, cfg=config: self._toggle_roi_section(cfg, checked)
            )
            dynamic_layout.addWidget(roi_checkbox)

            roi_container = QWidget()
            roi_container.setVisible(False)
            roi_container_layout = QVBoxLayout()
            roi_container_layout.setContentsMargins(0, 0, 0, 0)
            roi_container.setLayout(roi_container_layout)

            roi_scroll_area = QScrollArea()
            roi_scroll_area.setWidgetResizable(True)
            roi_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            roi_scroll_area.setSizePolicy(
                QSizePolicy.Expanding, QSizePolicy.Fixed
            )

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
            form_layout.addRow("Labels A", coloc_a)
            form_layout.addRow("Labels B", coloc_b)
            dynamic_layout.addLayout(form_layout)
            config["coloc_a_combo"] = coloc_a
            config["coloc_b_combo"] = coloc_b
            self._update_colocalization_options()

    def _toggle_roi_section(self, config: dict, enabled: bool) -> None:
        """Toggle the ROI section for a feature."""
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
        QTimer.singleShot(0, lambda cfg=config: self._update_roi_scroll_height(cfg))

    def _add_roi_row(self, config: dict) -> None:
        """Add a new ROI row to a feature."""
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
        roi_name.setMinimumWidth(180)
        roi_name.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        shapes_combo = RefreshingComboBox(
            refresh_callback=lambda combo_ref=None: self._refresh_shapes_combo(
                shapes_combo
            )
        )
        self._configure_combo(shapes_combo)

        roi_type = QComboBox()
        roi_type.addItems(["Include", "Exclude"])
        self._configure_combo(roi_type)

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
        """Remove an ROI row and disable ROI selection if empty."""
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
        """Remove a feature section and renumber remaining entries."""
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
        """Update colocalization feature dropdown options."""
        for key in ("coloc_a_combo", "coloc_b_combo"):
            combo = config.get(key)
            if combo is None:
                continue
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

    def _configure_combo(self, combo: QComboBox) -> None:
        """Apply sizing defaults to combo boxes."""
        combo.setSizeAdjustPolicy(
            QComboBox.AdjustToMinimumContentsLengthWithIcon
        )
        combo.setMinimumContentsLength(8)
        combo.setMinimumWidth(140)
        combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def _clear_layout(self, layout: QVBoxLayout) -> None:
        """Remove all widgets and layouts from a layout."""
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            child_layout = item.layout()
            if child_layout is not None:
                self._clear_layout(child_layout)

    def _feature_index(self, config: dict) -> int:
        """Return the 1-based index for a feature config."""
        return self._feature_configs.index(config) + 1

    def _update_roi_titles(self, config: dict) -> None:
        """Update ROI titles with the current feature index."""
        feature_index = self._feature_index(config)
        for roi_index, section in enumerate(config.get("roi_items", []), start=1):
            section.setTitle(f"Feature {feature_index}: ROI {roi_index}")

    def _clear_rois(self, config: dict) -> None:
        """Remove all ROI rows from a feature config."""
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
        """Update ROI scroll area height based on content."""
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
        """Populate a labels-layer combo."""
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
        """Populate a shapes-layer combo."""
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

    def _iter_label_layers(self) -> list:
        if self._viewer is None:
            return []

        label_layers = []
        for layer in self._viewer.layers:
            if layer.__class__.__name__ == "Labels":
                label_layers.append(layer)
        return label_layers

    def _iter_shapes_layers(self) -> list:
        if self._viewer is None:
            return []

        shape_layers = []
        for layer in self._viewer.layers:
            if layer.__class__.__name__ == "Shapes":
                shape_layers.append(layer)
        return shape_layers
