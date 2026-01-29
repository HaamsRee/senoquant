"""Tests for batch backend workflows.

Notes
-----
Uses lightweight stub backends and I/O helpers to validate batch
processing control flow.
"""

from __future__ import annotations

from pathlib import Path
import types

import numpy as np

from senoquant.tabs.batch import backend as batch_backend
from senoquant.tabs.batch.config import BatchChannelConfig


class DummySegmentationModel:
    """Segmentation model stub."""

    def run(self, **_kwargs):
        return {"masks": np.ones((2, 2), dtype=np.uint16)}

    def supports_task(self, _task: str) -> bool:
        return True


class DummySegmentationBackend:
    """Segmentation backend stub."""

    def get_model(self, _name: str):
        return DummySegmentationModel()

    def get_preloaded_model(self, name: str):
        return self.get_model(name)


class DummyDetector:
    """Spot detector stub."""

    def run(self, **_kwargs):
        return {"mask": np.ones((2, 2), dtype=np.uint16)}


class DummySpotsBackend:
    """Spots backend stub."""

    def get_detector(self, _name: str):
        return DummyDetector()


class DummyQuantResult:
    """Quantification result stub."""

    def __init__(self, output_root: Path) -> None:
        self.output_root = output_root


class DummyQuantBackend:
    """Quantification backend stub."""

    def process(self, _features, output_dir: str, _name: str, _fmt: str):
        return DummyQuantResult(Path(output_dir))


def test_process_folder_no_tasks(tmp_path: Path) -> None:
    """Return an empty summary when no tasks are enabled.

    Returns
    -------
    None
    """
    backend = batch_backend.BatchBackend(
        segmentation_backend=DummySegmentationBackend(),
        spots_backend=DummySpotsBackend(),
    )
    summary = backend.process_folder(
        input_path=str(tmp_path),
        output_path=str(tmp_path / "out"),
    )
    assert summary.processed == 0
    assert summary.failed == 0


def test_process_folder_runs_detection(tmp_path: Path, monkeypatch) -> None:
    """Run segmentation and spots on a mocked file.

    Returns
    -------
    None
    """
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    input_file = input_dir / "sample.tif"
    input_file.write_text("data")

    output_dir = tmp_path / "output"

    def fake_iter_input_files(_root, _exts, _include):
        yield input_file

    def fake_load_channel_data(_path, _index, _scene_id):
        return np.ones((2, 2), dtype=np.float32), {"physical_pixel_sizes": {"Y": 1.0, "X": 1.0}}

    def fake_write_array(out_dir, name, data, fmt):
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{name}.npy"
        np.save(path, data)
        return path

    monkeypatch.setattr(batch_backend, "iter_input_files", fake_iter_input_files)
    monkeypatch.setattr(batch_backend, "load_channel_data", fake_load_channel_data)
    monkeypatch.setattr(batch_backend, "write_array", fake_write_array)
    monkeypatch.setattr(batch_backend, "QuantificationBackend", DummyQuantBackend)

    backend = batch_backend.BatchBackend(
        segmentation_backend=DummySegmentationBackend(),
        spots_backend=DummySpotsBackend(),
    )

    summary = backend.process_folder(
        input_path=str(input_dir),
        output_path=str(output_dir),
        nuclear_model="nuclear",
        nuclear_channel=0,
        spot_detector="udwt",
        spot_channels=[0],
        channel_map=[BatchChannelConfig(name="Channel 0", index=0)],
    )

    assert summary.processed == 1
    assert summary.failed == 0
    outputs = summary.results[0].outputs
    assert "nuclear_labels" in outputs
    assert "spot_labels_0" in outputs


def test_apply_quantification_viewer_sets_viewer() -> None:
    """Attach viewer to quantification handlers.

    Returns
    -------
    None
    """
    viewer = batch_backend.BatchViewer([])

    class DummyHandler:
        def __init__(self):
            self._tab = types.SimpleNamespace(_viewer=None)

    class DummyContext:
        def __init__(self):
            self.feature_handler = DummyHandler()

    contexts = [DummyContext()]
    tab = types.SimpleNamespace(_viewer=None)

    batch_backend._apply_quantification_viewer(contexts, tab, viewer)
    assert tab._viewer is viewer
    assert contexts[0].feature_handler._tab._viewer is viewer
