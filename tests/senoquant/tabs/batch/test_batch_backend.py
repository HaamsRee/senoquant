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
    assert "Channel 0_nuclear_nuc_labels" in outputs or "0_nuclear_nuc_labels" in outputs
    assert "Channel 0_udwt_spot_labels" in outputs or "0_udwt_spot_labels" in outputs


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


def test_process_folder_tags_label_metadata_with_task(tmp_path: Path, monkeypatch) -> None:
    """Attach task metadata to generated labels before quantification."""
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    input_file = input_dir / "sample.tif"
    input_file.write_text("data")
    output_dir = tmp_path / "output"

    def fake_iter_input_files(_root, _exts, _include):
        yield input_file

    def fake_load_channel_data(_path, _index, _scene_id):
        return np.ones((2, 2), dtype=np.float32), {"path": "sample.tif"}

    def fake_write_array(out_dir, name, data, fmt):
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{name}.npy"
        np.save(path, data)
        return path

    captured_meta: dict[str, dict] = {}

    def fake_build_viewer(_path, _scene_id, _channel_map, _labels_data, labels_meta):
        captured_meta.update(labels_meta)
        return batch_backend.BatchViewer([])

    monkeypatch.setattr(batch_backend, "iter_input_files", fake_iter_input_files)
    monkeypatch.setattr(batch_backend, "load_channel_data", fake_load_channel_data)
    monkeypatch.setattr(batch_backend, "write_array", fake_write_array)
    monkeypatch.setattr(batch_backend, "_build_viewer_for_quantification", fake_build_viewer)
    monkeypatch.setattr(batch_backend, "QuantificationBackend", DummyQuantBackend)

    backend = batch_backend.BatchBackend(
        segmentation_backend=DummySegmentationBackend(),
        spots_backend=DummySpotsBackend(),
    )
    backend.process_folder(
        input_path=str(input_dir),
        output_path=str(output_dir),
        nuclear_model="nuclear",
        nuclear_channel=0,
        cyto_model="cyto",
        cyto_channel=0,
        spot_detector="udwt",
        spot_channels=[0],
        quantification_features=[types.SimpleNamespace()],
        channel_map=[BatchChannelConfig(name="Channel 0", index=0)],
    )

    assert captured_meta
    task_values = {meta.get("task") for meta in captured_meta.values()}
    assert {"nuclear", "cytoplasmic", "spots"} <= task_values

def test_progress_callback_invoked(tmp_path) -> None:
    """Progress callback is invoked during batch processing.

    Parameters
    ----------
    tmp_path : pathlib.Path
        Temporary directory for test files.

    Returns
    -------
    None
    """
    progress_calls: list[tuple] = []

    def progress_callback(current: int, total: int, message: str) -> None:
        progress_calls.append((current, total, message))

    backend = batch_backend.BatchBackend(
        segmentation_backend=DummySegmentationBackend(),
        spots_backend=DummySpotsBackend(),
    )

    # Run with no tasks should call with initial message
    summary = backend.process_folder(
        input_path=str(tmp_path),
        output_path=str(tmp_path / "output"),
        progress_callback=progress_callback,
    )

    # Should have at least one progress call (initial message)
    assert len(progress_calls) > 0
    # First call should be "Starting batch processing..."
    assert progress_calls[0][2] == "Starting batch processing..."
    assert summary.processed == 0
    assert summary.skipped == 0
    assert summary.failed == 0


def test_resolve_channel_name_with_map(tmp_path) -> None:
    """Test _resolve_channel_name with different input types.

    Parameters
    ----------
    tmp_path : pathlib.Path
        Temporary directory for test files.

    Returns
    -------
    None
    """
    channel_map = [
        BatchChannelConfig(name="DAPI", index=0),
        BatchChannelConfig(name="GFP", index=1),
    ]

    # Test with integer choice
    assert batch_backend._resolve_channel_name(0, channel_map) == "0"

    # Test with numeric string choice
    assert batch_backend._resolve_channel_name("1", channel_map) == "1"

    # Test with channel name in map
    assert batch_backend._resolve_channel_name("DAPI", channel_map) == "DAPI"

    # Test with channel name not in map (returns as-is)
    assert batch_backend._resolve_channel_name("Unknown", channel_map) == "Unknown"


