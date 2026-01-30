"""Tests for segmentation frontend layer filtering and model input modes.

Notes
-----
Validates dynamic layer filtering based on model input modes.
"""

from __future__ import annotations

import numpy as np
import pytest

from senoquant.tabs.batch.layers import Image as BatchImage
from senoquant.tabs.segmentation.backend import SegmentationBackend
from senoquant.tabs.segmentation.models.nuclear_dilation.model import (
    NuclearDilationModel,
)


def test_nuclear_dilation_input_modes() -> None:
    """Verify nuclear dilation has nuclear-only input mode.

    Returns
    -------
    None
    """
    backend = SegmentationBackend()
    model = backend.get_model("nuclear_dilation")

    modes = model.cytoplasmic_input_modes()

    assert modes == ["nuclear"]
    assert model.supports_task("cytoplasmic") is True
    assert model.supports_task("nuclear") is False


def test_nuclear_dilation_model_discovery() -> None:
    """Verify nuclear dilation model is discovered by backend.

    Returns
    -------
    None
    """
    backend = SegmentationBackend()
    cyto_models = backend.list_model_names(task="cytoplasmic")

    assert "nuclear_dilation" in cyto_models


def test_nuclear_dilation_compared_to_standard() -> None:
    """Verify nuclear dilation differs from standard models in input_modes.

    Returns
    -------
    None
    """
    backend = SegmentationBackend()
    nd_model = backend.get_model("nuclear_dilation")

    # Nuclear dilation should have nuclear-only mode
    nd_modes = nd_model.cytoplasmic_input_modes()
    assert nd_modes == ["nuclear"]

    # Other standard models should support nuclear+cytoplasmic
    other_cyto_models = [
        m
        for m in backend.list_model_names(task="cytoplasmic")
        if m != "nuclear_dilation"
    ]
    if other_cyto_models:
        other_model = backend.get_model(other_cyto_models[0])
        other_modes = other_model.cytoplasmic_input_modes()
        assert other_modes != ["nuclear"]


def test_nuclear_dilation_model_attributes() -> None:
    """Verify nuclear dilation model has expected attributes.

    Returns
    -------
    None
    """
    model = NuclearDilationModel()

    assert model.supports_task("cytoplasmic")
    assert not model.supports_task("nuclear")
    assert hasattr(model, "run")
    assert hasattr(model, "load_details")


def test_nuclear_dilation_has_dilation_setting() -> None:
    """Verify nuclear dilation model exposes dilation_iterations setting.

    Returns
    -------
    None
    """
    model = NuclearDilationModel()
    details = model.load_details()

    assert "settings" in details
    settings = details.get("settings", [])
    setting_keys = [s.get("key") for s in settings]
    assert "dilation_iterations" in setting_keys


def test_nuclear_dilation_setting_bounds() -> None:
    """Verify dilation_iterations has proper min/max bounds.

    Returns
    -------
    None

    """
    model = NuclearDilationModel()
    details = model.load_details()

    settings = details.get("settings", [])
    dilation_setting = next(
        (s for s in settings if s.get("key") == "dilation_iterations"),
        None,
    )

    assert dilation_setting is not None
    assert dilation_setting.get("min") == 1
    assert dilation_setting.get("max") == 100
    assert dilation_setting.get("default") == 5


def test_nuclear_dilation_preserves_label_ids_integration() -> None:
    """Verify that nuclear dilation preserves label IDs in model output.

    Returns
    -------
    None

    """
    model = NuclearDilationModel()

    # Create a simple mask with specific label IDs
    mask = np.zeros((20, 20), dtype=np.uint32)
    mask[2:5, 2:5] = 1
    mask[10:13, 10:13] = 3
    mask[15:18, 15:18] = 5

    layer = BatchImage(mask, "test", {})

    # Run the model
    result = model.run(task="cytoplasmic", nuclear_layer=layer, settings={})

    assert "masks" in result
    output_mask = result["masks"]

    # Check that original label IDs are preserved
    unique_labels = set(output_mask.flatten()) - {0}
    assert 1 in unique_labels or 3 in unique_labels or 5 in unique_labels
