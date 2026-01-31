"""Tests for the perinuclear rings model."""

from __future__ import annotations

import numpy as np
import pytest

from senoquant.tabs.segmentation.models.perinuclear_rings.model import (
    PerinuclearRingsModel,
)


class MockLayer:
    """Mock napari layer for testing."""

    def __init__(self, data: np.ndarray) -> None:
        self.data = data


def test_perinuclear_rings_basic() -> None:
    """Test basic perinuclear ring generation.

    Returns
    -------
    None
    """
    # Create a simple nuclear mask with one label
    nuclear_data = np.zeros((50, 50), dtype=np.uint32)
    nuclear_data[20:30, 20:30] = 1  # 10x10 nucleus

    nuclear_layer = MockLayer(nuclear_data)
    model = PerinuclearRingsModel()

    result = model.run(
        task="cytoplasmic",
        nuclear_layer=nuclear_layer,
        settings={"erosion_px": 2, "dilation_px": 5},
    )

    masks = result["masks"]
    
    # Check that we got a result
    assert masks is not None
    assert masks.shape == nuclear_data.shape
    
    # Check that the ring has the same label ID
    assert np.max(masks) == 1
    
    # Check that original nucleus center is eroded away
    assert masks[25, 25] == 0  # Center should be eroded
    
    # Check that there's dilation outside the original nucleus
    assert masks[15, 25] == 1  # Should be dilated outward


def test_perinuclear_rings_multiple_nuclei() -> None:
    """Test perinuclear rings with multiple nuclei.

    Returns
    -------
    None
    """
    # Create nuclear mask with two separate labels
    nuclear_data = np.zeros((60, 60), dtype=np.uint32)
    nuclear_data[10:20, 10:20] = 1  # First nucleus
    nuclear_data[35:45, 35:45] = 2  # Second nucleus

    nuclear_layer = MockLayer(nuclear_data)
    model = PerinuclearRingsModel()

    result = model.run(
        task="cytoplasmic",
        nuclear_layer=nuclear_layer,
        settings={"erosion_px": 1, "dilation_px": 3},
    )

    masks = result["masks"]
    
    # Check that both labels are present in the output
    unique_labels = np.unique(masks)
    unique_labels = unique_labels[unique_labels > 0]
    assert len(unique_labels) == 2
    assert 1 in unique_labels
    assert 2 in unique_labels


def test_perinuclear_rings_minimum_erosion() -> None:
    """Test that minimum erosion is enforced.

    Returns
    -------
    None
    """
    nuclear_data = np.zeros((30, 30), dtype=np.uint32)
    nuclear_data[10:20, 10:20] = 1

    nuclear_layer = MockLayer(nuclear_data)
    model = PerinuclearRingsModel()

    # Try to set erosion to 0 (should be clamped to 1)
    result = model.run(
        task="cytoplasmic",
        nuclear_layer=nuclear_layer,
        settings={"erosion_px": 0, "dilation_px": 2},
    )

    masks = result["masks"]
    
    # Should still produce rings (erosion clamped to 1)
    assert np.sum(masks > 0) > 0


def test_perinuclear_rings_requires_nuclear_task() -> None:
    """Test that only cytoplasmic task is supported.

    Returns
    -------
    None
    """
    nuclear_data = np.zeros((30, 30), dtype=np.uint32)
    nuclear_data[10:20, 10:20] = 1

    nuclear_layer = MockLayer(nuclear_data)
    model = PerinuclearRingsModel()

    with pytest.raises(ValueError, match="cytoplasmic"):
        model.run(
            task="nuclear",
            nuclear_layer=nuclear_layer,
            settings={},
        )


def test_perinuclear_rings_requires_nuclear_layer() -> None:
    """Test that nuclear layer is required.

    Returns
    -------
    None
    """
    model = PerinuclearRingsModel()

    with pytest.raises(ValueError, match="Nuclear layer is required"):
        model.run(
            task="cytoplasmic",
            nuclear_layer=None,
            settings={},
        )


def test_perinuclear_rings_overlap_guarantee() -> None:
    """Test that rings maintain at least 1 pixel overlap with original nuclei.

    Returns
    -------
    None
    """
    # Create a larger nuclear mask
    nuclear_data = np.zeros((50, 50), dtype=np.uint32)
    nuclear_data[20:35, 20:35] = 1  # 15x15 nucleus

    nuclear_layer = MockLayer(nuclear_data)
    model = PerinuclearRingsModel()

    # Use minimal erosion (will be 1 px) and no dilation
    result = model.run(
        task="cytoplasmic",
        nuclear_layer=nuclear_layer,
        settings={"erosion_px": 1, "dilation_px": 0},
    )

    masks = result["masks"]
    
    # Check that there's overlap with the original nucleus boundary
    # The ring should include the original boundary pixels
    original_boundary_pixels = 0
    for i in range(20, 35):
        for j in range(20, 35):
            if nuclear_data[i, j] == 1:
                # Check if this is a boundary pixel
                is_boundary = (
                    i == 20 or i == 34 or j == 20 or j == 34
                )
                if is_boundary and masks[i, j] == 1:
                    original_boundary_pixels += 1
    
    # Should have some overlap with original boundary
    assert original_boundary_pixels > 0
