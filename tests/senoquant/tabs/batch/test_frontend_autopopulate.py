"""Tests for batch channel auto-populate behavior."""

from __future__ import annotations

from pathlib import Path
import types

from tests.conftest import DummyLayer, DummyViewer
import senoquant.tabs.batch.frontend as batch_frontend
from senoquant.tabs.batch.frontend import BatchTab


class _ImageStub:
    def __init__(self, c_size: int = 1) -> None:
        self.dims = types.SimpleNamespace(C=c_size)


def test_batch_auto_populate_button_enabled_only_for_valid_input_folder(
    tmp_path: Path,
) -> None:
    """Enable auto-populate only when a valid input folder path is present."""
    viewer = DummyViewer([DummyLayer(None, "img")])
    tab = BatchTab(napari_viewer=viewer)

    assert tab._auto_populate_channels_button.isEnabled() is False

    tab._input_path.setText(str(tmp_path / "missing"))
    assert tab._auto_populate_channels_button.isEnabled() is False

    input_dir = tmp_path / "input"
    input_dir.mkdir()
    tab._input_path.setText(str(input_dir))
    assert tab._auto_populate_channels_button.isEnabled() is True

    tab._input_path.setText("")
    assert tab._auto_populate_channels_button.isEnabled() is False


def test_batch_auto_populate_channels_uses_first_input_file_metadata(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Populate rows from first discovered file and resolved metadata names."""
    viewer = DummyViewer([DummyLayer(None, "img")])
    tab = BatchTab(napari_viewer=viewer)
    input_dir = tmp_path / "input"
    input_dir.mkdir()

    first = input_dir / "a.ome.tif"
    second = input_dir / "b.ome.tif"
    first.write_text("")
    second.write_text("")
    tab._input_path.setText(str(input_dir))

    selected_paths: list[str] = []
    data_image = _ImageStub(c_size=3)
    metadata_image = _ImageStub(c_size=3)

    def _iter_input_files(
        root: Path,
        extensions: set[str] | None,
        include_subfolders: bool,
    ) -> list[Path]:
        assert root == input_dir
        assert include_subfolders is False
        assert extensions is not None
        return [second, first]

    def _open_bioimage(path: str):
        selected_paths.append(path)
        return data_image

    def _open_metadata_bioimage(path: str, *, fallback_image):
        assert path == str(first)
        assert fallback_image is data_image
        return metadata_image

    monkeypatch.setattr(batch_frontend.batch_io, "iter_input_files", _iter_input_files)
    monkeypatch.setattr(
        batch_frontend.reader_core,
        "_open_bioimage",
        _open_bioimage,
    )
    monkeypatch.setattr(
        batch_frontend.reader_core,
        "_open_metadata_bioimage",
        _open_metadata_bioimage,
    )
    monkeypatch.setattr(batch_frontend.reader_core, "_axes_present", lambda _img: {"C"})
    monkeypatch.setattr(
        batch_frontend.reader_core,
        "_resolve_channel_names",
        lambda _meta, _data, _size: ["DAPI", "FITC", "TRITC"],
    )

    tab._auto_populate_channels()

    assert selected_paths == [str(first)]
    assert [(cfg.name, cfg.index) for cfg in tab._channel_configs] == [
        ("DAPI", 0),
        ("FITC", 1),
        ("TRITC", 2),
    ]
    assert len(tab._channel_rows) == 3
