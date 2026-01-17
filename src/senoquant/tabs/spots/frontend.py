"""Frontend widget for the Spots tab."""
from qtpy.QtGui import QPalette
from qtpy.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

try:
    from napari.layers import Image
except Exception:  # pragma: no cover - optional import for runtime
    Image = None

from .backend import SpotsBackend


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


class SpotsTab(QWidget):
    """Spots tab UI for spot detectors.

    Parameters
    ----------
    backend : SpotsBackend or None
        Backend instance used to discover and load detectors.
    napari_viewer : object or None
        Napari viewer used to populate layer choices.
    """

    def __init__(
        self,
        backend: SpotsBackend | None = None,
        napari_viewer=None,
    ) -> None:
        super().__init__()
        self._backend = backend or SpotsBackend()
        self._viewer = napari_viewer
        self._settings_widgets = {}
        self._settings_meta = {}

        layout = QVBoxLayout()
        layout.addWidget(self._make_detector_section())
        layout.addStretch(1)
        self.setLayout(layout)

        self._refresh_layer_choices()
        self._refresh_detector_choices()
        self._update_detector_settings(self._detector_combo.currentText())


    def _make_detector_section(self) -> QGroupBox:
        """Build the detector UI section.

        Returns
        -------
        QGroupBox
            Group box containing spot detector controls.
        """
        section = QGroupBox("Spot detection")
        section_layout = QVBoxLayout()

        form_layout = QFormLayout()
        self._layer_combo = RefreshingComboBox(
            refresh_callback=self._refresh_layer_choices
        )
        self._detector_combo = QComboBox()
        self._detector_combo.currentTextChanged.connect(
            self._update_detector_settings
        )

        form_layout.addRow("Image layer", self._layer_combo)
        form_layout.addRow("Detector", self._detector_combo)

        section_layout.addLayout(form_layout)
        section_layout.addWidget(self._make_settings_section())

        self._run_button = QPushButton("Run")
        self._run_button.clicked.connect(self._run_detector)
        section_layout.addWidget(self._run_button)

        section.setLayout(section_layout)
        return section

    def _make_settings_section(self) -> QGroupBox:
        """Build the detector settings section container.

        Returns
        -------
        QGroupBox
            Group box containing detector-specific settings.
        """
        return self._make_titled_section("Detector settings")

    def _make_titled_section(self, title: str) -> QGroupBox:
        """Create a titled box that mimics a group box ring.

        Parameters
        ----------
        title : str
            Title displayed on the ring.

        Returns
        -------
        QGroupBox
            Group box containing a framed content area.
        """
        section = QGroupBox(title)
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
        frame.setObjectName("titled-section-frame")
        frame.setStyleSheet(
            "QFrame#titled-section-frame {"
            "  border: 1px solid palette(mid);"
            "  border-radius: 4px;"
            "}"
        )

        self._settings_layout = QVBoxLayout()
        self._settings_layout.setContentsMargins(10, 12, 10, 10)
        frame.setLayout(self._settings_layout)

        section_layout = QVBoxLayout()
        section_layout.setContentsMargins(8, 12, 8, 4)
        section_layout.addWidget(frame)
        section.setLayout(section_layout)

        return section

    def _refresh_layer_choices(self) -> None:
        """Populate the image layer dropdown from the napari viewer."""
        current = self._layer_combo.currentText()
        self._layer_combo.clear()
        if self._viewer is None:
            self._layer_combo.addItem("Select a layer")
            return

        for layer in self._iter_image_layers():
            self._layer_combo.addItem(layer.name)

        if current:
            index = self._layer_combo.findText(current)
            if index != -1:
                self._layer_combo.setCurrentIndex(index)

    def _refresh_detector_choices(self) -> None:
        """Populate the detector dropdown from available detector folders."""
        self._detector_combo.clear()
        names = self._backend.list_detector_names()
        if not names:
            self._detector_combo.addItem("No detectors found")
            return
        self._detector_combo.addItems(names)

    def _update_detector_settings(self, detector_name: str) -> None:
        """Rebuild the detector settings area for the selected detector.

        Parameters
        ----------
        detector_name : str
            Selected detector name from the dropdown.
        """
        while self._settings_layout.count():
            item = self._settings_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        if not detector_name or detector_name == "No detectors found":
            self._settings_layout.addWidget(
                QLabel("Select a detector to configure its settings.")
            )
            return

        detector = self._backend.get_detector(detector_name)
        self._settings_widgets.clear()
        self._settings_meta.clear()
        form_layout = self._build_detector_settings(detector)
        if form_layout is None:
            self._settings_layout.addWidget(
                QLabel(f"No settings defined for '{detector_name}'.")
            )
        else:
            form_container = QWidget()
            form_container.setAutoFillBackground(True)
            form_container.setBackgroundRole(QPalette.Window)
            form_container.setLayout(form_layout)
            self._settings_layout.addWidget(form_container)
            self._apply_setting_dependencies()

    def _build_detector_settings(self, detector) -> QFormLayout | None:
        """Build detector settings controls from metadata.

        Parameters
        ----------
        detector : SenoQuantSpotDetector
            Detector wrapper providing settings metadata.

        Returns
        -------
        QFormLayout or None
            Form layout containing controls or None if no settings exist.
        """
        settings = detector.list_settings()
        if not settings:
            return None

        form_layout = QFormLayout()
        for setting in settings:
            setting_type = setting.get("type")
            label = setting.get("label", setting.get("key", "Setting"))
            key = setting.get("key", label)
            self._settings_meta[key] = setting

            if setting_type == "float":
                widget = QDoubleSpinBox()
                decimals = int(setting.get("decimals", 1))
                widget.setDecimals(decimals)
                widget.setRange(
                    float(setting.get("min", 0.0)),
                    float(setting.get("max", 1.0)),
                )
                widget.setSingleStep(0.1)
                widget.setValue(float(setting.get("default", 0.0)))
                self._settings_widgets[key] = widget
                form_layout.addRow(label, widget)
            elif setting_type == "int":
                widget = QSpinBox()
                widget.setRange(
                    int(setting.get("min", 0)),
                    int(setting.get("max", 100)),
                )
                widget.setSingleStep(1)
                widget.setValue(int(setting.get("default", 0)))
                self._settings_widgets[key] = widget
                form_layout.addRow(label, widget)
            elif setting_type == "bool":
                widget = QCheckBox()
                widget.setChecked(bool(setting.get("default", False)))
                widget.toggled.connect(self._apply_setting_dependencies)
                self._settings_widgets[key] = widget
                form_layout.addRow(label, widget)
            else:
                form_layout.addRow(label, QLabel("Unsupported setting type"))

        return form_layout

    def _collect_settings(self) -> dict:
        """Collect current values from the settings widgets."""
        values = {}
        for key, widget in self._settings_widgets.items():
            if hasattr(widget, "value"):
                values[key] = widget.value()
            elif isinstance(widget, QCheckBox):
                values[key] = widget.isChecked()
        return values

    def _apply_setting_dependencies(self) -> None:
        """Apply enabled/disabled relationships between settings."""
        for key, setting in self._settings_meta.items():
            widget = self._settings_widgets.get(key)
            if widget is None:
                continue

            enabled_by = setting.get("enabled_by")
            disabled_by = setting.get("disabled_by")

            if enabled_by:
                controller = self._settings_widgets.get(enabled_by)
                if isinstance(controller, QCheckBox):
                    widget.setEnabled(controller.isChecked())
            if disabled_by:
                controller = self._settings_widgets.get(disabled_by)
                if isinstance(controller, QCheckBox):
                    widget.setEnabled(not controller.isChecked())

    def _run_detector(self) -> None:
        """Run the selected detector with the current settings."""
        detector_name = self._detector_combo.currentText()
        if not detector_name or detector_name == "No detectors found":
            return
        detector = self._backend.get_detector(detector_name)
        layer = self._get_layer_by_name(self._layer_combo.currentText())
        settings = self._collect_settings()
        detector.run(layer=layer, settings=settings)

    def _get_layer_by_name(self, name: str):
        """Return a viewer layer with the given name, if it exists."""
        if self._viewer is None:
            return None
        for layer in self._viewer.layers:
            if layer.name == name:
                return layer
        return None

    def _iter_image_layers(self) -> list:
        if self._viewer is None:
            return []

        image_layers = []
        for layer in self._viewer.layers:
            if Image is not None:
                if isinstance(layer, Image):
                    image_layers.append(layer)
            else:
                if layer.__class__.__name__ == "Image":
                    image_layers.append(layer)
        return image_layers
