"""Tests for the perinuclear rings model."""

from __future__ import annotations

import numpy as np
import pytest
from scipy import ndimage as ndi

from senoquant.tabs.segmentation.models.perinuclear_rings.model import (
    PerinuclearRingsModel,
)


class MockLayer:
    """Mock napari layer for testing."""

    def __init__(self, data: np.ndarray) -> None:
        self.data = data


def _reference_perinuclear_rings(
    labels: np.ndarray,
    *,
    erosion_px: int,
    dilation_px: int,
) -> np.ndarray:
    """Reference implementation matching nearest-label ring semantics."""
    if dilation_px <= 0:
        output = labels.copy()
    elif not np.any(labels):
        output = np.zeros_like(labels)
    else:
        background_mask = labels == 0
        distances, nearest_indices = ndi.distance_transform_edt(
            background_mask,
            return_indices=True,
        )
        nearest_labels = labels[tuple(nearest_indices)]
        output = labels.copy()
        within_radius = background_mask & (distances <= float(dilation_px))
        output[within_radius] = nearest_labels[within_radius]

    for label_id in np.unique(labels):
        if label_id == 0:
            continue
        nucleus_mask = labels == label_id
        eroded_mask = ndi.binary_erosion(
            nucleus_mask,
            iterations=erosion_px,
        )
        output[eroded_mask & (output == label_id)] = 0
    return output


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


def test_perinuclear_rings_matches_reference_for_sparse_label_ids() -> None:
    """Match nearest-label reference for sparse/non-sequential labels."""
    model = PerinuclearRingsModel()

    nuclear_data = np.zeros((90, 90), dtype=np.uint32)
    nuclear_data[8:14, 8:14] = 4
    nuclear_data[34:42, 45:53] = 99
    nuclear_data[60:66, 20:27] = 1200

    result = model.run(
        task="cytoplasmic",
        nuclear_layer=MockLayer(nuclear_data),
        settings={"erosion_px": 2, "dilation_px": 4},
    )

    expected = _reference_perinuclear_rings(
        nuclear_data,
        erosion_px=2,
        dilation_px=4,
    )
    assert np.array_equal(result["masks"], expected)


def test_perinuclear_rings_zero_dilation_has_no_outward_growth() -> None:
    """Zero dilation should not create ring pixels outside nucleus masks."""
    model = PerinuclearRingsModel()

    nuclear_data = np.zeros((40, 40), dtype=np.uint32)
    nuclear_data[12:20, 12:20] = 7
    nuclear_data[24:32, 24:32] = 250

    result = model.run(
        task="cytoplasmic",
        nuclear_layer=MockLayer(nuclear_data),
        settings={"erosion_px": 1, "dilation_px": 0},
    )

    expected = _reference_perinuclear_rings(
        nuclear_data,
        erosion_px=1,
        dilation_px=0,
    )
    masks = result["masks"]
    assert np.array_equal(masks, expected)

    outside_original = (masks > 0) & (nuclear_data == 0)
    assert not np.any(outside_original)


def test_perinuclear_rings_assigns_overlap_by_nearest_nucleus() -> None:
    """Resolve outward overlap by nearest nucleus rather than write order."""
    model = PerinuclearRingsModel()

    nuclear_data = np.zeros((40, 40), dtype=np.uint32)
    nuclear_data[16:21, 10:15] = 1
    nuclear_data[16:21, 19:24] = 2

    result = model.run(
        task="cytoplasmic",
        nuclear_layer=MockLayer(nuclear_data),
        settings={"erosion_px": 1, "dilation_px": 5},
    )
    masks = result["masks"]

    # Columns 16 and 17 are in the overlap zone; each should map to nearest label.
    assert masks[18, 16] == 1
    assert masks[18, 17] == 2
