"""Frontend widget for the SenNet Portal tab."""

from __future__ import annotations

from pathlib import Path

from qtpy.QtCore import QObject, QThread, QTimer
from qtpy.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QProgressBar,
    QSpinBox,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from senoquant.tabs.sennet_portal._frontend.background import (
    SenNetPortalBackgroundMixin,
    _RunWorker,
)
from senoquant.tabs.sennet_portal._frontend.connection import SenNetPortalConnectionMixin
from senoquant.tabs.sennet_portal._frontend.dataset import SenNetPortalDatasetMixin
from senoquant.tabs.sennet_portal.backend import SenNetDataset, SenNetPortalBackend


class SenNetPortalTab(
    QWidget,
    SenNetPortalConnectionMixin,
    SenNetPortalDatasetMixin,
    SenNetPortalBackgroundMixin,
):
    """UI for discovering and downloading SenNet datasets.

    Parameters
    ----------
    backend : SenNetPortalBackend or None, optional
        Backend used for API discovery and download operations.
    napari_viewer : object or None, optional
        Viewer handle reserved for future viewer-aware interactions.
    """

    def __init__(
        self,
        backend: SenNetPortalBackend | None = None,
        napari_viewer=None,
    ) -> None:
        """Build tab layout, controls, and initial state.

        Parameters
        ----------
        backend : SenNetPortalBackend or None, optional
            Backend instance to use. When ``None``, a default backend is created.
        napari_viewer : object or None, optional
            Optional napari viewer reference.

        Returns
        -------
        None
            The widget is initialized in-place.
        """
        super().__init__()
        self._backend = backend or SenNetPortalBackend()
        self._viewer = napari_viewer
        self._active_workers: list[tuple[QThread, QObject]] = []
        self._datasets: list[SenNetDataset] = []
        self._dataset_type_options: list[str] = list(self._backend.ANTIBODY_DATASET_TYPES)
        self._download_locked = False
        self._download_task_ids: list[str] = []
        self._download_monitor_in_flight = False
        self._download_summary: dict[str, object] = {}
        self._download_poll_timer = QTimer(self)
        self._download_poll_timer.setInterval(3000)
        self._download_poll_timer.timeout.connect(self._poll_download_tasks)

        layout = QVBoxLayout()
        layout.addWidget(self._make_connection_section())
        layout.addWidget(self._make_filter_section())
        layout.addWidget(self._make_dataset_section())
        layout.addWidget(self._make_destination_section())

        self._status_label = QLabel("Ready. Search for antibody-imaging datasets.")
        layout.addWidget(self._status_label)
        layout.addStretch(1)
        self.setLayout(layout)
        self._populate_table(preserve_filters=False)
        self._refresh_globus_auth_status()
        self._refresh_dataset_types()

    def _make_filter_section(self) -> QGroupBox:
        """Create dataset search filters and discovery trigger button.

        Returns
        -------
        QGroupBox
            Group box containing dataset type, status, and result-limit inputs.
        """
        section = QGroupBox("Dataset filters")
        section_layout = QVBoxLayout()
        form_layout = QFormLayout()
        form_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self._dataset_type_combo = QComboBox()
        self._dataset_type_combo.addItem("Any antibody-based imaging")
        self._dataset_type_combo.addItems(self._dataset_type_options)

        self._status_combo = QComboBox()
        self._status_combo.addItems(["Published", "QA", "New"])

        self._max_results_spin = QSpinBox()
        self._max_results_spin.setRange(1, 200)
        self._max_results_spin.setValue(40)

        self._search_button = QPushButton("Find datasets")
        self._search_button.clicked.connect(self._search_datasets)
        self._refresh_dataset_types_button = QPushButton("Refresh dataset types")
        self._refresh_dataset_types_button.clicked.connect(self._refresh_dataset_types)

        form_layout.addRow("Dataset type", self._dataset_type_combo)
        form_layout.addRow("Status", self._status_combo)
        form_layout.addRow("Max results", self._max_results_spin)
        section_layout.addLayout(form_layout)
        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.addWidget(self._search_button)
        button_row.addWidget(self._refresh_dataset_types_button)
        section_layout.addLayout(button_row)
        section.setLayout(section_layout)
        return section

    def _make_dataset_section(self) -> QGroupBox:
        """Create table section that lists compatible datasets.

        Returns
        -------
        QGroupBox
            Group box containing the dataset selection table.
        """
        section = QGroupBox("Compatible SenNet datasets")
        layout = QVBoxLayout()

        self._dataset_table = QTableWidget()
        self._dataset_table.setColumnCount(9)
        self._dataset_table.setHorizontalHeaderLabels(
            [
                "Include",
                "SenNet ID",
                "Type",
                "Source type",
                "Organ",
                "Age",
                "Status",
                "Access",
                "Files",
            ]
        )

        header = self._dataset_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(8, QHeaderView.ResizeToContents)
        if hasattr(header, "setSortIndicatorShown"):
            header.setSortIndicatorShown(True)
        if hasattr(header, "setSortIndicator"):
            header.setSortIndicator(1, self._SORT_ASC)
        if hasattr(header, "sectionClicked"):
            header.sectionClicked.connect(self._on_table_header_clicked)
        self._dataset_table.verticalHeader().setVisible(False)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        self._select_all_button = QPushButton("Select all")
        self._select_all_button.clicked.connect(self._select_all_datasets)
        self._clear_all_button = QPushButton("Clear all")
        self._clear_all_button.clicked.connect(self._clear_all_datasets)
        self._clear_filters_button = QPushButton("Clear filters")
        self._clear_filters_button.clicked.connect(self._clear_filters)
        button_row.addWidget(self._select_all_button)
        button_row.addWidget(self._clear_all_button)
        button_row.addWidget(self._clear_filters_button)
        button_row.addStretch(1)

        layout.addLayout(button_row)
        layout.addWidget(self._dataset_table)
        section.setLayout(layout)
        return section

    def _make_destination_section(self) -> QGroupBox:
        """Create output destination controls and download action button.

        Returns
        -------
        QGroupBox
            Group box containing destination picker and download trigger.
        """
        section = QGroupBox("Download")
        section_layout = QVBoxLayout()
        form_layout = QFormLayout()
        form_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self._destination_input = QLineEdit()
        self._destination_input.setPlaceholderText("Destination folder")
        browse_button = QPushButton("Browse")
        browse_button.clicked.connect(self._select_destination)

        destination_row = QHBoxLayout()
        destination_row.setContentsMargins(0, 0, 0, 0)
        destination_row.addWidget(self._destination_input)
        destination_row.addWidget(browse_button)
        destination_widget = QWidget()
        destination_widget.setLayout(destination_row)

        self._download_button = QPushButton("Download selected")
        self._download_button.setEnabled(False)
        self._download_button.clicked.connect(self._download_selected)
        self._download_progress_bar = QProgressBar()
        self._download_progress_bar.setVisible(False)
        self._download_speed_label = QLabel("")
        self._download_speed_label.setVisible(False)

        form_layout.addRow("Destination", destination_widget)
        section_layout.addLayout(form_layout)
        section_layout.addWidget(self._download_button)
        section_layout.addWidget(self._download_progress_bar)
        section_layout.addWidget(self._download_speed_label)
        section.setLayout(section_layout)
        return section

    def _select_destination(self) -> None:
        """Open a directory picker and store the selected destination path.

        Returns
        -------
        None
            Destination text field is updated when a path is chosen.
        """
        selected = QFileDialog.getExistingDirectory(self, "Select destination folder")
        if not selected:
            return
        self._destination_input.setText(selected)

    def _search_datasets(self) -> None:
        """Run dataset discovery in a background thread.

        Returns
        -------
        None
            Search starts asynchronously and UI state updates on completion.
        """
        type_text = self._dataset_type_combo.currentText().strip()
        if type_text == "Any antibody-based imaging":
            dataset_types = list(self._dataset_type_options)
        else:
            dataset_types = [type_text]

        self._run_background(
            button=self._search_button,
            busy_text="Searching...",
            run_callable=lambda: self._backend.search_datasets(
                dataset_types=dataset_types,
                token=self._token_input.text().strip(),
                max_results=self._max_results_spin.value(),
                status=self._status_combo.currentText().strip(),
            ),
            on_success=self._on_search_complete,
            on_error_prefix="Dataset search failed",
        )

    def _on_search_complete(self, datasets: list[SenNetDataset]) -> None:
        """Handle successful search response and refresh UI.

        Parameters
        ----------
        datasets : list of SenNetDataset
            Compatible datasets returned by backend discovery.

        Returns
        -------
        None
            Internal state and table UI are updated in-place.
        """
        self._datasets = list(datasets)
        self._populate_table(preserve_filters=False)
        self._download_button.setEnabled(bool(self._datasets))
        self._notify(
            f"Found {len(self._datasets)} compatible dataset(s). "
            "Select rows and choose a destination to download."
        )

    def _download_selected(self) -> None:
        """Validate selection and start asynchronous download operation.

        Returns
        -------
        None
            Download starts in a worker thread when validation passes.
        """
        destination_text = self._destination_input.text().strip()
        if not destination_text:
            self._notify("Choose a destination folder before downloading.")
            return

        selected = self._selected_datasets()
        if not selected:
            self._notify("Select at least one dataset row to download.")
            return

        self._download_locked = False
        destination = Path(destination_text)
        self._run_background(
            button=self._download_button,
            busy_text="Downloading...",
            run_callable=lambda: self._backend.download_datasets(selected, destination),
            on_success=self._on_download_complete,
            on_error_prefix="Download failed",
        )

    def _on_download_complete(self, result: dict[str, object]) -> None:
        """Display final download summary after a successful transfer.

        Parameters
        ----------
        result : dict of str to object
            Backend summary payload including counts and output destination.

        Returns
        -------
        None
            Status message is updated and emitted as a notification.
        """
        dataset_count = int(result.get("dataset_count", 0))
        file_count = int(result.get("file_count", 0))
        destination = str(result.get("destination", "")).strip()
        task_ids = [str(task_id).strip() for task_id in result.get("task_ids", []) if str(task_id).strip()]
        if not task_ids:
            self._notify(
                f"Submitted transfer for {dataset_count} dataset(s), {file_count} file(s) to {destination}."
            )
            self._download_locked = False
            self._download_progress_bar.setVisible(False)
            self._download_speed_label.setVisible(False)
            self._download_button.setEnabled(bool(self._datasets))
            return

        self._download_locked = True
        self._download_task_ids = task_ids
        self._download_summary = {
            "dataset_count": dataset_count,
            "file_count": file_count,
            "destination": destination,
        }
        self._download_progress_bar.setVisible(True)
        self._download_progress_bar.setValue(0)
        self._download_speed_label.setVisible(True)
        self._download_speed_label.setText("Transfer in progress: 0%")
        self._download_button.setEnabled(False)
        self._notify(
            f"Transfer initiated for {dataset_count} dataset(s), {file_count} file(s). "
            "Monitoring progress..."
        )
        self._start_download_monitoring()

    def _start_download_monitoring(self) -> None:
        """Begin polling Globus task status for active transfer task IDs."""
        if not self._download_task_ids:
            self._download_locked = False
            self._download_button.setEnabled(bool(self._datasets))
            return
        self._download_monitor_in_flight = False
        self._download_poll_timer.start()
        self._poll_download_tasks()

    def _stop_download_monitoring(self) -> None:
        """Stop task polling and release download lock state."""
        self._download_task_ids = []
        self._download_monitor_in_flight = False
        if hasattr(self._download_poll_timer, "stop"):
            self._download_poll_timer.stop()
        self._download_locked = False
        self._download_button.setEnabled(bool(self._datasets))

    def _poll_download_tasks(self) -> None:
        """Poll backend for aggregate transfer progress in a worker thread."""
        if not self._download_task_ids:
            self._stop_download_monitoring()
            return
        if self._download_monitor_in_flight:
            return
        self._download_monitor_in_flight = True

        thread = QThread(self)
        worker = _RunWorker(
            lambda: self._backend.download_tasks_status(self._download_task_ids)
        )
        worker.moveToThread(thread)

        def handle_success(payload: dict[str, object]) -> None:
            self._download_monitor_in_flight = False
            self._on_download_progress(payload)
            self._finish_background(thread, worker, self._download_button, "Download selected")

        def handle_error(message: str) -> None:
            self._download_monitor_in_flight = False
            self._stop_download_monitoring()
            self._notify(
                "Download progress monitoring failed. "
                f"Check Globus task status manually. Detail: {message}"
            )
            self._finish_background(thread, worker, self._download_button, "Download selected")

        thread.started.connect(worker.run)
        worker.finished.connect(handle_success)
        worker.error.connect(handle_error)
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(worker.deleteLater)

        self._active_workers.append((thread, worker))
        thread.start()

    def _on_download_progress(self, status: dict[str, object]) -> None:
        """Update progress widgets from aggregated transfer status payload."""
        percent = int(status.get("progress_percent", 0) or 0)
        speed_bps = int(status.get("speed_bps", 0) or 0)
        completed = int(status.get("subtasks_completed", 0) or 0)
        total = int(status.get("subtasks_total", 0) or 0)
        overall = str(status.get("overall_status", "UNKNOWN")).strip() or "UNKNOWN"
        self._download_progress_bar.setValue(max(0, min(100, percent)))
        self._download_speed_label.setText(
            f"Transfer {overall}: {percent}% ({completed}/{total} subtasks), "
            f"{self._format_bps(speed_bps)}"
        )

        if not bool(status.get("all_complete", False)):
            return

        dataset_count = int(self._download_summary.get("dataset_count", 0) or 0)
        file_count = int(self._download_summary.get("file_count", 0) or 0)
        destination = str(self._download_summary.get("destination", "")).strip()
        all_succeeded = bool(status.get("all_succeeded", False))
        self._stop_download_monitoring()
        if all_succeeded:
            self._notify(
                f"Transfer complete: {dataset_count} dataset(s), {file_count} file(s) "
                f"to {destination}."
            )
        else:
            self._notify(
                f"Transfer finished with failures: {dataset_count} dataset(s), "
                f"{file_count} file(s). Check Globus activity."
            )

    @staticmethod
    def _format_bps(bytes_per_second: int) -> str:
        """Format transfer speed in human-readable units."""
        value = float(max(0, int(bytes_per_second)))
        units = ("B/s", "KB/s", "MB/s", "GB/s", "TB/s")
        index = 0
        while value >= 1024.0 and index < len(units) - 1:
            value /= 1024.0
            index += 1
        return f"{value:.1f} {units[index]}"

    def cancel_active_downloads(self) -> None:
        """Cancel active transfer tasks and stop monitoring state."""
        if not self._download_task_ids:
            return
        task_ids = list(self._download_task_ids)
        try:
            self._backend.cancel_download_tasks(task_ids)
        except Exception:
            pass
        self._stop_download_monitoring()
        self._download_progress_bar.setVisible(False)
        self._download_speed_label.setVisible(False)

    def closeEvent(self, event) -> None:
        """Cancel in-progress transfer tasks when SenNet Portal closes."""
        self.cancel_active_downloads()
        super_close = getattr(super(), "closeEvent", None)
        if callable(super_close):
            super_close(event)


__all__ = ["SenNetPortalTab", "_RunWorker"]
