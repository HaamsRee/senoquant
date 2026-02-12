"""Execution and layer-output behavior mixin for segmentation frontend."""

from __future__ import annotations

import numpy as np
from qtpy.QtCore import QObject, QThread
from qtpy.QtWidgets import QPushButton

from senoquant.utils import append_run_metadata, labels_data_as_dask

from .widgets import (
    Labels,
    Notification,
    NotificationSeverity,
    _RunWorker,
    show_console_notification,
)


class SegmentationRunMixin:
    """Runtime execution helpers for segmentation tab."""

    def _run_nuclear(self) -> None:
        """Run nuclear segmentation for the selected model."""
        model_name = self._nuclear_model_combo.currentText()
        if not model_name or model_name == "No models found":
            return
        model = self._backend.get_preloaded_model(model_name)
        settings = self._collect_settings(self._nuclear_settings_widgets)
        layer_name = self._nuclear_layer_combo.currentText()
        layer = self._get_layer_by_name(layer_name)
        if not self._validate_single_channel_layer(layer, "Nuclear layer"):
            return
        self._start_background_run(
            run_button=self._nuclear_run_button,
            run_text="Run",
            task="nuclear",
            run_callable=lambda: model.run(
                task="nuclear",
                layer=layer,
                settings=settings,
            ),
            on_success=lambda result: self._add_labels_layer(
                layer,
                result.get("masks"),
                model_name=model_name,
                label_type="nuc",
                settings=settings,
            ),
        )

    def _run_cytoplasmic(self) -> None:
        """Run cytoplasmic segmentation for the selected model."""
        model_name = self._cyto_model_combo.currentText()
        if not model_name or model_name == "No models found":
            return
        model = self._backend.get_preloaded_model(model_name)
        settings = self._collect_settings(self._cyto_settings_widgets)
        modes = model.cytoplasmic_input_modes()

        if modes == ["nuclear"]:
            nuclear_layer = self._get_layer_by_name(
                self._cyto_nuclear_layer_combo.currentText()
            )
            if not self._validate_single_channel_layer(nuclear_layer, "Nuclear layer"):
                return
            self._start_background_run(
                run_button=self._cyto_run_button,
                run_text="Run",
                task="cytoplasmic",
                run_callable=lambda: model.run(
                    task="cytoplasmic",
                    nuclear_layer=nuclear_layer,
                    settings=settings,
                ),
                on_success=lambda result: self._add_labels_layer(
                    nuclear_layer,
                    result.get("masks"),
                    model_name=model_name,
                    label_type="cyto",
                    settings=settings,
                ),
            )
            return

        cyto_layer = self._get_layer_by_name(self._cyto_layer_combo.currentText())
        nuclear_layer = self._get_layer_by_name(
            self._cyto_nuclear_layer_combo.currentText()
        )
        if not self._validate_single_channel_layer(cyto_layer, "Cytoplasmic layer"):
            return
        if nuclear_layer is not None and not self._validate_single_channel_layer(
            nuclear_layer,
            "Nuclear layer",
        ):
            return
        if self._cyto_requires_nuclear(model) and nuclear_layer is None:
            return
        self._start_background_run(
            run_button=self._cyto_run_button,
            run_text="Run",
            task="cytoplasmic",
            run_callable=lambda: model.run(
                task="cytoplasmic",
                cytoplasmic_layer=cyto_layer,
                nuclear_layer=nuclear_layer,
                settings=settings,
            ),
            on_success=lambda result: self._add_labels_layer(
                cyto_layer,
                result.get("masks"),
                model_name=model_name,
                label_type="cyto",
                settings=settings,
            ),
        )

    def _start_background_run(
        self,
        run_button: QPushButton,
        run_text: str,
        task: str,
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
            self._notify(f"{task.capitalize()} run failed: {message}")
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

    def _get_layer_by_name(self, name: str):
        """Return a viewer layer with the given name, if it exists."""
        if self._viewer is None:
            return None
        for layer in self._viewer.layers:
            if layer.name == name:
                return layer
        return None

    def _validate_single_channel_layer(self, layer, label: str) -> bool:
        """Validate that a layer is single-channel 2D/3D image data."""
        if layer is None:
            return False
        if getattr(layer, "rgb", False):
            self._notify(f"{label} must be single-channel (not RGB).")
            return False
        shape = getattr(getattr(layer, "data", None), "shape", None)
        if shape is None:
            return False
        squeezed_ndim = sum(dim != 1 for dim in shape)
        if squeezed_ndim not in (2, 3):
            self._notify(f"{label} must be 2D or 3D single-channel.")
            return False
        return True

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

    def _add_labels_layer(
        self,
        source_layer,
        masks,
        model_name: str,
        label_type: str,
        settings: dict | None = None,
    ) -> None:
        """Add a labels layer and append run metadata for this segmentation."""
        if self._viewer is None or source_layer is None or masks is None:
            return
        label_name = f"{source_layer.name}_{model_name}_{label_type}_labels"
        dask_masks = labels_data_as_dask(masks)
        task_value = {
            "nuc": "nuclear",
            "cyto": "cytoplasmic",
        }.get(label_type)
        source_metadata = getattr(source_layer, "metadata", {})
        initial_metadata: dict[str, object] = {}
        if isinstance(source_metadata, dict):
            initial_metadata.update(source_metadata)
        if task_value:
            initial_metadata["task"] = task_value

        labels_layer = None
        if Labels is not None and hasattr(self._viewer, "add_layer"):
            labels_layer = Labels(
                dask_masks,
                name=label_name,
                metadata=initial_metadata,
            )
            added_layer = self._viewer.add_layer(labels_layer)
            if added_layer is not None:
                labels_layer = added_layer
        elif hasattr(self._viewer, "add_labels"):
            try:
                labels_layer = self._viewer.add_labels(
                    dask_masks,
                    name=label_name,
                    metadata=initial_metadata,
                )
            except TypeError:
                labels_layer = self._viewer.add_labels(
                    dask_masks,
                    name=label_name,
                )

        if labels_layer is None:
            return

        # Materialize after insertion: faster display interactions and simpler downstream ops.
        try:
            labels_layer.data = np.asarray(labels_layer.data)
        except Exception:
            pass

        layer_metadata = getattr(labels_layer, "metadata", {})
        merged_metadata: dict[str, object] = {}
        if isinstance(source_metadata, dict):
            merged_metadata.update(source_metadata)
        if isinstance(layer_metadata, dict):
            merged_metadata.update(layer_metadata)
        if task_value:
            merged_metadata = append_run_metadata(
                merged_metadata,
                task=task_value,
                runner_type="segmentation_model",
                runner_name=model_name,
                settings=settings,
            )
        labels_layer.metadata = merged_metadata
        labels_layer.contour = 2
