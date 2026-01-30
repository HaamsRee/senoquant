"""Additional tests for reader core helpers."""

from __future__ import annotations

import types

import pytest

from senoquant.reader import core as reader_core


def test_get_reader_handles_missing_bioio(tmp_path, monkeypatch) -> None:
    """Return None when bioio is unavailable.

    Returns
    -------
    None
    """
    path = tmp_path / "image.tif"
    path.write_text("data")
    monkeypatch.setitem(__import__("sys").modules, "bioio", None)
    assert reader_core.get_reader(str(path)) is None


def test_get_reader_handles_plugin_errors(tmp_path, monkeypatch) -> None:
    """Return None when determine_plugin errors.

    Returns
    -------
    None
    """
    path = tmp_path / "image.tif"
    path.write_text("data")

    class DummyBioImage:
        @staticmethod
        def determine_plugin(_path):
            raise ValueError("bad")

    monkeypatch.setitem(
        __import__("sys").modules,
        "bioio",
        types.SimpleNamespace(BioImage=DummyBioImage),
    )
    assert reader_core.get_reader(str(path)) is None


def test_try_bioimage_readers_falls_back(monkeypatch) -> None:
    """Return None when no reader modules can be imported.

    Returns
    -------
    None
    """
    bioio = types.SimpleNamespace(BioImage=lambda *args, **kwargs: None)
    result = reader_core._try_bioimage_readers(bioio, "/tmp/file.tif", ("missing",))
    assert result is None


def test_should_force_tifffile_with_entrypoint() -> None:
    """Detect tiff_glob in entrypoint metadata.

    Returns
    -------
    None
    """
    entrypoint = types.SimpleNamespace(name="bioio_tiff_glob")
    plugin = types.SimpleNamespace(entrypoint=entrypoint)
    assert reader_core._should_force_tifffile(plugin, "image.tif") is True


def test_colormap_cycle_returns_iterator() -> None:
    """Test that colormap_cycle returns a cycling iterator.

    Returns
    -------
    None
    """
    cycle = reader_core._colormap_cycle()
    # Should be able to call next multiple times
    first = next(cycle)
    second = next(cycle)
    assert first is not None
    assert second is not None


def test_colormap_cycle_cycles_through_colors() -> None:
    """Test that colormap cycle repeats after full list.

    Returns
    -------
    None
    """
    cycle = reader_core._colormap_cycle()
    colors = [next(cycle) for _ in range(10)]
    # Should have some repeats since we go through more than unique count
    assert len(set(colors)) < len(colors)


def test_physical_pixel_sizes_returns_dict() -> None:
    """Test physical_pixel_sizes returns dict with required keys.

    Returns
    -------
    None
    """
    mock_image = types.SimpleNamespace(
        physical_pixel_sizes=types.SimpleNamespace(Z=1.0, Y=0.5, X=0.5)
    )
    result = reader_core._physical_pixel_sizes(mock_image)
    assert "Z" in result
    assert "Y" in result
    assert "X" in result
    assert result["Z"] == 1.0
    assert result["Y"] == 0.5
    assert result["X"] == 0.5


def test_physical_pixel_sizes_handles_exception() -> None:
    """Test physical_pixel_sizes returns None values on error.

    Returns
    -------
    None
    """
    mock_image = types.SimpleNamespace()
    result = reader_core._physical_pixel_sizes(mock_image)
    assert result["Z"] is None
    assert result["Y"] is None
    assert result["X"] is None


def test_axes_present_with_string_dims() -> None:
    """Test axes_present with string dims.

    Returns
    -------
    None
    """
    mock_image = types.SimpleNamespace(dims="CZYX")
    result = reader_core._axes_present(mock_image)
    assert "C" in result
    assert "Z" in result
    assert "Y" in result
    assert "X" in result


def test_axes_present_with_no_dims() -> None:
    """Test axes_present returns empty set when dims missing.

    Returns
    -------
    None
    """
    mock_image = types.SimpleNamespace()
    result = reader_core._axes_present(mock_image)
    assert result == set()


def test_axes_present_extracts_from_order() -> None:
    """Test axes_present extracts from dims.order.

    Returns
    -------
    None
    """
    mock_dims = types.SimpleNamespace(order="ZYX")
    mock_image = types.SimpleNamespace(dims=mock_dims)
    result = reader_core._axes_present(mock_image)
    assert "Z" in result
    assert "Y" in result
    assert "X" in result


def test_should_force_tifffile_no_asterisk() -> None:
    """Test _should_force_tifffile returns False for glob patterns.

    Returns
    -------
    None
    """
    result = reader_core._should_force_tifffile(None, "/path/*.tif")
    assert result is False


def test_should_force_tifffile_non_tiff_extension() -> None:
    """Test _should_force_tifffile returns False for non-TIFF.

    Returns
    -------
    None
    """
    result = reader_core._should_force_tifffile(None, "image.png")
    assert result is False


def test_get_reader_with_list_input(tmp_path) -> None:
    """Test get_reader handles list of paths.

    Returns
    -------
    None
    """
    # With empty list
    result = reader_core.get_reader([])
    assert result is None
