"""Frontend widget for saving and loading tab settings."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from qtpy.QtWidgets import (
    QFileDialog,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from senoquant.tabs.batch.config import BatchJobConfig

from .backend import SettingsBackend

if TYPE_CHECKING:
    from senoquant.tabs.batch.frontend import BatchTab
    from senoquant.tabs.segmentation.frontend import SegmentationTab
    from senoquant.tabs.spots.frontend import SpotsTab


class SettingsTab(QWidget):
    """Settings tab for exporting and restoring UI settings state."""

    def __init__(
        self,
        backend: SettingsBackend | None = None,
        *,
        segmentation_tab: "SegmentationTab | None" = None,
        spots_tab: "SpotsTab | None" = None,
        batch_tab: "BatchTab | None" = None,
    ) -> None:
        """Build settings UI.

        Parameters
        ----------
        backend : SettingsBackend or None, optional
            Persistence backend used to read/write settings bundles.
        segmentation_tab : SegmentationTab or None, optional
            Segmentation tab instance used for state export/import.
        spots_tab : SpotsTab or None, optional
            Spots tab instance used for state export/import.
        batch_tab : BatchTab or None, optional
            Batch tab instance used for optional batch payload export/import.
        """
        super().__init__()
        self._backend = backend or SettingsBackend()
        self._segmentation_tab = segmentation_tab
        self._spots_tab = spots_tab
        self._batch_tab = batch_tab

        layout = QVBoxLayout()
        description = QLabel(
            "Save or load segmentation and spot detector settings.\n"
            "If batch settings exist in the JSON, Batch tab state is restored too."
        )
        layout.addWidget(description)

        buttons = QVBoxLayout()
        self._save_button = QPushButton("Save settings")
        self._save_button.clicked.connect(self._save_settings)
        self._load_button = QPushButton("Load settings")
        self._load_button.clicked.connect(self._load_settings)
        buttons.addWidget(self._save_button)
        buttons.addWidget(self._load_button)
        layout.addLayout(buttons)

        self._status_label = QLabel("Ready")
        layout.addWidget(self._status_label)
        layout.addStretch(1)
        self.setLayout(layout)

    def set_tab_references(
        self,
        *,
        segmentation_tab: "SegmentationTab | None" = None,
        spots_tab: "SpotsTab | None" = None,
        batch_tab: "BatchTab | None" = None,
    ) -> None:
        """Update linked tab references used for settings import/export."""
        self._segmentation_tab = segmentation_tab
        self._spots_tab = spots_tab
        self._batch_tab = batch_tab

    def _save_settings(self) -> None:
        """Prompt for a path and save current tab settings."""
        default_name = self._backend.default_settings_filename()
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save settings",
            str(Path.cwd() / default_name),
            "JSON (*.json)",
        )
        if not path:
            return
        payload = self._backend.build_bundle(
            segmentation=self._export_segmentation_settings(),
            spots=self._export_spots_settings(),
            batch_job=self._export_batch_payload(),
        )
        saved_path = self._backend.save_bundle(path, payload)
        self._set_status(f"Saved settings: {saved_path.name}")

    def _load_settings(self) -> None:
        """Prompt for a settings file and apply known settings payloads."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load settings",
            str(Path.cwd()),
            "JSON (*.json)",
        )
        if not path:
            return
        bundle = self._backend.load_bundle(path)
        tab_settings_payload = bundle.get("tab_settings", {})
        if isinstance(tab_settings_payload, dict):
            self._apply_segmentation_settings(
                tab_settings_payload.get("segmentation")
            )
            self._apply_spots_settings(tab_settings_payload.get("spots"))
        batch_payload = bundle.get("batch_job", {})
        if isinstance(batch_payload, dict) and batch_payload:
            self._apply_batch_settings(batch_payload)
        self._set_status(
            f"Loaded settings: {Path(path).expanduser().name}"
        )

    def _export_segmentation_settings(self) -> dict:
        """Collect segmentation tab settings payload."""
        tab = self._segmentation_tab
        if tab is None or not hasattr(tab, "export_settings_state"):
            return {}
        payload = tab.export_settings_state()
        return payload if isinstance(payload, dict) else {}

    def _apply_segmentation_settings(self, payload: object) -> None:
        """Apply segmentation settings payload when supported."""
        tab = self._segmentation_tab
        if (
            tab is None
            or not isinstance(payload, dict)
            or not hasattr(tab, "apply_settings_state")
        ):
            return
        tab.apply_settings_state(payload)

    def _export_spots_settings(self) -> dict:
        """Collect spots tab settings payload."""
        tab = self._spots_tab
        if tab is None or not hasattr(tab, "export_settings_state"):
            return {}
        payload = tab.export_settings_state()
        return payload if isinstance(payload, dict) else {}

    def _apply_spots_settings(self, payload: object) -> None:
        """Apply spots settings payload when supported."""
        tab = self._spots_tab
        if (
            tab is None
            or not isinstance(payload, dict)
            or not hasattr(tab, "apply_settings_state")
        ):
            return
        tab.apply_settings_state(payload)

    def _export_batch_payload(self) -> dict:
        """Collect serializable batch job settings payload."""
        tab = self._batch_tab
        if tab is None:
            return {}

        job = None
        if hasattr(tab, "export_job_config"):
            job = tab.export_job_config()
        elif hasattr(tab, "_build_job_config"):
            job = tab._build_job_config()  # pragma: no cover - compatibility fallback

        if isinstance(job, BatchJobConfig):
            return job.to_dict()
        if isinstance(job, dict):
            return dict(job)
        return {}

    def _apply_batch_settings(self, payload: dict) -> None:
        """Apply batch payload to the batch tab when available."""
        tab = self._batch_tab
        if tab is None:
            return
        job = BatchJobConfig.from_dict(payload)
        if hasattr(tab, "apply_job_config"):
            tab.apply_job_config(job)
            return
        if hasattr(tab, "_apply_job_config"):
            tab._apply_job_config(job)  # pragma: no cover - compatibility fallback

    def _set_status(self, message: str) -> None:
        """Update status message label."""
        self._status_label.setText(message)
