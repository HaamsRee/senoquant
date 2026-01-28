"""Frontend widget for the Batch tab."""

from __future__ import annotations

from pathlib import Path

from qtpy.QtCore import QObject, QThread, Signal
from qtpy.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

try:
    from napari.utils.notifications import (
        Notification,
        NotificationSeverity,
        show_console_notification,
    )
except Exception:  # pragma: no cover - optional import for runtime
    show_console_notification = None
    Notification = None
    NotificationSeverity = None

from .backend import BatchBackend
from ..segmentation.backend import SegmentationBackend
from ..spots.backend import SpotsBackend


class RefreshingComboBox(QComboBox):
    """Combo box that refreshes its items when opened."""

    def __init__(self, refresh_callback=None, parent=None) -> None:
        super().__init__(parent)
        self._refresh_callback = refresh_callback

    def showPopup(self) -> None:
        if self._refresh_callback is not None:
            self._refresh_callback()
        super().showPopup()


class BatchTab(QWidget):
    """Batch processing tab for running segmentation and spot detection."""

    def __init__(
        self,
        backend: BatchBackend | None = None,
        napari_viewer=None,
    ) -> None:
        super().__init__()
        self._viewer = napari_viewer
        self._segmentation_backend = SegmentationBackend()
        self._spots_backend = SpotsBackend()
        self._backend = backend or BatchBackend(
            segmentation_backend=self._segmentation_backend,
            spots_backend=self._spots_backend,
        )
        self._active_workers: list[tuple[QThread, QObject]] = []

        layout = QVBoxLayout()
        layout.addWidget(self._make_input_section())
        layout.addWidget(self._make_processing_section())
        layout.addWidget(self._make_output_section())

        self._run_button = QPushButton("Run batch")
        self._run_button.clicked.connect(self._run_batch)
        layout.addWidget(self._run_button)

        self._status_label = QLabel("Ready")
        self._status_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout.addWidget(self._status_label)
        layout.addStretch(1)
        self.setLayout(layout)

        self._refresh_segmentation_models()
        self._refresh_detectors()
        self._update_processing_state()

    def _make_input_section(self) -> QGroupBox:
        section = QGroupBox("Input")
        section_layout = QVBoxLayout()
        form_layout = QFormLayout()
        form_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self._input_path = QLineEdit()
        self._input_path.setPlaceholderText("Folder with images")
        browse_button = QPushButton("Browse")
        browse_button.clicked.connect(self._select_input_path)
        input_row = QHBoxLayout()
        input_row.setContentsMargins(0, 0, 0, 0)
        input_row.addWidget(self._input_path)
        input_row.addWidget(browse_button)
        input_widget = QWidget()
        input_widget.setLayout(input_row)

        self._extensions = QLineEdit()
        self._extensions.setPlaceholderText(".tif,.tiff,.ome.tif,.png,.jpg")
        self._extensions.setText(
            ".tif,.tiff,.ome.tif,.ome.tiff,.png,.jpg,.jpeg,.czi,.nd2,.lif,.zarr"
        )

        self._include_subfolders = QCheckBox("Include subfolders")
        self._process_scenes = QCheckBox("Process all scenes")

        form_layout.addRow("Input folder", input_widget)
        form_layout.addRow("Extensions", self._extensions)
        form_layout.addRow("", self._include_subfolders)
        form_layout.addRow("", self._process_scenes)

        section_layout.addLayout(form_layout)
        section.setLayout(section_layout)
        return section

    def _make_processing_section(self) -> QGroupBox:
        section = QGroupBox("Processing")
        section_layout = QVBoxLayout()
        form_layout = QFormLayout()
        form_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self._segmentation_enabled = QCheckBox("Run segmentation")
        self._segmentation_enabled.setChecked(True)
        self._segmentation_enabled.toggled.connect(self._update_processing_state)
        self._segmentation_model_combo = RefreshingComboBox(
            refresh_callback=self._refresh_segmentation_models
        )
        self._segmentation_channel = QSpinBox()
        self._segmentation_channel.setMinimum(0)
        self._segmentation_channel.setMaximum(128)

        self._spots_enabled = QCheckBox("Run spot detection")
        self._spots_enabled.setChecked(True)
        self._spots_enabled.toggled.connect(self._update_processing_state)
        self._spot_detector_combo = RefreshingComboBox(
            refresh_callback=self._refresh_detectors
        )
        self._spot_channel = QSpinBox()
        self._spot_channel.setMinimum(0)
        self._spot_channel.setMaximum(128)

        form_layout.addRow(self._segmentation_enabled)
        form_layout.addRow("Segmentation model", self._segmentation_model_combo)
        form_layout.addRow("Segmentation channel", self._segmentation_channel)
        form_layout.addRow(self._spots_enabled)
        form_layout.addRow("Spot detector", self._spot_detector_combo)
        form_layout.addRow("Spot channel", self._spot_channel)

        section_layout.addLayout(form_layout)
        section.setLayout(section_layout)
        return section

    def _make_output_section(self) -> QGroupBox:
        section = QGroupBox("Output")
        section_layout = QVBoxLayout()
        form_layout = QFormLayout()
        form_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self._output_path = QLineEdit()
        self._output_path.setPlaceholderText("Output folder")
        browse_button = QPushButton("Browse")
        browse_button.clicked.connect(self._select_output_path)
        output_row = QHBoxLayout()
        output_row.setContentsMargins(0, 0, 0, 0)
        output_row.addWidget(self._output_path)
        output_row.addWidget(browse_button)
        output_widget = QWidget()
        output_widget.setLayout(output_row)

        self._output_format = QComboBox()
        self._output_format.addItems(["tif", "npy"])

        self._overwrite = QCheckBox("Overwrite existing outputs")

        form_layout.addRow("Output folder", output_widget)
        form_layout.addRow("Format", self._output_format)
        form_layout.addRow("", self._overwrite)

        section_layout.addLayout(form_layout)
        section.setLayout(section_layout)
        return section

    def _select_input_path(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select input folder")
        if path:
            self._input_path.setText(path)

    def _select_output_path(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select output folder")
        if path:
            self._output_path.setText(path)

    def _refresh_segmentation_models(self) -> None:
        names = self._segmentation_backend.list_model_names(task="nuclear")
        self._segmentation_model_combo.clear()
        if names:
            self._segmentation_model_combo.addItems(names)
            self._segmentation_model_combo.setEnabled(True)
        else:
            self._segmentation_model_combo.addItem("(no models)")
            self._segmentation_model_combo.setEnabled(False)

    def _refresh_detectors(self) -> None:
        names = self._spots_backend.list_detector_names()
        self._spot_detector_combo.clear()
        if names:
            self._spot_detector_combo.addItems(names)
            self._spot_detector_combo.setEnabled(True)
        else:
            self._spot_detector_combo.addItem("(no detectors)")
            self._spot_detector_combo.setEnabled(False)

    def _update_processing_state(self) -> None:
        seg_enabled = self._segmentation_enabled.isChecked()
        spot_enabled = self._spots_enabled.isChecked()
        seg_available = (
            seg_enabled
            and not self._segmentation_model_combo.currentText().startswith("(")
        )
        spot_available = (
            spot_enabled
            and not self._spot_detector_combo.currentText().startswith("(")
        )
        self._segmentation_model_combo.setEnabled(seg_available)
        self._segmentation_channel.setEnabled(seg_available)
        self._spot_detector_combo.setEnabled(spot_available)
        self._spot_channel.setEnabled(spot_available)

    def _run_batch(self) -> None:
        input_path = self._input_path.text().strip()
        if not input_path:
            self._notify("Select an input folder.")
            return
        if not Path(input_path).exists():
            self._notify("Input folder does not exist.")
            return

        output_path = self._output_path.text().strip()
        if not output_path:
            output_path = str(Path(input_path) / "batch-output")
            self._output_path.setText(output_path)

        segmentation_model = None
        if self._segmentation_enabled.isChecked() and self._segmentation_model_combo.isEnabled():
            segmentation_model = self._segmentation_model_combo.currentText().strip()
            if segmentation_model.startswith("("):
                segmentation_model = None

        spot_detector = None
        if self._spots_enabled.isChecked() and self._spot_detector_combo.isEnabled():
            spot_detector = self._spot_detector_combo.currentText().strip()
            if spot_detector.startswith("("):
                spot_detector = None

        if not segmentation_model and not spot_detector:
            self._notify("Enable segmentation and/or spot detection.")
            return

        extensions = [
            ext.strip()
            for ext in self._extensions.text().split(",")
            if ext.strip()
        ]

        self._start_background_run(
            run_button=self._run_button,
            run_text="Run batch",
            run_callable=lambda: self._backend.process_folder(
                input_path,
                output_path,
                segmentation_model=segmentation_model,
                segmentation_channel=self._segmentation_channel.value(),
                spot_detector=spot_detector,
                spot_channel=self._spot_channel.value(),
                extensions=extensions or None,
                include_subfolders=self._include_subfolders.isChecked(),
                output_format=self._output_format.currentText(),
                overwrite=self._overwrite.isChecked(),
                process_all_scenes=self._process_scenes.isChecked(),
            ),
            on_success=self._handle_batch_complete,
        )

    def _start_background_run(
        self,
        *,
        run_button: QPushButton,
        run_text: str,
        run_callable,
        on_success,
    ) -> None:
        run_button.setEnabled(False)
        run_button.setText("Running...")
        self._status_label.setText("Running batch...")

        worker = _RunWorker(run_callable)
        thread = QThread()
        worker.moveToThread(thread)
        worker.finished.connect(lambda result: on_success(result))
        worker.finished.connect(
            lambda: self._finish_background_run(run_button, run_text, thread, worker)
        )
        worker.failed.connect(
            lambda message: self._notify(f"Batch run failed: {message}")
        )
        worker.failed.connect(
            lambda: self._finish_background_run(run_button, run_text, thread, worker)
        )
        thread.started.connect(worker.run)
        thread.start()
        self._active_workers.append((thread, worker))

    def _finish_background_run(
        self,
        run_button: QPushButton,
        run_text: str,
        thread: QThread,
        worker: QObject,
    ) -> None:
        run_button.setEnabled(True)
        run_button.setText(run_text)
        self._status_label.setText("Ready")
        thread.quit()
        thread.wait()
        try:
            self._active_workers.remove((thread, worker))
        except ValueError:
            pass

    def _handle_batch_complete(self, summary) -> None:
        message = (
            f"Batch complete: {summary.processed} processed, "
            f"{summary.failed} failed, {summary.skipped} skipped."
        )
        self._notify(message)

    def _notify(self, message: str) -> None:
        if (
            show_console_notification is not None
            and Notification is not None
            and NotificationSeverity is not None
        ):
            show_console_notification(
                Notification(message, severity=NotificationSeverity.WARNING)
            )
        self._status_label.setText(message)


class _RunWorker(QObject):
    """Worker wrapper for background batch execution."""

    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, run_callable) -> None:
        super().__init__()
        self._run_callable = run_callable

    def run(self) -> None:
        try:
            result = self._run_callable()
        except Exception as exc:  # pragma: no cover - runtime error path
            self.failed.emit(str(exc))
            return
        self.finished.emit(result)
