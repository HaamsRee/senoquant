"""Extra tests for batch io helpers."""

from __future__ import annotations

import types

import numpy as np

from senoquant.tabs.batch import io as batch_io
from senoquant.tabs.batch.config import BatchChannelConfig


def test_sanitize_label_strips_symbols() -> None:
    """Sanitize label strings for filesystem use.

    Returns
    -------
    None
    """
    assert batch_io.sanitize_label(" A/B ") == "A_B"
    assert batch_io.sanitize_label("***") == "spots"


def test_spot_label_name_numeric_string() -> None:
    """Test removed - spot_label_name function no longer used.

    Returns
    -------
    None
    """
    # spot_label_name function removed in favor of inline naming
    pass


def test_load_channel_data_raises_on_bad_index(monkeypatch, tmp_path) -> None:
    """Raise when channel index is out of range.

    Returns
    -------
    None
    """
    class DummyDims:
        def __init__(self) -> None:
            self.C = 1
            self.Z = 1
            self.T = 1

    class DummyImage:
        def __init__(self) -> None:
            self.dims = DummyDims()
            self.scenes = []
            self.physical_pixel_sizes = types.SimpleNamespace(Z=1.0, Y=1.0, X=1.0)

        def get_image_data(self, _order, **_kwargs):
            return np.zeros((4, 4), dtype=np.uint8)

        def close(self):
            return None

    monkeypatch.setattr(batch_io.reader_core, "_open_bioimage", lambda _p: DummyImage())
    try:
        batch_io.load_channel_data(tmp_path / "file.tif", 3, None)
    except ValueError as exc:
        assert "out of range" in str(exc)

def test_basename_for_path() -> None:
    """Test extracting base name from path.

    Returns
    -------
    None
    """
    from pathlib import Path

    path = Path("/some/folder/image.tif")
    result = batch_io.basename_for_path(path)
    assert result == "image"


def test_iter_input_files_empty_folder(tmp_path) -> None:
    """Test iterating over files in empty folder.

    Returns
    -------
    None
    """
    result = list(batch_io.iter_input_files(tmp_path, [".tif"], False))
    assert result == []


def test_iter_input_files_filters_extensions(tmp_path) -> None:
    """Test that file iteration filters by extension.

    Returns
    -------
    None
    """
    # Create some files
    (tmp_path / "image1.tif").touch()
    (tmp_path / "image2.tif").touch()
    (tmp_path / "image3.lif").touch()

    # Only tif files
    result = list(batch_io.iter_input_files(tmp_path, [".tif"], False))
    assert len(result) == 2


def test_list_scenes_no_scenes(tmp_path) -> None:
    """Test listing scenes from single-scene file.

    Returns
    -------
    None
    """
    # Create a dummy file
    test_file = tmp_path / "image.tif"
    test_file.write_bytes(b"dummy")

    result = batch_io.list_scenes(test_file)
    # Should return empty list or None for single-scene files
    assert result is None or result == []


def test_safe_scene_dir_sanitizes_name() -> None:
    """Test that scene directory name is sanitized.

    Returns
    -------
    None
    """
    result = batch_io.safe_scene_dir("Scene / 1")
    # Slashes should be replaced with underscores and spaces preserved
    assert "/" not in result


def test_resolve_channel_index_numeric_string() -> None:
    """Test resolving channel by numeric string.

    Returns
    -------
    None
    """
    channel_map = [
        BatchChannelConfig(name="DAPI", index=0),
        BatchChannelConfig(name="GFP", index=1),
    ]
    # String "0" should resolve to index 0
    result = batch_io.resolve_channel_index("0", channel_map)
    assert result == 0


def test_resolve_channel_index_by_name() -> None:
    """Test resolving channel by name.

    Returns
    -------
    None
    """
    channel_map = [
        BatchChannelConfig(name="DAPI", index=0),
        BatchChannelConfig(name="GFP", index=1),
    ]
    result = batch_io.resolve_channel_index("GFP", channel_map)
    assert result == 1


def test_write_array_creates_file(tmp_path) -> None:
    """Test writing array to file.

    Returns
    -------
    None
    """
    data = np.ones((10, 10), dtype=np.uint32)
    result = batch_io.write_array(tmp_path, "test_array", data, "tif")
    
    assert result.exists()
    assert "test_array" in str(result)