"""Tests for marker morphology extraction."""

from __future__ import annotations

import numpy as np
from skimage.measure import label as skmeasure_label

from senoquant.tabs.quantification.features.marker.morphology import (
    extract_morphology,
    add_morphology_columns,
)

AREA_REGION_1 = 400
AREA_REGION_2 = 900
AREA_UM2 = 400.0


def test_extract_morphology_basic() -> None:
    """Test basic morphology extraction on a simple 2D image."""
    image = np.zeros((100, 100), dtype=np.uint8)
    image[10:30, 10:30] = 1
    image[50:80, 50:80] = 2

    labels = np.asarray(skmeasure_label(image))
    label_ids = np.array([1, 2])

    morphology = extract_morphology(labels, label_ids)

    assert len(morphology) > 0
    assert "morph_area" in morphology
    assert morphology["morph_area"][0] == AREA_REGION_1
    assert morphology["morph_area"][1] == AREA_REGION_2


def test_extract_morphology_with_pixel_sizes() -> None:
    """Test morphology extraction with physical pixel sizes."""
    image = np.zeros((100, 100), dtype=np.uint8)
    image[10:30, 10:30] = 1

    labels = np.asarray(skmeasure_label(image))
    label_ids = np.array([1])
    pixel_sizes = np.array([1.0, 1.0])

    morphology = extract_morphology(labels, label_ids, pixel_sizes)

    assert "morph_area" in morphology
    assert "morph_area_um2" in morphology
    assert morphology["morph_area_um2"][0] == AREA_UM2


def test_add_morphology_columns() -> None:
    """Test adding morphology columns to export rows."""
    image = np.zeros((100, 100), dtype=np.uint8)
    image[10:30, 10:30] = 1

    labels = np.asarray(skmeasure_label(image))
    label_ids = np.array([1])
    pixel_sizes = np.array([1.0, 1.0])

    rows = [{"label_id": 1.0}]
    columns = add_morphology_columns(rows, labels, label_ids, pixel_sizes)

    assert len(columns) > 0
    assert len(rows[0]) > 1
    assert "morph_area" in rows[0]
    assert rows[0]["morph_area"] == AREA_UM2


def test_morphology_derived_metrics() -> None:
    """Test that derived metrics like circularity are computed."""
    image = np.zeros((100, 100), dtype=np.uint8)
    image[10:30, 10:30] = 1

    labels = np.asarray(skmeasure_label(image))
    label_ids = np.array([1])

    morphology = extract_morphology(labels, label_ids)

    assert "morph_circularity" in morphology
    assert "morph_aspect_ratio" in morphology


def test_morphology_3d() -> None:
    """Test morphology extraction on 3D data."""
    image = np.zeros((50, 50, 50), dtype=np.uint8)
    image[10:20, 10:20, 10:20] = 1

    labels = np.asarray(skmeasure_label(image))
    label_ids = np.array([1])
    pixel_sizes = np.array([1.0, 1.0, 1.0])

    morphology = extract_morphology(labels, label_ids, pixel_sizes)

    assert "morph_volume" in morphology
    assert "morph_volume_um3" in morphology



