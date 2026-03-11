"""Tests for visualization frontend helpers."""

from __future__ import annotations

import json
from pathlib import Path

from qtpy.QtWidgets import QLineEdit, QTableWidget, QTableWidgetItem

from senoquant.tabs.visualization.frontend import VisualizationTab


def _build_marker_table(markers: list[str]) -> QTableWidget:
    """Create a minimal marker table for threshold-loading tests."""
    table = QTableWidget()
    table.setColumnCount(3)
    table.setRowCount(len(markers))
    for row, marker in enumerate(markers):
        table.setItem(row, 1, QTableWidgetItem(marker))
        table.setCellWidget(row, 2, QLineEdit())
    return table


def test_load_thresholds_from_json_deduplicates_colliding_channel_tokens(
    tmp_path: Path,
) -> None:
    """Map threshold values onto the same deduplicated tokens as export."""
    payload = {
        "channels": [
            {"name": "Ch 1", "threshold_min": 1},
            {"name": "Ch-1", "threshold_min": 2},
        ]
    }
    json_path = tmp_path / "feature_settings.json"
    json_path.write_text(json.dumps(payload), encoding="utf-8")

    tab = VisualizationTab.__new__(VisualizationTab)
    tab._marker_table = _build_marker_table(["Ch_1", "Ch_1__2"])

    tab._load_thresholds_from_json(json_path)

    assert tab._marker_table.cellWidget(0, 2).text() == "1"
    assert tab._marker_table.cellWidget(1, 2).text() == "2"


def test_load_thresholds_from_bundle_maps_merged_wide_marker_names(
    tmp_path: Path,
) -> None:
    """Apply saved thresholds to segmentation-prefixed merged marker columns."""

    payload = {
        "feature_settings": {
            "config": {
                "segmentations": [
                    {"label": "Nuclear 1"},
                    {"label": "Cyto 1"},
                ],
                "channels": [
                    {"name": "Ch 1", "threshold_min": 1.5},
                    {"name": "Ch-1", "threshold_min": 2.5},
                ],
            }
        }
    }
    json_path = tmp_path / "feature_settings.json"
    json_path.write_text(json.dumps(payload), encoding="utf-8")

    tab = VisualizationTab.__new__(VisualizationTab)
    tab._marker_table = _build_marker_table(
        [
            "Nuclear_1_Ch_1",
            "Cyto_1_Ch_1__2",
        ]
    )

    tab._load_thresholds_from_json(json_path)

    assert tab._marker_table.cellWidget(0, 2).text() == "1.5"
    assert tab._marker_table.cellWidget(1, 2).text() == "2.5"
