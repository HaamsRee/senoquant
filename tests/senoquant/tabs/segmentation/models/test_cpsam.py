"""Tests for CPSAM model utilities.

Notes
-----
Validates input preparation and error handling without running Cellpose.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock
import numpy as np
import pytest

from senoquant.tabs.segmentation.models.cpsam import model as cpsam_module

CPSAMModel = cpsam_module.CPSAMModel


@pytest.fixture
def cellpose_constructor(monkeypatch):
    constructor = Mock()
    monkeypatch.setattr("cellpose.models.CellposeModel", constructor)
    return constructor


def test_constructor_propagates_download_failure(
    tmp_path, monkeypatch, cellpose_constructor,
) -> None:
    failure = RuntimeError("Model download failed")
    download = Mock(side_effect=failure)
    monkeypatch.setattr(cpsam_module, "ensure_hf_model", download)

    with pytest.raises(RuntimeError, match="Model download failed") as caught:
        CPSAMModel(models_root=tmp_path / "models")

    assert caught.value is failure
    download.assert_called_once()
    cellpose_constructor.assert_not_called()


@pytest.mark.parametrize("weights_kind", ("missing", "directory"))
def test_constructor_rejects_invalid_downloaded_weights(
    tmp_path, monkeypatch, cellpose_constructor, weights_kind,
) -> None:
    weights = tmp_path / "download-cache" / "cpsam"
    if weights_kind == "directory":
        weights.mkdir(parents=True)
    download = Mock(return_value=weights)
    monkeypatch.setattr(cpsam_module, "ensure_hf_model", download)

    with pytest.raises(FileNotFoundError):
        CPSAMModel(models_root=tmp_path / "models")

    download.assert_called_once()
    cellpose_constructor.assert_not_called()


@pytest.mark.parametrize("downloaded", (False, True))
def test_constructor_passes_local_weights_to_cellpose(
    tmp_path, monkeypatch, cellpose_constructor, downloaded,
) -> None:
    models_root = tmp_path / "models"
    weights = (
        tmp_path / "download-cache" / "cpsam"
        if downloaded else models_root / "cpsam" / "cpsam"
    )
    weights.parent.mkdir(parents=True)
    weights.write_bytes(b"test weights")
    download = Mock(return_value=weights)
    monkeypatch.setattr(cpsam_module, "ensure_hf_model", download)

    model = CPSAMModel(models_root=models_root)

    cellpose_constructor.assert_called_once_with(
        gpu=True, pretrained_model=str(weights),
    )
    assert model._model is cellpose_constructor.return_value
    if downloaded:
        download.assert_called_once_with(
            "cpsam", models_root / "cpsam", repo_id=cpsam_module.DEFAULT_REPO_ID,
        )
    else:
        download.assert_not_called()


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
