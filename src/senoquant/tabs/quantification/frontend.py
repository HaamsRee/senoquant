"""Frontend widget for the Quantification tab."""

from qtpy.QtCore import Qt, QTimer
from qtpy.QtGui import QGuiApplication
from qtpy.QtWidgets import (
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
from .features import get_feature_registry


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
        self._feature_registry = get_feature_registry()

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
        type_combo.addItems(self._feature_types())
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
            "roi_section": None,
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
            "feature_handler": None,
        }
        self._feature_configs.append(config)
        name_input.textChanged.connect(self._notify_features_changed)
        type_combo.currentTextChanged.connect(
            lambda _text, cfg=config: self._on_feature_type_changed(cfg)
        )
        self._on_feature_type_changed(config)
        self._notify_features_changed()
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
        config["feature_handler"] = None
        config["roi_section"] = None

        feature_type = config["type_combo"].currentText()
        feature_handler = self._feature_handler_for_type(feature_type, config)
        config["feature_handler"] = feature_handler
        if feature_handler is not None:
            feature_handler.build()
        self._notify_features_changed()


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
        self._notify_features_changed()
        self._features_layout.activate()
        QTimer.singleShot(0, self._update_features_scroll_height)

    def _renumber_features(self) -> None:
        """Renumber feature sections after insertions/removals."""
        for index, config in enumerate(self._feature_configs, start=1):
            config["section"].setTitle(f"Feature {index}")

    def _notify_features_changed(self) -> None:
        """Notify feature handlers that the feature list has changed."""
        for feature_cls in self._feature_registry.values():
            feature_cls.update_type_options(self, self._feature_configs)
        for config in self._feature_configs:
            handler = config.get("feature_handler")
            if handler is not None:
                handler.on_features_changed(self._feature_configs)


    def _feature_types(self) -> list[str]:
        """Return the available feature type names."""
        return list(self._feature_registry.keys())

    def _feature_handler_for_type(self, feature_type: str, config: dict):
        """Return the feature handler for a given feature type.

        Parameters
        ----------
        feature_type : str
            Selected feature type.
        config : dict
            Feature configuration dictionary.

        Returns
        -------
        SenoQuantFeature or None
            Feature handler instance for the selected type.
        """
        feature_cls = self._feature_registry.get(feature_type)
        if feature_cls is None:
            return None
        return feature_cls(self, config)

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
