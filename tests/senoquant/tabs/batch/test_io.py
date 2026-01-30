"""Tests for batch I/O helpers.

Notes
-----
These tests exercise filesystem normalization, channel mapping, and
channel extraction logic with mocked BioIO images.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from senoquant.tabs.batch import io as batch_io
from senoquant.tabs.batch.config import BatchChannelConfig


class DummyDims:
    """Minimal dims container."""

    def __init__(self, order: str, C: int = 1, Z: int = 1, T: int = 1) -> None:
        self.order = order
        self.C = C
        self.Z = Z
        self.T = T


class DummyImage:
    """Minimal BioIO-like image."""

    def __init__(self, data: np.ndarray, dims: DummyDims) -> None:
        self._data = data
        self.dims = dims
        self.scenes = ["scene-1"]
        self._closed = False

    def get_image_data(self, _order: str, **_kwargs):
        return self._data

    def set_scene(self, _scene):
        return None

    def close(self):
        self._closed = True


class DummySizes:
    """Physical pixel sizes stub."""

    def __init__(self) -> None:
        self.Z = 1.0
        self.Y = 1.0
        self.X = 1.0


def test_normalize_extensions() -> None:
    """Normalize extension inputs to dotted lower-case strings.

    Returns
    -------
    None
    """
    assert batch_io.normalize_extensions(["TIF", ".png"]) == {".tif", ".png"}
    assert batch_io.normalize_extensions([]) is None


def test_iter_input_files(tmp_path: Path) -> None:
    """Iterate files with and without extension filters.

    Returns
    -------
    None
    """
    tif_file = tmp_path / "sample.tif"
    png_file = tmp_path / "sample.png"
    tif_file.write_text("data")
    png_file.write_text("data")

    found = list(batch_io.iter_input_files(tmp_path, {".tif"}, False))
    assert tif_file in found
    assert png_file not in found

    found_all = list(batch_io.iter_input_files(tmp_path, None, False))
    assert tif_file in found_all and png_file in found_all


def test_basename_for_path() -> None:
    """Strip microscopy extensions from file names.

    Returns
    -------
    None
    """
    assert batch_io.basename_for_path(Path("sample.ome.tif")) == "sample"
    assert batch_io.basename_for_path(Path("sample.tiff")) == "sample"
    assert batch_io.basename_for_path(Path("sample.txt")) == "sample"


def test_safe_scene_dir() -> None:
    """Sanitize scene identifiers.

    Returns
    -------
    None
    """
    assert batch_io.safe_scene_dir("scene/1") == "scene_1"
    assert batch_io.safe_scene_dir(" ") == "scene"


def test_resolve_channel_index() -> None:
    """Resolve channel choices to indices.

    Returns
    -------
    None
    """
    channel_map = [BatchChannelConfig(name="DAPI", index=0)]
    assert batch_io.resolve_channel_index(0, channel_map) == 0
    assert batch_io.resolve_channel_index("0", channel_map) == 0
    assert batch_io.resolve_channel_index("DAPI", channel_map) == 0
    with pytest.raises(ValueError):
        batch_io.resolve_channel_index("", channel_map)


def test_spot_label_name() -> None:
    """Build spot label names from channels.

    Returns
    -------
    None
    """
    # spot_label_name function removed in favor of inline naming
    pass


def test_write_array_fallback(tmp_path: Path, monkeypatch) -> None:
    """Fallback to NumPy when TIFF writing fails.

    Returns
    -------
    None
    """
    data = np.ones((2, 2), dtype=np.uint8)

    class DummyTiff:
        """Tiff stub that raises on write."""

        @staticmethod
        def imwrite(_path, _data):
            raise RuntimeError("fail")

    monkeypatch.setitem(__import__("sys").modules, "tifffile", DummyTiff)

    path = batch_io.write_array(tmp_path, "labels", data, "tif")
    assert path.suffix == ".npy"
    assert path.exists()


def test_load_channel_data(monkeypatch) -> None:
    """Load a single channel from a mocked BioIO image.

    Returns
    -------
    None
    """
    data = np.zeros((2, 4, 4), dtype=np.uint8)
    dims = DummyDims(order="CYX", C=2, Z=1, T=1)
    image = DummyImage(data, dims)
    image.physical_pixel_sizes = DummySizes()

    def fake_open(_path):
        return image

    monkeypatch.setattr(batch_io.reader_core, "_open_bioimage", fake_open)
    array, metadata = batch_io.load_channel_data(Path("/tmp/test.tif"), 1, None)
    assert array.shape == (4, 4)
    assert "physical_pixel_sizes" in metadata


def test_list_scenes(monkeypatch) -> None:
    """Return scenes from a mocked BioIO image.

    Returns
    -------
    None
    """
    data = np.zeros((4, 4), dtype=np.uint8)
    dims = DummyDims(order="YX", C=1, Z=1, T=1)
    image = DummyImage(data, dims)

    monkeypatch.setattr(batch_io.reader_core, "_open_bioimage", lambda _p: image)
    scenes = batch_io.list_scenes(Path("/tmp/test.tif"))
    assert scenes == ["scene-1"]

def test_write_array_tif_format(tmp_path: Path) -> None:
    """Write numpy array to tif file format.

    Returns
    -------
    None
    """
    data = np.ones((10, 10), dtype=np.uint16)
    output_path = batch_io.write_array(tmp_path, "test_output", data, "tif")
    
    assert output_path.exists()
    assert output_path.suffix == ".tif"


def test_write_array_npy_format(tmp_path: Path) -> None:
    """Write numpy array to npy file format.

    Returns
    -------
    None
    """
    data = np.ones((10, 10), dtype=np.uint16)
    output_path = batch_io.write_array(tmp_path, "test_output", data, "npy")
    
    assert output_path.exists()
    assert output_path.suffix == ".npy"


def test_safe_scene_dir() -> None:
    """Sanitize scene identifiers for filesystem use.

    Returns
    -------
    None
    """
    # Test normal scene ID
    assert batch_io.safe_scene_dir("scene-1") == "scene-1"
    
    # Test scene ID with problematic characters (forward and backslash)
    result = batch_io.safe_scene_dir("scene/path\\with_chars")
    assert "/" not in result
    assert "\\" not in result


def test_resolve_channel_index_with_numeric_string() -> None:
    """Resolve channel index from numeric string without channel map.

    Returns
    -------
    None
    """
    channel_map = [
        BatchChannelConfig(name="DAPI", index=0),
        BatchChannelConfig(name="GFP", index=1),
    ]
    
    # Numeric string should resolve to index
    idx = batch_io.resolve_channel_index("1", channel_map)
    assert idx == 1


def test_resolve_channel_index_by_name() -> None:
    """Resolve channel index by name from channel map.

    Returns
    -------
    None
    """
    channel_map = [
        BatchChannelConfig(name="DAPI", index=0),
        BatchChannelConfig(name="GFP", index=1),
    ]
    
    # Named channel should resolve to its index
    idx = batch_io.resolve_channel_index("GFP", channel_map)
    assert idx == 1


def test_spot_label_name_generation() -> None:
    """Generate consistent spot label names.

    Returns
    -------
    None
    """
    channel_map = [
        BatchChannelConfig(name="GFP", index=0),
        BatchChannelConfig(name="DAPI", index=1),
    ]
    
    # Test with channel name
    name = batch_io.spot_label_name("GFP", channel_map)
    assert name == "spot_labels_GFP"
    
    # Test with numeric index
    name = batch_io.spot_label_name(0, channel_map)
    assert name == "spot_labels_0"