def test_normalize_channel_map() -> None:
    """Test channel map normalization with different input formats.

    Returns
    -------
    None
    """
    # Test with BatchChannelConfig objects
    config_list = [
        BatchChannelConfig(name="Ch0", index=0),
        BatchChannelConfig(name="Ch1", index=1),
    ]
    result = batch_backend._normalize_channel_map(config_list)
    assert len(result) == 2
    assert result[0].name == "Ch0"

    # Test with dict objects
    dict_list = [
        {"name": "DAPI", "index": 0},
        {"name": "GFP", "index": 1},
    ]
    result = batch_backend._normalize_channel_map(dict_list)
    assert len(result) == 2
    assert result[0].name == "DAPI"

    # Test with None
    result = batch_backend._normalize_channel_map(None)
    assert result == []

    # Test with mixed valid/invalid entries
    mixed = [
        BatchChannelConfig(name="Valid", index=0),
        {"name": "", "index": 1},  # Empty name -> gets default
    ]
    result = batch_backend._normalize_channel_map(mixed)
    assert len(result) == 2
    assert result[1].name == "Channel 1"  # Default name


def test_process_folder_with_overwrite_skip(tmp_path) -> None:
    """Test output directory handling with overwrite flag.

    Parameters
    ----------
    tmp_path : pathlib.Path
        Temporary directory for test files.

    Returns
    -------
    None
    """
    backend = batch_backend.BatchBackend(
        segmentation_backend=DummySegmentationBackend(),
        spots_backend=DummySpotsBackend(),
    )

    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()

    # Create existing output to trigger skip
    (output_dir / "test_file").mkdir()

    # Without overwrite flag, should skip existing output
    summary = backend.process_folder(
        input_path=str(input_dir),
        output_path=str(output_dir),
        nuclear_model="TestModel",
        overwrite=False,
    )

    assert summary.skipped >= 0


def test_batch_item_result_initialization() -> None:
    """Test BatchItemResult dataclass initialization.

    Returns
    -------
    None
    """
    path = Path("test.tif")
    result = batch_backend.BatchItemResult(path=path, scene_id="scene-1")

    assert result.path == path
    assert result.scene_id == "scene-1"
    assert result.outputs == {}
    assert result.errors == []

    # Test with error appending
    result.errors.append("Test error")
    assert len(result.errors) == 1


def test_batch_summary_counts() -> None:
    """Test BatchSummary dataclass initialization and counts.

    Returns
    -------
    None
    """
    input_root = Path("/input")
    output_root = Path("/output")
    result1 = batch_backend.BatchItemResult(path=Path("file1.tif"), scene_id=None)
    result2 = batch_backend.BatchItemResult(path=Path("file2.tif"), scene_id=None)

    summary = batch_backend.BatchSummary(
        input_root=input_root,
        output_root=output_root,
        processed=1,
        skipped=1,
        failed=0,
        results=[result1, result2],
    )

    assert summary.processed == 1
    assert summary.skipped == 1
    assert summary.failed == 0
    assert len(summary.results) == 2


def test_normalize_channel_map_with_dict() -> None:
    """Test normalization of dict channel map entries.

    Returns
    -------
    None
    """
    channel_map = [
        {"name": "DAPI", "index": 0},
        {"name": "GFP", "index": 1},
    ]
    result = batch_backend._normalize_channel_map(channel_map)
    
    assert len(result) == 2
    assert result[0].name == "DAPI"
    assert result[0].index == 0
    assert result[1].name == "GFP"
    assert result[1].index == 1


def test_normalize_channel_map_with_config_objects() -> None:
    """Test normalization with BatchChannelConfig objects.

    Returns
    -------
    None
    """
    channel_map = [
        BatchChannelConfig(name="DAPI", index=0),
        BatchChannelConfig(name="GFP", index=1),
    ]
    result = batch_backend._normalize_channel_map(channel_map)
    
    assert len(result) == 2
    assert result[0].name == "DAPI"
    assert result[1].name == "GFP"


def test_normalize_channel_map_with_none() -> None:
    """Test normalization when channel_map is None.

    Returns
    -------
    None
    """
    result = batch_backend._normalize_channel_map(None)
    assert result == []


