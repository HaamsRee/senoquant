"""Tests for CPSAM model utilities.

Notes
-----
Validates input preparation and error handling without running Cellpose.
"""

from __future__ import annotations

from types import SimpleNamespace
import numpy as np
import pytest

from senoquant.tabs.segmentation.models.cpsam.model import CPSAMModel


def test_prepare_input_2d_single_channel() -> None:
    """Return single-channel 2D input.

    Returns
    -------
    None
    """
    model = CPSAMModel.__new__(CPSAMModel)
    data = np.zeros((4, 4), dtype=np.float32)
    output = model._prepare_input(data)
    assert output.shape == (4, 4)


def test_prepare_input_2d_stacks_channels() -> None:
    """Stack nuclear and cytoplasmic channels for 2D input.

    Returns
    -------
    None
    """
    model = CPSAMModel.__new__(CPSAMModel)
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
    model = CPSAMModel.__new__(CPSAMModel)
    with pytest.raises(ValueError):
        model._prepare_input(np.zeros((4, 4)), np.zeros((3, 3)))


def test_run_nuclear_auto_detects_3d_and_always_normalizes() -> None:
    """Infer 3D mode from image ndim and force normalization on."""
    eval_calls: list[dict[str, object]] = []

    class FakeCellposeModel:
        def eval(self, input_data, **kwargs):
            eval_calls.append({"input_data": input_data, "kwargs": kwargs})
            masks = np.zeros_like(input_data, dtype=np.int32)
            return masks, [], []

    model = CPSAMModel.__new__(CPSAMModel)
    model._model = FakeCellposeModel()

    layer = SimpleNamespace(data=np.zeros((3, 6, 6), dtype=np.float32))
    result = model.run(
        task="nuclear",
        layer=layer,
        settings={"use_3d": False, "normalize": False},
    )

    assert "masks" in result
    assert eval_calls
    kwargs = eval_calls[0]["kwargs"]
    assert kwargs["do_3D"] is True
    assert kwargs["z_axis"] == 0
    assert kwargs["normalize"] is True


def test_run_cytoplasmic_2d_stacked_input_stays_2d() -> None:
    """Use 2D Cellpose mode even when channels are stacked into CYX."""
    eval_calls: list[dict[str, object]] = []

    class FakeCellposeModel:
        def eval(self, input_data, **kwargs):
            eval_calls.append({"input_data": input_data, "kwargs": kwargs})
            masks = np.zeros(input_data.shape[-2:], dtype=np.int32)
            return masks, [], []

    model = CPSAMModel.__new__(CPSAMModel)
    model._model = FakeCellposeModel()

    cyto_layer = SimpleNamespace(data=np.zeros((8, 8), dtype=np.float32))
    nuclear_layer = SimpleNamespace(data=np.ones((8, 8), dtype=np.float32))
    model.run(
        task="cytoplasmic",
        cytoplasmic_layer=cyto_layer,
        nuclear_layer=nuclear_layer,
        settings={},
    )

    assert eval_calls
    call = eval_calls[0]
    kwargs = call["kwargs"]
    assert call["input_data"].shape == (2, 8, 8)
    assert kwargs["do_3D"] is False
    assert kwargs["z_axis"] is None
    assert kwargs["normalize"] is True
