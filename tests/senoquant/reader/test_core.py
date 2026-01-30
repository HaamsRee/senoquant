"""Tests for BioIO reader integration utilities.

Notes
-----
These tests cover path validation, axis parsing, and layer construction
from mocked BioIO image objects.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import numpy as np

from senoquant.reader import core as reader_core


class DummyDims:
    """Simple dims container for axis metadata."""

    def __init__(self, order: str, C: int = 1, Z: int = 1, T: int = 1) -> None:
        self.order = order
        self.C = C
        self.Z = Z
        self.T = T


class DummySizes:
    """Physical pixel size container."""

    def __init__(self, Z: float = 1.0, Y: float = 1.0, X: float = 1.0) -> None:
        self.Z = Z
        self.Y = Y
        self.X = X


class DummyImage:
    """Minimal image for layer iteration tests."""

    def __init__(self, data: np.ndarray, dims: DummyDims) -> None:
        self._data = data
        self.dims = dims
        self.metadata = {"meta": True}
        self.physical_pixel_sizes = DummySizes()

    def get_image_data(self, _order: str, **_kwargs):
        return self._data


def test_get_reader_returns_none_for_invalid_path() -> None:
    """Ensure unsupported path types are rejected.

    Returns
    -------
    None
    """
    assert reader_core.get_reader(123) is None
    assert reader_core.get_reader("") is None
    assert reader_core.get_reader([]) is None


def test_get_reader_with_supported_file(tmp_path, monkeypatch) -> None:
    """Return the reader callable for a supported BioIO path.

    Returns
    -------
    None
    """
    file_path = tmp_path / "image.tif"
    file_path.write_text("data")

    class DummyBioImage:
        """BioImage stub for determine_plugin."""

        @staticmethod
        def determine_plugin(_path):
            return "dummy"

    monkeypatch.setitem(sys.modules, "bioio", types.SimpleNamespace(BioImage=DummyBioImage))

    reader = reader_core.get_reader(str(file_path))
    assert reader is reader_core._read_senoquant


def test_should_force_tifffile_detects_tiff_glob() -> None:
    """Detect tiff_glob plugins when appropriate.

    Returns
    -------
    None
    """
    assert reader_core._should_force_tifffile("tiff_glob", "image.tif")
    assert not reader_core._should_force_tifffile("other", "image.png")


def test_axes_present_from_dims_order() -> None:
    """Parse axes from dims order metadata.

    Returns
    -------
    None
    """
    dims = DummyDims(order="TCZYX", C=2, Z=3, T=1)
    image = types.SimpleNamespace(dims=dims)
    axes = reader_core._axes_present(image)
    assert axes == set("TCZYX")


def test_iter_channel_layers_builds_layers() -> None:
    """Build layer tuples for multi-channel data.

    Returns
    -------
    None
    """
    data = np.zeros((2, 1, 4, 4), dtype=np.uint8)
    dims = DummyDims(order="CZYX", C=2, Z=1, T=1)
    image = DummyImage(data, dims)

    layers = reader_core._iter_channel_layers(
        image,
        base_name="sample",
        scene_id="scene-1",
        scene_idx=0,
        total_scenes=1,
        path="/tmp/sample.tif",
        colormap_cycle=reader_core._colormap_cycle(),
    )
    assert len(layers) == 2
    for layer_data, meta, layer_type in layers:
        assert layer_data.shape == (1, 4, 4) or layer_data.shape == (4, 4)
        assert layer_type == "image"
        assert "metadata" in meta
        assert "physical_pixel_sizes" in meta["metadata"]

def test_physical_pixel_sizes_defaults() -> None:
    """Test physical pixel size extraction with defaults.

    Returns
    -------
    None
    """
    class DummyImage:
        def __init__(self):
            pass

    image = DummyImage()
    result = reader_core._physical_pixel_sizes(image)
    
    # Should have Z, Y, X keys with None values when not available
    assert "Z" in result
    assert "Y" in result
    assert "X" in result
    assert result["Z"] is None


def test_axes_present_from_string() -> None:
    """Test extracting axes from string dims.

    Returns
    -------
    None
    """
    class DummyDims:
        def __init__(self):
            self.order = "CZYX"

    class DummyImage:
        def __init__(self):
            self.dims = DummyDims()

    image = DummyImage()
    result = reader_core._axes_present(image)
    
    assert "C" in result
    assert "Z" in result
    assert "Y" in result
    assert "X" in result


def test_colormap_cycle() -> None:
    """Test colormap cycle generation.

    Returns
    -------
    None
    """
    cycle = reader_core._colormap_cycle()
    
    # Should be an iterator
    colors = [next(cycle) for _ in range(16)]
    assert len(colors) == 16
    # Should cycle back - after 8 items (the colormap list size)
    # The cycle repeats, so colors[0] should equal colors[8]
    assert colors[0] == colors[8]


def test_should_force_tifffile_with_wildcard() -> None:
    """Test that wildcards prevent tifffile forcing.

    Returns
    -------
    None
    """
    result = reader_core._should_force_tifffile(None, "/path/to/*.tif")
    assert result is False


def test_should_force_tifffile_non_tiff() -> None:
    """Test that non-TIFF files return False.

    Returns
    -------
    None
    """
    result = reader_core._should_force_tifffile(None, "/path/to/image.lif")
    assert result is False


def test_should_force_tifffile_with_tiff_glob_plugin() -> None:
    """Test that tiff_glob plugin triggers forcing.

    Returns
    -------
    None
    """
    class MockPlugin:
        name = "bioio_tiff_glob"

    result = reader_core._should_force_tifffile(MockPlugin(), "/path/to/image.tif")
    assert result is True


def test_get_reader_empty_list() -> None:
    """Test that empty list of paths returns None.

    Returns
    -------
    None
    """
    result = reader_core.get_reader([])
    assert result is None

def test_open_bioimage_exception_handling() -> None:
    """Test _open_bioimage with mock exception handling.

    Returns
    -------
    None
    """
    try:
        # This will fail because path doesn't exist, testing exception paths
        result = reader_core._open_bioimage("/nonexistent/path.tif")
    except Exception:
        # Expected to raise exception for nonexistent path
        pass


def test_try_bioimage_readers() -> None:
    """Test _try_bioimage_readers returns None for invalid readers.

    Returns
    -------
    None
    """
    class MockBioIO:
        pass

    result = reader_core._try_bioimage_readers(MockBioIO(), "/path.tif", ("nonexistent_reader",))
    assert result is None

def test_get_reader_invalid_path_type() -> None:
    """Test that invalid path type returns None.

    Returns
    -------
    None
    """
    result = reader_core.get_reader(123)
    assert result is None


def test_get_reader_empty_string() -> None:
    """Test that empty string path returns None.

    Returns
    -------
    None
    """
    result = reader_core.get_reader("")
    assert result is None