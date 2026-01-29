"""Tests for CPSAM model utilities.

Notes
-----
Validates input preparation and error handling without running Cellpose.
"""

from __future__ import annotations

import numpy as np
import pytest

from senoquant.tabs.segmentation.models.cpsam.model import CPSAMModel


def test_prepare_input_2d_single_channel() -> None:
    """Return single-channel 2D input.

    Returns
    -------
    None
    """
    model = CPSAMModel(models_root=None)
    data = np.zeros((4, 4), dtype=np.float32)
    output = model._prepare_input(data)
    assert output.shape == (4, 4)


def test_prepare_input_2d_stacks_channels() -> None:
    """Stack nuclear and cytoplasmic channels for 2D input.

    Returns
    -------
    None
    """
    model = CPSAMModel(models_root=None)
    nuclear = np.zeros((4, 4), dtype=np.float32)
    cyto = np.ones((4, 4), dtype=np.float32)
    output = model._prepare_input(nuclear, cyto)
    assert output.shape == (2, 4, 4)


def test_prepare_input_mismatched_shapes() -> None:
    """Raise on mismatched nuclear/cytoplasmic shapes.

    Returns
    -------
    None
    """
    model = CPSAMModel(models_root=None)
    with pytest.raises(ValueError):
        model._prepare_input(np.zeros((4, 4)), np.zeros((3, 3)))
