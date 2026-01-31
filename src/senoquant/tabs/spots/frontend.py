"""Frontend widget for the Spots tab."""
import numpy as np
from qtpy.QtCore import QObject, QThread, Signal
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
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

try:
    from napari.layers import Image, Labels
    from napari.utils.notifications import (
        Notification,
        NotificationSeverity,
        show_console_notification,
    )
except Exception:  # pragma: no cover - optional import for runtime
    Image = None
    Labels = None
    show_console_notification = None
    Notification = None
    NotificationSeverity = None

from senoquant.utils import layer_data_asarray
from .backend import SpotsBackend


def _filter_labels_by_size(
    mask: np.ndarray,
    min_size: int = 0,
    max_size: int = 0,
) -> np.ndarray:
    """Filter a labeled mask by region size.
    
    Parameters
    ----------
    mask : numpy.ndarray
        Labeled mask array.
    min_size : int, optional
        Minimum region size in pixels (0 = no minimum).
    max_size : int, optional
        Maximum region size in pixels (0 = no maximum).
        
    Returns
    -------
    numpy.ndarray
        Filtered labeled mask with regions outside size range removed.
    """
    from skimage.measure import regionprops
    
    if mask is None or mask.size == 0:
        return mask
        
    # If both are 0, no filtering needed
    if min_size == 0 and max_size == 0:
        return mask
        
    # Get region properties
    regions = regionprops(mask)
    if not regions:
        return mask
        
    # Build a mask of labels to keep
    filtered_mask = np.zeros_like(mask)
    for region in regions:
        area = region.area
        keep = True
        
        if min_size > 0 and area < min_size:
            keep = False
        if max_size > 0 and area > max_size:
            keep = False
            
        if keep:
            filtered_mask[mask == region.label] = region.label
            
    return filtered_mask


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
        self._active_workers: list[tuple[QThread, QObject]] = []
        self._min_size_spin = None
        self._max_size_spin = None

        layout = QVBoxLayout()
        layout.addWidget(self._make_detector_section())
        layout.addWidget(self._make_colocalization_section())
        layout.addStretch(1)
        self.setLayout(layout)

        self._refresh_layer_choices()
        self._refresh_label_choices()
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
        form_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self._layer_combo = RefreshingComboBox(
            refresh_callback=self._refresh_layer_choices
        )
        self._configure_combo(self._layer_combo)
        self._detector_combo = QComboBox()
        self._configure_combo(self._detector_combo)
        self._detector_combo.currentTextChanged.connect(
            self._update_detector_settings
        )

        form_layout.addRow("Image layer", self._layer_combo)
        form_layout.addRow("Detector", self._detector_combo)

        section_layout.addLayout(form_layout)
        section_layout.addWidget(self._make_settings_section())
        section_layout.addWidget(self._make_size_filter_section())

        self._run_button = QPushButton("Run")
        self._run_button.clicked.connect(self._run_detector)
        section_layout.addWidget(self._run_button)

        section.setLayout(section_layout)
        return section

    def _make_colocalization_section(self) -> QGroupBox:
        """Build the colocalization visualization section.

        Returns
        -------
        QGroupBox
            Group box containing colocalization controls.
        """
        section = QGroupBox("Visualize colocalization")
        section_layout = QVBoxLayout()

        form_layout = QFormLayout()
        form_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self._coloc_a_combo = RefreshingComboBox(
            refresh_callback=self._refresh_label_choices
        )
        self._configure_combo(self._coloc_a_combo)
        self._coloc_b_combo = RefreshingComboBox(
            refresh_callback=self._refresh_label_choices
        )
        self._configure_combo(self._coloc_b_combo)
        form_layout.addRow("Labels A", self._coloc_a_combo)
        form_layout.addRow("Labels B", self._coloc_b_combo)

        section_layout.addLayout(form_layout)

        self._coloc_run_button = QPushButton("Visualize")
        self._coloc_run_button.clicked.connect(self._run_colocalization)
        section_layout.addWidget(self._coloc_run_button)

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

    def _make_size_filter_section(self) -> QGroupBox:
        """Build the spot size filter section.

        Returns
        -------
        QGroupBox
            Group box containing size filter controls.
        """
        section = QGroupBox("Filter spots by size (pixels)")
        section.setFlat(False)
        
        layout = QFormLayout()
        layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        
        self._min_size_spin = QSpinBox()
        self._min_size_spin.setRange(0, 100000)
        self._min_size_spin.setValue(0)
        
        self._max_size_spin = QSpinBox()
        self._max_size_spin.setRange(0, 100000)
        self._max_size_spin.setValue(0)
        
        layout.addRow("Minimum size", self._min_size_spin)
        layout.addRow("Maximum size", self._max_size_spin)
        
        section.setLayout(layout)
        return section

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

    def _refresh_label_choices(self) -> None:
        """Populate label layer dropdowns from the napari viewer."""
        current_a = self._coloc_a_combo.currentText()
        current_b = self._coloc_b_combo.currentText()
        self._coloc_a_combo.clear()
        self._coloc_b_combo.clear()
        if self._viewer is None:
            self._coloc_a_combo.addItem("Select labels")
            self._coloc_b_combo.addItem("Select labels")
            return

        for layer in self._iter_label_layers():
            self._coloc_a_combo.addItem(layer.name)
            self._coloc_b_combo.addItem(layer.name)

        if current_a:
            index = self._coloc_a_combo.findText(current_a)
            if index != -1:
                self._coloc_a_combo.setCurrentIndex(index)
        if current_b:
            index = self._coloc_b_combo.findText(current_b)
            if index != -1:
                self._coloc_b_combo.setCurrentIndex(index)

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

    def _configure_combo(self, combo: QComboBox) -> None:
        """Apply sizing defaults to combo boxes."""
        combo.setSizeAdjustPolicy(
            QComboBox.AdjustToMinimumContentsLengthWithIcon
        )
        combo.setMinimumContentsLength(20)
        combo.setMinimumWidth(180)
        combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

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
        self._start_background_run(
            run_button=self._run_button,
            run_text="Run",
            detector_name=detector_name,
            run_callable=lambda: detector.run(layer=layer, settings=settings),
            on_success=lambda result: self._handle_run_result(
                layer, detector_name, result
            ),
        )

    def _run_colocalization(self) -> None:
        """Visualize intersections between two label layers."""
        layer_a = self._get_layer_by_name(self._coloc_a_combo.currentText())
        layer_b = self._get_layer_by_name(self._coloc_b_combo.currentText())
        if not self._validate_label_layer(layer_a, "Labels A"):
            return
        if not self._validate_label_layer(layer_b, "Labels B"):
            return

        data_a = layer_data_asarray(layer_a)
        data_b = layer_data_asarray(layer_b)
        if data_a.shape != data_b.shape:
            self._notify("Label layers must have matching shapes.")
            return

        self._start_background_run(
            run_button=self._coloc_run_button,
            run_text="Visualize",
            detector_name="colocalization",
            run_callable=lambda: self._backend.compute_colocalization(
                data_a, data_b
            ),
            on_success=lambda result: self._apply_colocalization_result(
                layer_a, layer_b, result
            ),
        )

    def _apply_colocalization_result(
        self,
        layer_a,
        layer_b,
        result: dict,
    ) -> None:
        """Apply colocalization results to the viewer."""
        if not isinstance(result, dict):
            return
        points = result.get("points")
        if points is None or len(points) == 0:
            self._notify("No overlapping labels found.")
            return
        self._add_colocalization_points(layer_a, layer_b, points)

    def _add_colocalization_points(
        self,
        layer_a,
        layer_b,
        points: np.ndarray,
    ) -> None:
        """Add colocalization points as yellow circles."""
        if self._viewer is None:
            return
        name = f"{layer_a.name}_{layer_b.name}_colocalization"
        if name in self._viewer.layers:
            self._viewer.layers.remove(name)
        self._viewer.add_points(
            points,
            name=name,
            face_color="yellow",
            symbol="ring",
            size=6,
        )

    def _start_background_run(
        self,
        run_button: QPushButton,
        run_text: str,
        detector_name: str,
        run_callable,
        on_success,
    ) -> None:
        """Run a detector in a background thread and manage UI state.

        Parameters
        ----------
        run_button : QPushButton
            Button to disable while the background task runs.
        run_text : str
            Label text to restore after completion.
        detector_name : str
            Detector name used for error messaging.
        run_callable : callable
            Callable that executes the detector run.
        on_success : callable
            Callback invoked with the run result dictionary.
        """
        run_button.setEnabled(False)
        run_button.setText("Running...")

        thread = QThread(self)
        worker = _RunWorker(run_callable)
        worker.moveToThread(thread)

        def handle_success(result: dict) -> None:
            on_success(result)
            self._finish_background_run(run_button, run_text, thread, worker)

        def handle_error(message: str) -> None:
            self._notify(f"Run failed for '{detector_name}': {message}")
            self._finish_background_run(run_button, run_text, thread, worker)

        thread.started.connect(worker.run)
        worker.finished.connect(handle_success)
        worker.error.connect(handle_error)
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(worker.deleteLater)

        self._active_workers.append((thread, worker))
        thread.start()

    def _finish_background_run(
        self,
        run_button: QPushButton,
        run_text: str,
        thread: QThread,
        worker: QObject,
    ) -> None:
        """Restore UI state after a background run completes.

        Parameters
        ----------
        run_button : QPushButton
            Button to restore after completion.
        run_text : str
            Label text to restore on the button.
        thread : QThread
            Background thread being torn down.
        worker : QObject
            Worker object associated with the thread.
        """
        run_button.setEnabled(True)
        run_button.setText(run_text)
        try:
            self._active_workers.remove((thread, worker))
        except ValueError:
            pass

    def _handle_run_result(self, layer, detector_name: str, result: dict) -> None:
        """Handle detector output and update the viewer."""
        if not isinstance(result, dict):
            return
        mask = result.get("mask")
        if mask is not None:
            filtered_mask = self._apply_size_filter(mask)
            self._add_labels_layer(layer, filtered_mask, detector_name)

    def _add_labels_layer(self, source_layer, mask, detector_name: str) -> None:
        """Add a labels layer for the detector mask."""
        if self._viewer is None or source_layer is None:
            return
        name = self._spot_label_name(source_layer, detector_name)
        self._viewer.add_labels(mask, name=name)
        labels_layer = self._viewer.layers[name]
        labels_layer.contour = 1

    def _apply_size_filter(self, mask: np.ndarray) -> np.ndarray:
        """Filter spots by size based on min/max settings.
        
        Parameters
        ----------
        mask : numpy.ndarray
            Labeled spot mask from detector.
            
        Returns
        -------
        numpy.ndarray
            Filtered labeled mask.
        """
        if self._min_size_spin is None or self._max_size_spin is None:
            return mask
            
        min_size = self._min_size_spin.value()
        max_size = self._max_size_spin.value()
        
        # If both are 0 (disabled), return original mask
        if min_size == 0 and max_size == 0:
            return mask
            
        return _filter_labels_by_size(mask, min_size, max_size)

    def _spot_label_name(self, source_layer, detector_name: str) -> str:
        """Return a standardized spot labels layer name."""
        layer_name = getattr(source_layer, "name", "")
        layer_name = layer_name.strip() if isinstance(layer_name, str) else ""
        if layer_name:
            return f"{layer_name}_{detector_name}_spot_labels"
        return f"{detector_name}_spot_labels"

    def _notify(self, message: str) -> None:
        """Send a warning notification to the napari console.

        Parameters
        ----------
        message : str
            Notification message to display.
        """
        if (
            show_console_notification is not None
            and Notification is not None
            and NotificationSeverity is not None
        ):
            show_console_notification(
                Notification(message, severity=NotificationSeverity.WARNING)
            )

    def _get_layer_by_name(self, name: str):
        """Return a viewer layer with the given name, if it exists."""
        if self._viewer is None:
            return None
        for layer in self._viewer.layers:
            if layer.name == name:
                return layer
        return None

    def _validate_label_layer(self, layer, label: str) -> bool:
        """Validate that a layer is a Labels layer.

        Parameters
        ----------
        layer : object or None
            Napari layer to validate.
        label : str
            User-facing label for notifications.

        Returns
        -------
        bool
            True if the layer is a Labels layer.
        """
        if layer is None:
            self._notify(f"{label} is not selected.")
            return False
        if Labels is not None:
            if not isinstance(layer, Labels):
                self._notify(f"{label} must be a Labels layer.")
                return False
        else:
            if layer.__class__.__name__ != "Labels":
                self._notify(f"{label} must be a Labels layer.")
                return False
        return True

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

    def _iter_label_layers(self) -> list:
        if self._viewer is None:
            return []

        label_layers = []
        for layer in self._viewer.layers:
            if Labels is not None:
                if isinstance(layer, Labels):
                    label_layers.append(layer)
            else:
                if layer.__class__.__name__ == "Labels":
                    label_layers.append(layer)
        return label_layers


class _RunWorker(QObject):
    """Worker that executes a callable in a background thread."""

    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, run_callable) -> None:
        """Initialize the worker with a callable.

        Parameters
        ----------
        run_callable : callable
            Callable to execute on the worker thread.
        """
        super().__init__()
        self._run_callable = run_callable

    def run(self) -> None:
        """Execute the callable and emit results."""
        try:
            result = self._run_callable()
        except Exception as exc:  # pragma: no cover - runtime error path
            self.error.emit(str(exc))
            return
        self.finished.emit(result)
