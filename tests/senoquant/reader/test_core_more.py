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