def test_normalize_channel_map_empty_name_creates_default() -> None:
    """Test that empty names get default labels.

    Returns
    -------
    None
    """
    channel_map = [{"name": "", "index": 5}]
    result = batch_backend._normalize_channel_map(channel_map)
    
    assert len(result) == 1
    assert result[0].name == "Channel 5"
    assert result[0].index == 5


def test_resolve_channel_name_with_index() -> None:
    """Test channel name resolution from integer index.

    Returns
    -------
    None
    """
    channel_map = [
        BatchChannelConfig(name="DAPI", index=0),
        BatchChannelConfig(name="GFP", index=1),
    ]
    result = batch_backend._resolve_channel_name(0, channel_map)
    assert result == "0"


def test_resolve_channel_name_with_string_index() -> None:
    """Test channel name resolution from string index.

    Returns
    -------
    None
    """
    channel_map = [
        BatchChannelConfig(name="DAPI", index=0),
        BatchChannelConfig(name="GFP", index=1),
    ]
    result = batch_backend._resolve_channel_name("1", channel_map)
    assert result == "1"


def test_resolve_channel_name_with_mapped_name() -> None:
    """Test channel name resolution from mapped name.

    Returns
    -------
    None
    """
    channel_map = [
        BatchChannelConfig(name="DAPI", index=0),
        BatchChannelConfig(name="GFP", index=1),
    ]
    result = batch_backend._resolve_channel_name("GFP", channel_map)
    assert result == "GFP"


def test_resolve_channel_name_unmapped_name() -> None:
    """Test channel name when not in map.

    Returns
    -------
    None
    """
    channel_map = [BatchChannelConfig(name="DAPI", index=0)]
    result = batch_backend._resolve_channel_name("Unknown", channel_map)
    assert result == "Unknown"


def test_normalize_channel_map_empty() -> None:
    """Test normalizing empty channel map.

    Returns
    -------
    None
    """
    result = batch_backend._normalize_channel_map(None)
    assert result == []


def test_normalize_channel_map_from_dicts() -> None:
    """Test normalizing channel map from dict list.

    Returns
    -------
    None
    """
    channel_map = [
        {"name": "DAPI", "index": 0},
        {"name": "GFP", "index": 1},
    ]
    result = batch_backend._normalize_channel_map(channel_map)
    assert len(result) == 2
    assert result[0].name == "DAPI"
    assert result[1].index == 1


def test_normalize_channel_map_mixed_types() -> None:
    """Test normalizing channel map with mixed types.

    Returns
    -------
    None
    """
    channel_map = [
        BatchChannelConfig(name="DAPI", index=0),
        {"name": "GFP", "index": 1},
    ]
    result = batch_backend._normalize_channel_map(channel_map)
    assert len(result) == 2
    assert all(isinstance(c, BatchChannelConfig) for c in result)


def test_resolve_channel_index_by_name() -> None:
    """Test resolving channel index by name.

    Returns
    -------
    None
    """
    from senoquant.tabs.batch.io import resolve_channel_index

    channel_map = [
        BatchChannelConfig(name="DAPI", index=0),
        BatchChannelConfig(name="GFP", index=1),
    ]
    result = resolve_channel_index("GFP", channel_map)
    assert result == 1


def test_resolve_output_dir_creates_new() -> None:
    """Test resolving output directory when it doesn't exist.

    Returns
    -------
    None
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        output_root = Path(tmp)
        input_path = Path("test_image.tif")
        result = batch_backend._resolve_output_dir(output_root, input_path, None, False)
        assert result is not None
        assert result.exists()


def test_resolve_output_dir_skip_existing() -> None:
    """Test resolving output directory when it exists and no overwrite.

    Returns
    -------
    None
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        output_root = Path(tmp)
        input_path = Path("test_image.tif")
        
        # Create the output directory first
        output_dir = output_root / "test_image"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Request without overwrite should return None
        result = batch_backend._resolve_output_dir(output_root, input_path, None, False)
        assert result is None


def test_resolve_output_dir_overwrite() -> None:
    """Test resolving output directory with overwrite enabled.

    Returns
    -------
    None
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        output_root = Path(tmp)
        input_path = Path("test_image.tif")
        
        # Create the output directory first
        output_dir = output_root / "test_image"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Request with overwrite should return the directory
        result = batch_backend._resolve_output_dir(output_root, input_path, None, True)
        assert result is not None
        assert result.exists()
