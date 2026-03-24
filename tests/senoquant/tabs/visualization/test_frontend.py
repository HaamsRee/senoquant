"""Tests for visualization frontend helpers."""

from __future__ import annotations

import json
from pathlib import Path

from qtpy.QtWidgets import QLineEdit, QTableWidget, QTableWidgetItem, QMessageBox, QFileDialog

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


def test_select_marker_source_file_returns_single_result_file(tmp_path: Path) -> None:
    """Use the only supported result file without prompting."""
    csv_path = tmp_path / "markers.csv"
    csv_path.write_text("CD3_mean_intensity\n", encoding="utf-8")

    tab = VisualizationTab.__new__(VisualizationTab)

    selected = tab._select_marker_source_file(tmp_path)

    assert selected == csv_path


def test_select_marker_source_file_returns_single_excel(tmp_path: Path) -> None:
    """Use the only Excel file without prompting."""
    excel_path = tmp_path / "markers.xlsx"
    excel_path.write_text("", encoding="utf-8")

    tab = VisualizationTab.__new__(VisualizationTab)

    selected = tab._select_marker_source_file(tmp_path)

    assert selected == excel_path


def test_select_marker_source_file_prompts_for_multiple_results(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Show a blocking popup, then prompt when several result files exist."""
    csv_path = tmp_path / "a.csv"
    excel_path = tmp_path / "b.xls"
    csv_path.write_text("CD3_mean_intensity\n", encoding="utf-8")
    excel_path.write_text("", encoding="utf-8")

    calls: list[tuple[str, str, str]] = []
    message_counts: list[int] = []

    def _get_open_file_name(*args, **kwargs):
        strs = [a for a in args if isinstance(a, str)]
        if len(strs) >= 3:
            calls.append((strs[0], strs[1], strs[2]))
        return str(excel_path), "Result files (*.csv *.xlsx *.xls)"

    # Create the tab instance
    tab = VisualizationTab.__new__(VisualizationTab)

    # 1. Mock the warning method directly on the instance to prevent UI hangs
    def _mock_show_message(file_count: int) -> None:
        message_counts.append(file_count)
        
    monkeypatch.setattr(tab, "_show_result_file_selection_message", _mock_show_message)

    # 2. Patch QFileDialog where it is safely imported at the top of frontend.py
    import senoquant.tabs.visualization.frontend as frontend
    monkeypatch.setattr(frontend.QFileDialog, "getOpenFileName", _get_open_file_name)

    # Run the method
    selected = tab._select_marker_source_file(tmp_path)

    # Assertions
    assert selected == excel_path
    assert message_counts == [2]  # Verifies it tried to warn about 2 files
    assert calls == [
        ("Select result file", str(tmp_path), "Result files (*.csv *.xlsx *.xls)")
    ]


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
