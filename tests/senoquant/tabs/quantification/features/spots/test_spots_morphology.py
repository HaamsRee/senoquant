"""Tests for spots morphology extraction."""

import numpy as np
import pytest
from skimage.measure import label as skmeasure_label

from senoquant.tabs.quantification.features.spots.morphology import (
    extract_morphology,
    add_morphology_columns,
)


def test_extract_morphology_basic():
    """Test basic morphology extraction for 2D image."""
    # Create a simple 2D image with one labeled region
    image = np.zeros((50, 50), dtype=np.uint8)
    image[10:20, 10:20] = 1

    labels = np.asarray(skmeasure_label(image))
    label_ids = np.array([1])

    morphology = extract_morphology(labels, label_ids)

    assert "morph_area" in morphology
    assert "morph_eccentricity" in morphology
    assert "morph_perimeter" in morphology
    assert "morph_circularity" in morphology
    assert len(morphology) > 5  # Should have multiple properties


def test_extract_morphology_with_pixel_sizes():
    """Test morphology extraction with physical pixel sizes."""
    image = np.zeros((50, 50), dtype=np.uint8)
    image[10:20, 10:20] = 1

    labels = np.asarray(skmeasure_label(image))
    label_ids = np.array([1])
    pixel_sizes = np.array([0.5, 0.5])  # 0.5 um per pixel

    morphology = extract_morphology(labels, label_ids, pixel_sizes)

    assert "morph_area_um2" in morphology
    # Physical area should be area_pixels * (0.5 * 0.5)
    expected_area = morphology["morph_area"][0] * 0.25
    assert np.isclose(morphology["morph_area_um2"][0], expected_area)


def test_add_morphology_columns():
    """Test integration of morphology columns into rows."""
    image = np.zeros((50, 50), dtype=np.uint8)
    image[10:20, 10:20] = 1
    image[30:35, 30:35] = 2

    labels = np.asarray(skmeasure_label(image))
    label_ids = np.array([1, 2])

    # Initialize rows (simulating what spots export does)
    rows = [{"label_id": 1}, {"label_id": 2}]

    column_names = add_morphology_columns(rows, labels, label_ids)

    assert len(column_names) > 0
    assert all(name in rows[0] for name in column_names)
    assert rows[0]["morph_area"] == 100  # 10x10
    assert rows[1]["morph_area"] == 25  # 5x5


def test_morphology_derived_metrics():
    """Test that derived metrics are computed correctly."""
    image = np.zeros((50, 50), dtype=np.uint8)
    image[10:20, 10:20] = 1

    labels = np.asarray(skmeasure_label(image))
    label_ids = np.array([1])

    morphology = extract_morphology(labels, label_ids)

    # Check that circularity and aspect_ratio are computed
    assert "morph_circularity" in morphology
    assert "morph_aspect_ratio" in morphology
    # For a square, circularity should be close to 1.0 (perfect circle is 1.0)
    assert morphology["morph_circularity"][0] > 0.9


def test_morphology_3d():
    """Test morphology extraction for 3D image."""
    image = np.zeros((50, 50, 50), dtype=np.uint8)
    image[10:20, 10:20, 10:20] = 1

    labels = np.asarray(skmeasure_label(image))
    label_ids = np.array([1])
    pixel_sizes = np.array([1.0, 1.0, 1.0])

    morphology = extract_morphology(labels, label_ids, pixel_sizes)

    # For 3D, "area" should be renamed to "volume"
    assert "morph_volume" in morphology
    assert "morph_volume_um3" in morphology
    assert "morph_area" not in morphology
    # Should not have circularity in 3D
    assert "morph_circularity" not in morphology
