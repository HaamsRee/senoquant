"""Frontend widget for the Prediction tab."""

from __future__ import annotations

from qtpy.QtCore import QObject, QThread, Signal
from qtpy.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from senoquant.tabs.prediction.backend import PredictionBackend

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


class PredictionTab(QWidget):
    """Prediction tab UI for deep-learning prediction models.

    Parameters
    ----------
    backend : PredictionBackend or None
        Backend instance used to discover and run prediction models.
    napari_viewer : object or None
        napari viewer passed to models during runs.
    """

    def __init__(
        self,
        backend: PredictionBackend | None = None,
        napari_viewer=None,
    ) -> None:
        super().__init__()
        self._backend = backend or PredictionBackend()
        self._viewer = napari_viewer
        self._model_widget = None
        self._active_workers: list[tuple[QThread, QObject]] = []

        layout = QVBoxLayout()

        model_selector_layout = QFormLayout()
        model_selector_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self._model_combo = QComboBox()
        self._configure_combo(self._model_combo)
        self._model_combo.currentTextChanged.connect(self._update_model_widget)
        model_selector_layout.addRow("Select model", self._model_combo)
        layout.addLayout(model_selector_layout)

        layout.addWidget(self._make_model_section())
        self._run_button = QPushButton("Run")
        self._run_button.clicked.connect(self._run_prediction)
        layout.addWidget(self._run_button)
        layout.addStretch(1)
        self.setLayout(layout)

        self._refresh_model_choices()
        self._update_model_widget(self._model_combo.currentText())

    def _make_model_section(self) -> QGroupBox:
        """Build the model UI section container."""
        section = QGroupBox("Model interface")
        section_layout = QVBoxLayout()

        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)
        frame.setFrameShadow(QFrame.Plain)
        frame.setObjectName("prediction-model-widget-frame")
        frame.setStyleSheet(
            "QFrame#prediction-model-widget-frame {"
            "  border: 1px solid palette(mid);"
            "  border-radius: 4px;"
            "}"
        )

        self._model_widget_layout = QVBoxLayout()
        self._model_widget_layout.setContentsMargins(10, 10, 10, 10)
        frame.setLayout(self._model_widget_layout)
        section_layout.addWidget(frame)

        section.setLayout(section_layout)
        return section

    def _refresh_model_choices(self) -> None:
        """Populate prediction-model dropdown from discovered model folders."""
        self._model_combo.clear()
        names = self._backend.list_model_names()
        if not names:
            self._model_combo.addItem("No models found")
            return
        self._model_combo.addItems(names)

    def _update_model_widget(self, model_name: str) -> None:
        """Swap in the selected model's custom Qt widget."""
        self._clear_layout(self._model_widget_layout)
        self._model_widget = None

        if not model_name or model_name == "No models found":
            self._model_widget_layout.addWidget(
                QLabel("Select a model to configure prediction settings.")
            )
            return

        model = self._backend.get_model(model_name)
        widget = model.build_widget(parent=self, viewer=self._viewer)
        if widget is None:
            self._model_widget_layout.addWidget(
                QLabel(f"Model '{model_name}' does not define a custom widget.")
            )
            return

        self._model_widget = widget
        self._model_widget_layout.addWidget(widget)

    def _run_prediction(self) -> None:
        """Run the selected prediction model with current UI state."""
        model_name = self._model_combo.currentText()
        if not model_name or model_name == "No models found":
            return

        model = self._backend.get_model(model_name)
        settings = model.collect_widget_settings(self._model_widget)

        self._start_background_run(
            run_button=self._run_button,
            run_text="Run",
            model_name=model_name,
            run_callable=lambda: self._backend.run_model(
                model_name=model_name,
                viewer=self._viewer,
                settings=settings,
            ),
            on_success=lambda result: self._handle_run_result(
                model_name,
                result,
            ),
        )

    def _handle_run_result(self, model_name: str, result: dict) -> None:
        """Push prediction outputs to viewer and notify when no layers were added."""
        added = self._backend.push_layers_to_viewer(
            viewer=self._viewer,
            source_layer=None,
            model_name=model_name,
            result=result,
        )
        if not added:
            self._notify(f"Prediction model '{model_name}' did not produce any layers.")

    def _start_background_run(
        self,
        run_button: QPushButton,
        run_text: str,
        model_name: str,
        run_callable,
        on_success,
    ) -> None:
        """Run a model in a background thread and manage UI state."""
        run_button.setEnabled(False)
        run_button.setText("Running...")

        thread = QThread(self)
        worker = _RunWorker(run_callable)
        worker.moveToThread(thread)

        def handle_success(result: dict) -> None:
            on_success(result)
            self._finish_background_run(run_button, run_text, thread, worker)

        def handle_error(message: str) -> None:
            self._notify(f"Run failed for '{model_name}': {message}")
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
        """Restore UI state after a background run completes."""
        run_button.setEnabled(True)
        run_button.setText(run_text)
        try:
            self._active_workers.remove((thread, worker))
        except ValueError:
            pass

    def _notify(self, message: str) -> None:
        """Send a warning notification to the napari console."""
        if (
            show_console_notification is not None
            and Notification is not None
            and NotificationSeverity is not None
        ):
            show_console_notification(
                Notification(message, severity=NotificationSeverity.WARNING)
            )

    @staticmethod
    def _clear_layout(layout: QVBoxLayout) -> None:
        """Remove widgets and nested layouts from a layout."""
        while layout.count():
            item = layout.takeAt(0)
            child_layout = item.layout()
            if child_layout is not None:
                PredictionTab._clear_layout(child_layout)
                continue
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    @staticmethod
    def _configure_combo(combo: QComboBox) -> None:
        """Apply sizing defaults to combo boxes."""
        combo.setSizeAdjustPolicy(
            QComboBox.AdjustToMinimumContentsLengthWithIcon
        )
        combo.setMinimumContentsLength(20)
        combo.setMinimumWidth(180)
        combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)


class _RunWorker(QObject):
    """Worker that executes a callable in a background thread."""

    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, run_callable) -> None:
        super().__init__()
        self._run_callable = run_callable

    def run(self) -> None:
        try:
            result = self._run_callable()
        except Exception as exc:  # pragma: no cover - runtime error path
            self.error.emit(str(exc))
            return
        self.finished.emit(result)


__all__ = ["PredictionTab", "_RunWorker"]
