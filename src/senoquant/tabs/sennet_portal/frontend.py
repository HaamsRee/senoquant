"""Frontend widget for the SenNet Portal tab."""

from __future__ import annotations

from pathlib import Path

from qtpy.QtCore import QObject, QThread
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

        layout = QVBoxLayout()
        layout.addWidget(self._make_connection_section())
        layout.addWidget(self._make_filter_section())
        layout.addWidget(self._make_dataset_section())
        layout.addWidget(self._make_destination_section())

        self._status_label = QLabel("Ready. Search for antibody-imaging datasets.")
        layout.addWidget(self._status_label)
        layout.addStretch(1)
        self.setLayout(layout)
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
        self._dataset_table.setColumnCount(8)
        self._dataset_table.setHorizontalHeaderLabels(
            [
                "Include",
                "SenNet ID",
                "Type",
                "Source type",
                "Organ",
                "Status",
                "Access",
                "Files",
            ]
        )

        header = self._dataset_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeToContents)
        self._dataset_table.verticalHeader().setVisible(False)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        self._select_all_button = QPushButton("Select all")
        self._select_all_button.clicked.connect(self._select_all_datasets)
        self._clear_all_button = QPushButton("Clear all")
        self._clear_all_button.clicked.connect(self._clear_all_datasets)
        button_row.addWidget(self._select_all_button)
        button_row.addWidget(self._clear_all_button)
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
        self._populate_table()
        self._populate_column_filter_combos()
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
        self._notify(
            f"Downloaded {dataset_count} dataset(s), {file_count} file(s) to {destination}."
        )


__all__ = ["SenNetPortalTab", "_RunWorker"]
