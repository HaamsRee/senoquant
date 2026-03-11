"""Tests for marker merged-table postprocessing."""

from __future__ import annotations

import csv
import types

import pytest

from tests.conftest import DummyLayout, DummyViewer, Image, Labels
from senoquant.tabs.quantification.features.base import FeatureConfig
from senoquant.tabs.quantification.features.marker.config import (
    MarkerChannelConfig,
    MarkerFeatureData,
    MarkerSegmentationConfig,
)
from senoquant.tabs.quantification.features.marker.export import _write_table
from senoquant.tabs.quantification.features.marker.feature import MarkerFeature
from senoquant.tabs.quantification.features.marker.postprocess import (
    postprocess_marker_merged_wide,
)


class DummyContext:
    """Feature context stub."""

    def __init__(self, state: FeatureConfig) -> None:
        self.state = state
        self.left_dynamic_layout = DummyLayout()


def test_marker_feature_export_appends_merged_wide_csv(tmp_path) -> None:
    """MarkerFeature.export adds merged_wide.csv on strict 1:1 overlap."""
    labels = [[1, 1], [0, 2]]
    viewer = DummyViewer(
        [
            Labels(labels, "nuclear"),
            Labels(labels, "cytoplasmic"),
            Image([[1.0, 2.0], [3.0, 4.0]], "p21"),
        ]
    )
    data = MarkerFeatureData(
        segmentations=[
            MarkerSegmentationConfig(label="nuclear"),
            MarkerSegmentationConfig(label="cytoplasmic"),
        ],
        channels=[MarkerChannelConfig(name="p21", channel="p21")],
    )
    state = FeatureConfig(name="Markers", type_name="Markers", data=data)
    tab = types.SimpleNamespace(
        _viewer=viewer,
        _enable_rois=False,
        _enable_thresholds=False,
    )
    feature = MarkerFeature(tab, DummyContext(state))

    outputs = list(feature.export(tmp_path, "csv"))

    merged_path = next(path for path in outputs if path.name == "merged_wide.csv")
    with merged_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert rows
    assert rows[0]["merge_label_id"] == "1"
    assert rows[0]["nuclear_seg_name"] == "nuclear"
    assert rows[0]["cytoplasmic_seg_name"] == "cytoplasmic"
    assert "nuclear_label_id" in rows[0]
    assert "cytoplasmic_p21_mean_intensity" in rows[0]


def test_postprocess_marker_creates_merged_wide_xlsx(tmp_path) -> None:
    """Create merged_wide.xlsx with prefixed headers for strict 3-way match."""
    viewer = DummyViewer(
        [
            Labels([[1]], "nuclear 1"),
            Labels([[1]], "cyto 1"),
            Labels([[1]], "membrane 1"),
        ]
    )
    data = MarkerFeatureData(
        segmentations=[
            MarkerSegmentationConfig(label="nuclear 1"),
            MarkerSegmentationConfig(label="cyto 1"),
            MarkerSegmentationConfig(label="membrane 1"),
        ],
        channels=[MarkerChannelConfig(name="p21", channel="p21")],
    )
    feature = FeatureConfig(name="Markers", type_name="Markers", data=data)
    header = ["label_id", "overlaps_with", "p21_mean_intensity"]
    _write_table(
        tmp_path / "nuclear_1.xlsx",
        header,
        [
            {
                "label_id": 1,
                "overlaps_with": "cyto_1_1;membrane_1_1",
                "p21_mean_intensity": 1.0,
            }
        ],
        "xlsx",
    )
    _write_table(
        tmp_path / "cyto_1.xlsx",
        header,
        [
            {
                "label_id": 1,
                "overlaps_with": "nuclear_1_1;membrane_1_1",
                "p21_mean_intensity": 2.0,
            }
        ],
        "xlsx",
    )
    _write_table(
        tmp_path / "membrane_1.xlsx",
        header,
        [
            {
                "label_id": 1,
                "overlaps_with": "nuclear_1_1;cyto_1_1",
                "p21_mean_intensity": 3.0,
            }
        ],
        "xlsx",
    )

    outputs = postprocess_marker_merged_wide(
        feature,
        tmp_path,
        [
            tmp_path / "nuclear_1.xlsx",
            tmp_path / "cyto_1.xlsx",
            tmp_path / "membrane_1.xlsx",
        ],
        viewer=viewer,
        export_format="xlsx",
    )

    merged_path = next(path for path in outputs if path.name == "merged_wide.xlsx")
    import openpyxl

    workbook = openpyxl.load_workbook(merged_path, read_only=True, data_only=True)
    try:
        rows = list(workbook.active.iter_rows(values_only=True))
    finally:
        workbook.close()

    assert rows[0][:4] == (
        "merge_label_id",
        "nuclear_1_seg_name",
        "nuclear_1_label_id",
        "nuclear_1_overlaps_with",
    )
    assert "cyto_1_p21_mean_intensity" in rows[0]
    assert "membrane_1_p21_mean_intensity" in rows[0]


