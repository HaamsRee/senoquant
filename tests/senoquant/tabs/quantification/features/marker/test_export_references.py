"""Tests for marker export reference columns functionality."""

import csv
import numpy as np
import pytest

from tests.conftest import DummyViewer, Image, Labels
from senoquant.tabs.quantification.features.base import FeatureConfig
from senoquant.tabs.quantification.features.marker.config import (
    MarkerChannelConfig,
    MarkerFeatureData,
    MarkerSegmentationConfig,
)
from senoquant.tabs.quantification.features.marker.export import (
    _add_reference_columns,
    _build_cross_segmentation_map,
    _add_cross_reference_column,
    export_marker,
)


class TestAddReferenceColumns:
    """Test the _add_reference_columns function."""

    def test_add_file_path_and_seg_type(self):
        """Test adding file path and segmentation type columns."""
        rows = [
            {"label_id": 1, "area": 100},
            {"label_id": 2, "area": 200},
        ]
        labels = np.zeros((10, 10), dtype=np.uint16)
        label_ids = np.array([1, 2])
        file_path = "/path/to/image.tif"
        seg_type = "nuclear"

        cols = _add_reference_columns(rows, labels, label_ids, file_path, seg_type)

        assert "file_path" in cols
        assert "segmentation_type" in cols
        assert all(row.get("file_path") == file_path for row in rows)
        assert all(row.get("segmentation_type") == seg_type for row in rows)

    def test_no_file_path_when_none(self):
        """Test that file_path column is skipped when None."""
        rows = [{"label_id": 1}]
        labels = np.zeros((10, 10), dtype=np.uint16)
        label_ids = np.array([1])

        cols = _add_reference_columns(rows, labels, label_ids, None, "cytoplasmic")

        assert "file_path" not in cols
        assert "segmentation_type" in cols
        assert "file_path" not in rows[0]

    def test_cytoplasmic_segmentation_type(self):
        """Test cytoplasmic segmentation type assignment."""
        rows = [{"label_id": 1}]
        labels = np.zeros((10, 10), dtype=np.uint16)
        label_ids = np.array([1])

        _add_reference_columns(rows, labels, label_ids, None, "cytoplasmic")

        assert rows[0]["segmentation_type"] == "cytoplasmic"


def test_export_segmentation_type_uses_layer_metadata(tmp_path):
    """Use labels metadata task for segmentation_type export."""
    labels = np.array([[0, 1], [0, 2]], dtype=np.int32)
    image = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32)
    viewer = DummyViewer(
        [
            Labels(labels, "cells", metadata={"task": "cytoplasmic"}),
            Image(image, "chan1"),
        ]
    )
    data = MarkerFeatureData(
        segmentations=[MarkerSegmentationConfig(label="cells")],
        channels=[MarkerChannelConfig(name="Ch1", channel="chan1")],
    )
    feature = FeatureConfig(name="Markers", type_name="Markers", data=data)

    outputs = list(export_marker(feature, tmp_path, viewer=viewer, export_format="csv"))
    csv_paths = [path for path in outputs if path.suffix == ".csv"]
    assert csv_paths

    with csv_paths[0].open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert rows
    assert all(row.get("segmentation_type") == "cytoplasmic" for row in rows)


class TestBuildCrossSegmentationMap:
    """Test the _build_cross_segmentation_map function."""

    def test_single_segmentation(self):
        """Test with a single segmentation (no overlaps)."""
        labels = np.array([[1, 1, 0], [1, 1, 0], [0, 0, 0]], dtype=np.uint16)
        label_ids = np.array([1])
        all_segs = {"nuclear": (labels, label_ids)}

        cross_map = _build_cross_segmentation_map(all_segs)

        assert ("nuclear", 1) in cross_map
        assert cross_map[("nuclear", 1)] == []

    def test_two_segmentations_overlapping(self):
        """Test two segmentations with overlapping labels."""
        # Nuclear labels: nuc1 at [0:2,0:2], nuc2 at [0:2,2]
        # Cyto labels: cyto1 at [0:2,0:2], cyto2 at [0:2,2]
        # So: nuc1 overlaps cyto1&cyto2, nuc2 overlaps cyto1&cyto2
        nuc_labels = np.array(
            [[1, 1, 2], [1, 1, 2], [3, 3, 0]], dtype=np.uint16,
        )
        nuc_ids = np.array([1, 2, 3])
        cyto_labels = np.array(
            [[1, 1, 1], [2, 2, 2], [2, 2, 0]], dtype=np.uint16,
        )
        cyto_ids = np.array([1, 2])

        all_segs = {
            "nuclear": (nuc_labels, nuc_ids),
            "cytoplasmic": (cyto_labels, cyto_ids),
        }

        cross_map = _build_cross_segmentation_map(all_segs)

        # Nuclear region 1 overlaps with both cyto regions (cyto 1 and 2)
        assert ("nuclear", 1) in cross_map
        overlaps_nuc1 = cross_map[("nuclear", 1)]
        assert len(overlaps_nuc1) == 2
        assert ("cytoplasmic", 1) in overlaps_nuc1
        assert ("cytoplasmic", 2) in overlaps_nuc1

        # Nuclear region 2 also overlaps with both cyto regions
        assert ("nuclear", 2) in cross_map
        overlaps_nuc2 = cross_map[("nuclear", 2)]
        assert len(overlaps_nuc2) == 2
        assert ("cytoplasmic", 1) in overlaps_nuc2
        assert ("cytoplasmic", 2) in overlaps_nuc2

    def test_no_overlap(self):
        """Test segmentations with no overlapping labels."""
        nuc_labels = np.array(
            [[1, 1, 0], [1, 1, 0], [0, 0, 0]], dtype=np.uint16
        )
        nuc_ids = np.array([1])
        cyto_labels = np.array(
            [[0, 0, 2], [0, 0, 2], [0, 0, 0]], dtype=np.uint16
        )
        cyto_ids = np.array([2])

        all_segs = {
            "nuclear": (nuc_labels, nuc_ids),
            "cytoplasmic": (cyto_labels, cyto_ids),
        }

        cross_map = _build_cross_segmentation_map(all_segs)

        # No overlaps expected
        assert cross_map[("nuclear", 1)] == []


