"""Frontend widget for the SenNet Portal tab."""

from __future__ import annotations

import sys
from pathlib import Path

from qtpy.QtCore import QObject, QThread, Qt, Signal
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
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from senoquant.tabs.sennet_portal.backend import SenNetDataset, SenNetPortalBackend

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


class SenNetPortalTab(QWidget):
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

        layout = QVBoxLayout()
        layout.addWidget(self._make_connection_section())
        layout.addWidget(self._make_filter_section())
        layout.addWidget(self._make_dataset_section())
        layout.addWidget(self._make_destination_section())

        self._status_label = QLabel("Ready. Search for antibody-imaging datasets.")
        layout.addWidget(self._status_label)
        layout.addStretch(1)
        self.setLayout(layout)

    def _make_connection_section(self) -> QGroupBox:
        """Create connection controls used for optional API authentication.

        Returns
        -------
        QGroupBox
            Group box containing bearer-token input.
        """
        section = QGroupBox("Connection")
        section_layout = QVBoxLayout()
        form_layout = QFormLayout()
        form_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self._token_input = QLineEdit()
        self._token_input.setPlaceholderText(
            "Optional API bearer token (leave blank for public datasets)"
        )
        form_layout.addRow("API token", self._token_input)
        section_layout.addLayout(form_layout)
        section.setLayout(section_layout)
        return section

    def _make_filter_section(self) -> QGroupBox:
        """Create dataset search filters and discovery trigger button.

        Returns
        -------
        QGroupBox
            Group box containing dataset type, status, and result-limit inputs.
        """
        section = QGroupBox("Dataset Filters")
        section_layout = QVBoxLayout()
        form_layout = QFormLayout()
        form_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self._dataset_type_combo = QComboBox()
        self._dataset_type_combo.addItem("Any antibody-based imaging")
        self._dataset_type_combo.addItems(self._backend.ANTIBODY_DATASET_TYPES)

        self._status_combo = QComboBox()
        self._status_combo.addItems(["Published", "QA", "New"])

        self._max_results_spin = QSpinBox()
        self._max_results_spin.setRange(1, 200)
        self._max_results_spin.setValue(40)

        self._search_button = QPushButton("Find datasets")
        self._search_button.clicked.connect(self._search_datasets)

        form_layout.addRow("Dataset type", self._dataset_type_combo)
        form_layout.addRow("Status", self._status_combo)
        form_layout.addRow("Max results", self._max_results_spin)
        section_layout.addLayout(form_layout)
        section_layout.addWidget(self._search_button)
        section.setLayout(section_layout)
        return section

    def _make_dataset_section(self) -> QGroupBox:
        """Create table section that lists compatible datasets.

        Returns
        -------
        QGroupBox
            Group box containing the dataset selection table.
        """
        section = QGroupBox("Compatible SenNet Datasets")
        layout = QVBoxLayout()

        self._dataset_table = QTableWidget()
        self._dataset_table.setColumnCount(7)
        self._dataset_table.setHorizontalHeaderLabels(
            [
                "Include",
                "SenNet ID",
                "Type",
                "Status",
                "Access",
                "Files",
                "Extensions",
            ]
        )

        header = self._dataset_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.Stretch)
        self._dataset_table.verticalHeader().setVisible(False)

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

        form_layout.addRow("Destination", destination_widget)
        section_layout.addLayout(form_layout)
        section_layout.addWidget(self._download_button)
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
        if not self._ensure_globus_login_for_search():
            return

        type_text = self._dataset_type_combo.currentText().strip()
        if type_text == "Any antibody-based imaging":
            dataset_types = list(self._backend.ANTIBODY_DATASET_TYPES)
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

    def _ensure_globus_login_for_search(self) -> bool:
        """Ensure Globus login is present before starting dataset search.

        Returns
        -------
        bool
            ``True`` when search can proceed, otherwise ``False``.
        """
        try:
            self._backend._require_globus_login_for_search()
            return True
        except RuntimeError as exc:
            message = str(exc).strip()
            lowered = message.lower()
            if "globus login is required" not in lowered:
                self._notify(f"Dataset search failed: {message}")
                return False

        if not self._prompt_globus_login():
            self._notify("Dataset search cancelled. Globus login is required.")
            return False

        self._notify("Starting Globus login...")
        try:
            self._backend.login_globus()
            self._backend._require_globus_login_for_search()
        except RuntimeError as exc:
            self._notify(f"Dataset search failed: {exc}")
            return False
        return True

    def _prompt_globus_login(self) -> bool:
        """Show login prompt when Globus authentication is missing.

        Returns
        -------
        bool
            ``True`` when user selected **Login**, otherwise ``False``.
        """
        try:
            from qtpy.QtWidgets import QMessageBox
        except Exception:
            return False

        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Warning)
        dialog.setWindowTitle("Globus Login Required")
        dialog.setText("You must log in to Globus before searching datasets.")
        dialog.setInformativeText("Click Login to run `globus login`, or Cancel to stop.")
        login_button = dialog.addButton("Login", QMessageBox.AcceptRole)
        dialog.addButton(QMessageBox.Cancel)
        dialog.setDefaultButton(login_button)
        dialog.exec()
        return dialog.clickedButton() is login_button

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
        self._populate_table()
        self._download_button.setEnabled(bool(self._datasets))
        self._notify(
            f"Found {len(self._datasets)} compatible dataset(s). "
            "Select rows and choose a destination to download."
        )

    def _populate_table(self) -> None:
        """Render currently loaded datasets into the selection table.

        Returns
        -------
        None
            Table rows are recreated from ``self._datasets``.
        """
        self._dataset_table.setRowCount(0)
        for row, dataset in enumerate(self._datasets):
            self._dataset_table.insertRow(row)

            include_item = QTableWidgetItem()
            include_item.setCheckState(Qt.Checked)
            include_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            self._dataset_table.setItem(row, 0, include_item)

            self._dataset_table.setItem(row, 1, QTableWidgetItem(dataset.sennet_id))
            self._dataset_table.setItem(row, 2, QTableWidgetItem(dataset.dataset_type))
            self._dataset_table.setItem(row, 3, QTableWidgetItem(dataset.status))
            self._dataset_table.setItem(row, 4, QTableWidgetItem(dataset.access_level))
            self._dataset_table.setItem(
                row,
                5,
                QTableWidgetItem(str(len(dataset.compatible_paths))),
            )
            self._dataset_table.setItem(
                row,
                6,
                QTableWidgetItem(", ".join(dataset.compatible_extensions)),
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

        destination = Path(destination_text)
        self._run_background(
            button=self._download_button,
            busy_text="Downloading...",
            run_callable=lambda: self._backend.download_datasets(selected, destination),
            on_success=self._on_download_complete,
            on_error_prefix="Download failed",
        )

    def _selected_datasets(self) -> list[SenNetDataset]:
        """Collect datasets whose include checkbox is enabled.

        Returns
        -------
        list of SenNetDataset
            Subset of datasets currently selected by the user.
        """
        selected: list[SenNetDataset] = []
        row_count = self._dataset_table.rowCount()
        for row in range(row_count):
            include_item = self._dataset_table.item(row, 0)
            if include_item is None:
                continue
            if include_item.checkState() != Qt.Checked:
                continue
            if row < len(self._datasets):
                selected.append(self._datasets[row])
        return selected

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
        self._notify(
            f"Downloaded {dataset_count} dataset(s), {file_count} file(s) to {destination}."
        )

    def _run_background(
        self,
        *,
        button: QPushButton,
        busy_text: str,
        run_callable,
        on_success,
        on_error_prefix: str,
    ) -> None:
        """Run an arbitrary callable on a worker thread and manage UI state.

        Parameters
        ----------
        button : QPushButton
            Button that initiated the background task.
        busy_text : str
            Temporary button label shown while work is running.
        run_callable : callable
            Function executed on the worker thread.
        on_success : callable
            Callback invoked with worker result payload.
        on_error_prefix : str
            Prefix used when reporting worker failures.

        Returns
        -------
        None
            Thread and worker lifecycle are managed internally.
        """
        button.setEnabled(False)
        original_text = button.text()
        button.setText(busy_text)

        thread = QThread(self)
        worker = _RunWorker(run_callable)
        worker.moveToThread(thread)

        def handle_success(payload) -> None:
            """Handle worker success payload on the GUI thread.

            Parameters
            ----------
            payload : object
                Result emitted by the worker.

            Returns
            -------
            None
                Delegates to caller callback and restores button state.
            """
            on_success(payload)
            self._finish_background(thread, worker, button, original_text)

        def handle_error(message: str) -> None:
            """Handle worker error signal on the GUI thread.

            Parameters
            ----------
            message : str
                Error message emitted by worker.

            Returns
            -------
            None
                Reports error and restores button state.
            """
            self._notify(f"{on_error_prefix}: {message}")
            self._finish_background(thread, worker, button, original_text)

        thread.started.connect(worker.run)
        worker.finished.connect(handle_success)
        worker.error.connect(handle_error)
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(worker.deleteLater)

        self._active_workers.append((thread, worker))
        thread.start()

    def _finish_background(
        self,
        thread: QThread,
        worker: QObject,
        button: QPushButton,
        original_text: str,
    ) -> None:
        """Restore UI state after a background thread exits.

        Parameters
        ----------
        thread : QThread
            Worker thread that completed.
        worker : QObject
            Worker object associated with ``thread``.
        button : QPushButton
            Trigger button to re-enable.
        original_text : str
            Button label to restore.

        Returns
        -------
        None
            UI state and active-worker registry are updated.
        """
        button.setEnabled(True)
        button.setText(original_text)
        self._download_button.setEnabled(bool(self._datasets))
        try:
            self._active_workers.remove((thread, worker))
        except ValueError:
            pass

    def _notify(self, message: str) -> None:
        """Update status text and emit napari warning notification when available.

        Parameters
        ----------
        message : str
            Message text to display and emit.

        Returns
        -------
        None
            Status label and optional napari console notifications are updated.
        """
        self._status_label.setText(message)
        if (
            show_console_notification is not None
            and Notification is not None
            and NotificationSeverity is not None
        ):
            show_console_notification(
                Notification(message, severity=NotificationSeverity.WARNING)
            )
            try:
                sys.stdout.flush()
            except Exception:  # pragma: no cover - best-effort flush
                pass


class _RunWorker(QObject):
    """Worker that executes a callable in a background thread.

    Parameters
    ----------
    run_callable : callable
        Callable to execute inside the worker thread.
    """

    finished = Signal(object)
    error = Signal(str)

    def __init__(self, run_callable) -> None:
        """Store callable used during worker execution.

        Parameters
        ----------
        run_callable : callable
            Callable returning result payload or raising an exception.

        Returns
        -------
        None
            Callable is stored for later execution.
        """
        super().__init__()
        self._run_callable = run_callable

    def run(self) -> None:
        """Execute worker callable and emit finished or error signal.

        Returns
        -------
        None
            Emits ``finished`` on success or ``error`` on failure.
        """
        try:
            result = self._run_callable()
        except Exception as exc:
            self.error.emit(str(exc))
            return
        self.finished.emit(result)


__all__ = ["SenNetPortalTab", "_RunWorker"]
