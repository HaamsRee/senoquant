"""Tests for nuclear dilation model.

Notes
-----
Validates nuclear mask dilation preserves label IDs and handles edge cases.
"""

from __future__ import annotations

import numpy as np
import pytest

from senoquant.tabs.segmentation.models.nuclear_dilation.model import (
    NuclearDilationModel,
)


class MockLayer:
    """Mock napari layer for testing."""

    def __init__(self, data):
        """Initialize mock layer with data."""
        self.data = data


def test_nuclear_dilation_preserves_label_ids() -> None:
    """Verify dilated labels retain original IDs.

    Returns
    -------
    None
    """
    model = NuclearDilationModel(models_root=None)
    
    # Create nuclear mask with 3 distinct labels
    nuclear_mask = np.zeros((50, 50), dtype=np.uint32)
    nuclear_mask[10:15, 10:15] = 1
    nuclear_mask[30:35, 30:35] = 2
    nuclear_mask[20:25, 40:45] = 5  # Non-sequential ID
    
    nuclear_layer = MockLayer(nuclear_mask)
    
    result = model.run(
        task="cytoplasmic",
        nuclear_layer=nuclear_layer,
        settings={"dilation_iterations": 3}
    )
    
    dilated = result["masks"]
    
    # Check that original label IDs are preserved
    assert set(np.unique(dilated)) == {0, 1, 2, 5}
    
    # Check that dilation actually occurred (size increased)
    assert np.sum(dilated == 1) > np.sum(nuclear_mask == 1)
    assert np.sum(dilated == 2) > np.sum(nuclear_mask == 2)
    assert np.sum(dilated == 5) > np.sum(nuclear_mask == 5)
    
    # Check that original pixels are preserved
    assert np.all(dilated[nuclear_mask == 1] == 1)
    assert np.all(dilated[nuclear_mask == 2] == 2)
    assert np.all(dilated[nuclear_mask == 5] == 5)


def test_nuclear_dilation_default_iterations() -> None:
    """Use default iteration count when not specified.

    Returns
    -------
    None
    """
    model = NuclearDilationModel(models_root=None)
    
    nuclear_mask = np.zeros((30, 30), dtype=np.uint32)
    nuclear_mask[10:15, 10:15] = 1
    
    nuclear_layer = MockLayer(nuclear_mask)
    
    result = model.run(
        task="cytoplasmic",
        nuclear_layer=nuclear_layer,
        settings={}
    )
    
    dilated = result["masks"]
    
    # Should have dilated with default iterations (5)
    assert np.sum(dilated == 1) > np.sum(nuclear_mask == 1)


def test_nuclear_dilation_zero_iterations() -> None:
    """Handle zero iterations gracefully.

    Returns
    -------
    None
    """
    model = NuclearDilationModel(models_root=None)
    
    nuclear_mask = np.zeros((30, 30), dtype=np.uint32)
    nuclear_mask[10:15, 10:15] = 1
    
    nuclear_layer = MockLayer(nuclear_mask)
    
    # Zero iterations should be clamped to 1 (minimum)
    result = model.run(
        task="cytoplasmic",
        nuclear_layer=nuclear_layer,
        settings={"dilation_iterations": 0}
    )
    
    dilated = result["masks"]
    
    # Should still dilate (minimum 1 iteration)
    assert np.sum(dilated == 1) > np.sum(nuclear_mask == 1)


def test_nuclear_dilation_requires_nuclear_layer() -> None:
    """Raise when nuclear layer is missing.

    Returns
    -------
    None
    """
    model = NuclearDilationModel(models_root=None)
    
    with pytest.raises(ValueError, match="Nuclear layer is required"):
        model.run(
            task="cytoplasmic",
            nuclear_layer=None,
            settings={}
        )


def test_nuclear_dilation_wrong_task() -> None:
    """Raise when task is not cytoplasmic.

    Returns
    -------
    None
    """
    model = NuclearDilationModel(models_root=None)
    
    nuclear_mask = np.zeros((30, 30), dtype=np.uint32)
    nuclear_mask[10:15, 10:15] = 1
    nuclear_layer = MockLayer(nuclear_mask)
    
    with pytest.raises(ValueError, match="only supports cytoplasmic"):
        model.run(
            task="nuclear",
            nuclear_layer=nuclear_layer,
            settings={}
        )


def test_nuclear_dilation_3d() -> None:
    """Handle 3D nuclear masks correctly.

    Returns
    -------
    None
    """
    model = NuclearDilationModel(models_root=None)
    
    nuclear_mask = np.zeros((10, 30, 30), dtype=np.uint32)
    nuclear_mask[3:6, 10:15, 10:15] = 1
    nuclear_mask[5:8, 20:25, 20:25] = 2
    
    nuclear_layer = MockLayer(nuclear_mask)
    
    result = model.run(
        task="cytoplasmic",
        nuclear_layer=nuclear_layer,
        settings={"dilation_iterations": 2}
    )
    
    dilated = result["masks"]
    
    # Check label IDs preserved in 3D
    assert set(np.unique(dilated)) == {0, 1, 2}
    
    # Check dilation occurred in 3D
    assert np.sum(dilated == 1) > np.sum(nuclear_mask == 1)
    assert np.sum(dilated == 2) > np.sum(nuclear_mask == 2)


def test_nuclear_dilation_model_info() -> None:
    """Verify model metadata.

    Returns
    -------
    None
    """
    model = NuclearDilationModel(models_root=None)
    
    details = model.load_details()
    
    assert details["name"] == "nuclear_dilation"
    assert model.supports_task("cytoplasmic") is True
    assert model.supports_task("nuclear") is False
    assert model.cytoplasmic_input_modes() == ["nuclear"]
    
    settings = model.list_settings()
    assert len(settings) == 1
    assert settings[0]["key"] == "dilation_iterations"
    assert settings[0]["type"] == "int"
    assert settings[0]["default"] == 5