class TestAddCrossReferenceColumn:
    """Test the _add_cross_reference_column function."""

    def test_add_overlaps_with_column(self):
        """Test adding overlaps_with column to rows."""
        rows = [
            {"label_id": 1},
            {"label_id": 2},
        ]
        label_ids = np.array([1, 2])
        cross_map = {
            ("nuclear", 1): [("cytoplasmic", 10), ("cytoplasmic", 11)],
            ("nuclear", 2): [("cytoplasmic", 20)],
        }

        col_name = _add_cross_reference_column(
            rows, "nuclear", label_ids, cross_map
        )

        assert col_name == "overlaps_with"
        assert rows[0]["overlaps_with"] == "cytoplasmic_10;cytoplasmic_11"
        assert rows[1]["overlaps_with"] == "cytoplasmic_20"

    def test_empty_overlaps(self):
        """Test when label has no overlaps."""
        rows = [{"label_id": 5}]
        label_ids = np.array([5])
        cross_map = {("nuclear", 5): []}

        _add_cross_reference_column(rows, "nuclear", label_ids, cross_map)

        assert rows[0]["overlaps_with"] == ""

    def test_missing_label_in_map(self):
        """Test when label is not in cross_map."""
        rows = [{"label_id": 99}]
        label_ids = np.array([99])
        cross_map = {}  # Empty map

        _add_cross_reference_column(rows, "nuclear", label_ids, cross_map)

        assert rows[0]["overlaps_with"] == ""


class TestCrossSegmentationIntegration:
    """Integration tests for cross-segmentation workflow."""

    def test_full_workflow(self):
        """Test the full workflow from labels to export rows."""
        # Create nuclear and cytoplasmic segmentations
        # Nuclear region 1 at [0:2, 0:2]
        # Cyto region 1 at [0:2, 0:2], cyto region 2 at [0:2, 2] (non-overlapping)
        # So nuclear 1 overlaps with only cyto 1
        nuc_labels = np.array(
            [[1, 1, 0], [1, 1, 0], [0, 0, 0]], dtype=np.uint16,
        )
        nuc_ids = np.array([1])

        cyto_labels = np.array(
            [[1, 1, 2], [1, 1, 2], [0, 0, 0]], dtype=np.uint16,
        )
        cyto_ids = np.array([1, 2])

        # Build cross-reference map
        all_segs = {
            "nuclear": (nuc_labels, nuc_ids),
            "cytoplasmic": (cyto_labels, cyto_ids),
        }
        cross_map = _build_cross_segmentation_map(all_segs)

        # Create nuclear export rows
        nuc_rows = [
            {"label_id": 1, "area": 4},
        ]
        nuc_label_ids = np.array([1])

        # Add cross-reference column to nuclear rows
        _add_cross_reference_column(
            nuc_rows, "nuclear", nuc_label_ids, cross_map,
        )

        # Verify: nuclear 1 overlaps with only cyto 1 (cyto 2 is outside nuc1 region)
        assert nuc_rows[0]["overlaps_with"] == "cytoplasmic_1"

    def test_cytoplasmic_rows_in_cross_map(self):
        """Test adding cross-references to cytoplasmic rows."""
        # Create labels where cyto 1 overlaps with nuc 1
        nuc_labels = np.array(
            [[1, 1, 0], [1, 1, 0], [0, 0, 0]], dtype=np.uint16
        )
        nuc_ids = np.array([1])

        cyto_labels = np.array(
            [[1, 1, 2], [1, 1, 2], [0, 0, 0]], dtype=np.uint16
        )
        cyto_ids = np.array([1, 2])

        all_segs = {
            "nuclear": (nuc_labels, nuc_ids),
            "cytoplasmic": (cyto_labels, cyto_ids),
        }
        cross_map = _build_cross_segmentation_map(all_segs)

        # Create cytoplasmic rows
        cyto_rows = [
            {"label_id": 1, "area": 4},
            {"label_id": 2, "area": 2},
        ]
        cyto_label_ids = np.array([1, 2])

        # Add cross-references to cyto rows
        # (Note: cyto rows would not have entries in cross_map
        # since we only built forward references above)
        _add_cross_reference_column(
            cyto_rows, "cytoplasmic", cyto_label_ids, cross_map
        )

        # Both cyto regions will have empty overlaps (no backward references)
        assert cyto_rows[0]["overlaps_with"] == ""
        assert cyto_rows[1]["overlaps_with"] == ""
