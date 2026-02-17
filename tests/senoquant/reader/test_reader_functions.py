"""Tests for reader core functions."""

import io
import logging
from pathlib import Path
import sys
import types

import pytest

from senoquant.reader import core


def test_colormap_cycle_returns_iterator():
    """Test that _colormap_cycle returns an iterator."""
    cycle = core._colormap_cycle()
    assert hasattr(cycle, "__iter__")
    assert hasattr(cycle, "__next__")


def test_colormap_cycle_cycles_through_colors():
    """Test that _colormap_cycle cycles through the expected colors."""
    cycle = core._colormap_cycle()
    expected = ["blue", "green", "red", "yellow", "cyan", "bop blue", "bop orange", "bop purple"]
    for color in expected:
        assert next(cycle) == color
    # After 8, it should cycle back to blue
    assert next(cycle) == "blue"


def test_all_channels_same_color_same():
    """Test _all_channels_same_color returns True when all colors are the same."""
    channel_colors = [
        {"colors": [[0, 0, 0, 1], [1, 1, 1, 1]], "name": "channel_0_white"},
        {"colors": [[0, 0, 0, 1], [1, 1, 1, 1]], "name": "channel_1_white"},
    ]
    assert core._all_channels_same_color(channel_colors) is True


def test_all_channels_same_color_different():
    """Test _all_channels_same_color returns False when colors differ."""
    channel_colors = [
        {"colors": [[0, 0, 0, 1], [1, 0, 0, 1]], "name": "channel_0_red"},
        {"colors": [[0, 0, 0, 1], [0, 1, 0, 1]], "name": "channel_1_green"},
    ]
    assert core._all_channels_same_color(channel_colors) is False


def test_all_channels_same_color_empty():
    """Test _all_channels_same_color returns False for empty list."""
    assert core._all_channels_same_color([]) is False


def test_all_channels_same_color_all_none():
    """Test _all_channels_same_color returns False when all are None."""
    assert core._all_channels_same_color([None, None]) is False


def test_all_channels_same_color_mixed():
    """Test _all_channels_same_color with mix of None and valid colors."""
    # With one None and one valid, there's only one valid color to compare
    # so it returns True (vacuously all same)
    channel_colors = [
        None,
        {"colors": [[0, 0, 0, 1], [1, 0, 0, 1]], "name": "channel_0_red"},
    ]
    assert core._all_channels_same_color(channel_colors) is True


def test_get_channel_colors_from_ome_no_ome():
    """Test _get_channel_colors_from_ome returns empty when no OME metadata."""
    # Create a mock image without OME metadata
    class MockImage:
        def __init__(self):
            self._ome_metadata = None

        @property
        def ome_metadata(self):
            return self._ome_metadata

    image = MockImage()
    result = core._get_channel_colors_from_ome(image)
    assert result == []


def test_get_channel_colors_from_ome_no_images():
    """Test _get_channel_colors_from_ome returns empty when no images in OME."""
    class MockOME:
        images = None

    class MockImage:
        def __init__(self):
            self._ome_metadata = MockOME()

        @property
        def ome_metadata(self):
            return self._ome_metadata

    image = MockImage()
    result = core._get_channel_colors_from_ome(image)
    assert result == []


def test_get_channel_colors_from_ome_no_pixels():
    """Test _get_channel_colors_from_ome returns empty when no pixels."""
    class MockPixelsImage:
        images = []

    class MockImage:
        def __init__(self):
            self._ome_metadata = MockPixelsImage()

        @property
        def ome_metadata(self):
            return self._ome_metadata

    image = MockImage()
    result = core._get_channel_colors_from_ome(image)
    assert result == []