@pytest.mark.parametrize(
    ("rows_a", "rows_b", "expected_fragment"),
    [
        (
            [
                {"label_id": 1, "overlaps_with": "cytoplasmic_1", "signal": 1.0},
                {"label_id": 2, "overlaps_with": "cytoplasmic_2", "signal": 2.0},
            ],
            [
                {"label_id": 1, "overlaps_with": "nuclear_1", "signal": 3.0},
            ],
            "does not share the same label_id set",
        ),
        (
            [
                {"label_id": 1, "overlaps_with": "cytoplasmic_1", "signal": 1.0},
                {"label_id": 1, "overlaps_with": "cytoplasmic_1", "signal": 2.0},
            ],
            [
                {"label_id": 1, "overlaps_with": "nuclear_1", "signal": 3.0},
            ],
            "duplicate row for label_id=1",
        ),
        (
            [
                {"label_id": 1, "overlaps_with": "", "signal": 1.0},
            ],
            [
                {"label_id": 1, "overlaps_with": "nuclear_1", "signal": 3.0},
            ],
            "missing expected overlap",
        ),
        (
            [
                {
                    "label_id": 1,
                    "overlaps_with": "cytoplasmic_1;cytoplasmic_1",
                    "signal": 1.0,
                },
            ],
            [
                {"label_id": 1, "overlaps_with": "nuclear_1", "signal": 3.0},
            ],
            "duplicate overlap references",
        ),
        (
            [
                {"label_id": 1, "overlaps_with": "cytoplasmic_2", "signal": 1.0},
            ],
            [
                {"label_id": 1, "overlaps_with": "nuclear_1", "signal": 3.0},
            ],
            "missing expected overlap",
        ),
        (
            [
                {"label_id": 1, "overlaps_with": "cytoplasmic_1", "signal": 1.0},
                {"label_id": 2, "overlaps_with": "cytoplasmic_2", "signal": 2.0},
            ],
            [
                {
                    "label_id": 1,
                    "overlaps_with": "nuclear_1;nuclear_2",
                    "signal": 3.0,
                },
                {"label_id": 2, "overlaps_with": "nuclear_2", "signal": 4.0},
            ],
            "unexpected overlap",
        ),
    ],
)
def test_postprocess_marker_skips_invalid_strict_merges(
    tmp_path,
    capsys,
    rows_a,
    rows_b,
    expected_fragment: str,
) -> None:
    """Skip merged export and log the first strict-validation failure."""
    viewer = DummyViewer(
        [
            Labels([[1, 0], [0, 2]], "nuclear"),
            Labels([[1, 0], [0, 2]], "cytoplasmic"),
        ]
    )
    data = MarkerFeatureData(
        segmentations=[
            MarkerSegmentationConfig(label="nuclear"),
            MarkerSegmentationConfig(label="cytoplasmic"),
        ],
        channels=[MarkerChannelConfig(name="p21", channel="p21")],
    )
    feature = FeatureConfig(name="Markers", type_name="Markers", data=data)
    header = ["label_id", "overlaps_with", "signal"]
    table_a = tmp_path / "nuclear.csv"
    table_b = tmp_path / "cytoplasmic.csv"
    _write_table(table_a, header, rows_a, "csv")
    _write_table(table_b, header, rows_b, "csv")

    outputs = postprocess_marker_merged_wide(
        feature,
        tmp_path,
        [table_a, table_b],
        viewer=viewer,
        export_format="csv",
    )

    captured = capsys.readouterr()
    assert all(path.name != "merged_wide.csv" for path in outputs)
    assert "Marker merged table skipped for feature 'Markers':" in captured.out
    assert expected_fragment in captured.out


def test_postprocess_marker_noops_for_single_segmentation(tmp_path, capsys) -> None:
    """Do not log or write merged output when only one segmentation exists."""
    viewer = DummyViewer([Labels([[1]], "nuclear")])
    data = MarkerFeatureData(
        segmentations=[MarkerSegmentationConfig(label="nuclear")],
        channels=[MarkerChannelConfig(name="p21", channel="p21")],
    )
    feature = FeatureConfig(name="Markers", type_name="Markers", data=data)
    table_path = tmp_path / "nuclear.csv"
    _write_table(
        table_path,
        ["label_id", "overlaps_with", "signal"],
        [{"label_id": 1, "overlaps_with": "", "signal": 1.0}],
        "csv",
    )

    outputs = postprocess_marker_merged_wide(
        feature,
        tmp_path,
        [table_path],
        viewer=viewer,
        export_format="csv",
    )

    captured = capsys.readouterr()
    assert outputs == [table_path]
    assert captured.out == ""