def test_get_reader_logs_plugin_detection_failures(monkeypatch, tmp_path, caplog) -> None:
    """Log plugin determination failures before returning None."""

    class _BrokenBioImage:
        @staticmethod
        def determine_plugin(_path: str):
            raise RuntimeError("plugin probe failed")

    fake_bioio = types.SimpleNamespace(BioImage=_BrokenBioImage)
    monkeypatch.setitem(sys.modules, "bioio", fake_bioio)

    sample_path = tmp_path / "sample.tif"
    sample_path.write_bytes(b"test")

    caplog.set_level(logging.WARNING, logger=core.__name__)
    assert core.get_reader(str(sample_path)) is None
    assert "failed to determine a BioIO plugin" in caplog.text


def test_get_reader_uses_resolved_path_for_plugin_probe(monkeypatch, tmp_path) -> None:
    """Probe plugin support using the resolved local path."""

    resolved_path = tmp_path / "staged.czi"
    resolved_path.write_bytes(b"data")
    probed_path: dict[str, str] = {}

    class _BioImage:
        @staticmethod
        def determine_plugin(path: str):
            probed_path["value"] = path
            return object()

    monkeypatch.setattr(core, "_resolve_reader_path", lambda _path: str(resolved_path))
    monkeypatch.setitem(sys.modules, "bioio", types.SimpleNamespace(BioImage=_BioImage))

    assert core.get_reader("smb://server/share/image.czi") is core._read_senoquant
    assert probed_path["value"] == str(resolved_path)


def test_stage_network_path_downloads_once_and_reuses_cache(monkeypatch, tmp_path) -> None:
    """Download a network image to temp once and reuse cached local path."""
    monkeypatch.setattr(core, "_NETWORK_STAGE_ROOT", tmp_path)
    monkeypatch.setattr(core, "_STAGED_NETWORK_PATHS", {})

    calls: list[tuple[str, str]] = []

    class _OpenContext:
        def __init__(self, data: bytes) -> None:
            self._buffer = io.BytesIO(data)

        def __enter__(self):
            return self._buffer

        def __exit__(self, *_args) -> None:
            self._buffer.close()

    def _fake_open(path: str, mode: str = "rb"):
        calls.append((path, mode))
        return _OpenContext(b"network-bytes")

    monkeypatch.setitem(sys.modules, "fsspec", types.SimpleNamespace(open=_fake_open))

    original = "smb://server/share/image.czi"
    staged_first = core._stage_network_path(original)
    staged_second = core._stage_network_path(original)
    assert staged_first == staged_second
    assert Path(staged_first).read_bytes() == b"network-bytes"
    assert calls == [(original, "rb")]


def test_path_display_name_handles_unc_url_and_local_paths() -> None:
    """Return stable display names for path variants."""
    assert core._path_display_name(r"\\server\share\folder\image.czi") == "image.czi"
    assert core._path_display_name("smb://server/share/folder/image.czi") == "image.czi"
    assert core._path_display_name("/tmp/local-image.czi") == "local-image.czi"


def test_network_download_source_converts_unc_and_rejects_invalid_unc() -> None:
    """Convert UNC to smb URL and reject malformed UNC inputs."""
    assert (
        core._network_download_source(r"\\server\share\folder\image.czi")
        == "smb://server/share/folder/image.czi"
    )
    with pytest.raises(ValueError, match="Unsupported UNC path format"):
        core._network_download_source(r"\\server")


def test_stage_network_path_cleans_partial_file_on_copy_failure(
    monkeypatch, tmp_path
) -> None:
    """Remove partial staged file when network copy fails."""
    monkeypatch.setattr(core, "_NETWORK_STAGE_ROOT", tmp_path)
    monkeypatch.setattr(core, "_STAGED_NETWORK_PATHS", {})

    class _BrokenReader:
        def read(self, *_args, **_kwargs):
            raise OSError("network read failed")

    class _BrokenContext:
        def __enter__(self):
            return _BrokenReader()

        def __exit__(self, *_args) -> None:
            return None

    monkeypatch.setitem(
        sys.modules,
        "fsspec",
        types.SimpleNamespace(open=lambda *_args, **_kwargs: _BrokenContext()),
    )

    with pytest.raises(OSError, match="network read failed"):
        core._stage_network_path("smb://server/share/image.czi")

    assert not list(tmp_path.glob("*.part"))
