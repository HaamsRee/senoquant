"""Tests for scene-selection behavior in the BioIO reader."""

from __future__ import annotations

import types

from senoquant.reader import core as reader_core


class _FakeSceneItem:
    """Minimal QListWidgetItem-like object for unit tests."""

    def __init__(self, index: int, checked: bool) -> None:
        self._index = index
        self._state = 2 if checked else 0

    def setCheckState(self, state: int) -> None:
        self._state = int(state)

    def checkState(self) -> int:
        return self._state

    def data(self, _role: int) -> int:
        return self._index


class _FakeSceneList:
    """Minimal QListWidget-like container for unit tests."""

    def __init__(self, items: list[_FakeSceneItem]) -> None:
        self._items = items

    def count(self) -> int:
        return len(self._items)

    def item(self, row: int):
        if 0 <= row < len(self._items):
            return self._items[row]
        return None


class _DummyImage:
    """Simple BioImage stand-in for scene iteration tests."""

    def __init__(self, scenes: list[str]) -> None:
        self.scenes = scenes
        self.scene_calls: list[str] = []
        self.closed = False

    def set_scene(self, scene_id: str) -> None:
        self.scene_calls.append(scene_id)

    def close(self) -> None:
        self.closed = True


def test_select_scene_indices_short_circuits() -> None:
    """Handle empty and single-scene inputs without prompting."""
    assert reader_core._select_scene_indices("file.tif", []) == []
    assert reader_core._select_scene_indices("file.tif", ["s0"]) == [0]


def test_select_scene_indices_cancel_returns_empty(monkeypatch) -> None:
    """Return no scenes when the selection dialog is cancelled."""
    monkeypatch.setattr(reader_core, "_prompt_scene_selection", lambda *_args: None)
    selected = reader_core._select_scene_indices("file.tif", ["s0", "s1"])
    assert selected == []


def test_prompt_scene_selection_falls_back_without_qt_dialog(monkeypatch) -> None:
    """Select all scenes when required Qt widgets are unavailable."""
    qtcore = types.ModuleType("qtpy.QtCore")
    qtcore.Qt = object()
    qtwidgets = types.ModuleType("qtpy.QtWidgets")
    monkeypatch.setitem(__import__("sys").modules, "qtpy.QtCore", qtcore)
    monkeypatch.setitem(__import__("sys").modules, "qtpy.QtWidgets", qtwidgets)

    scenes = ["s0", "s1", "s2"]
    assert reader_core._prompt_scene_selection("file.tif", scenes) == [0, 1, 2]


def test_set_scene_checks_updates_all_items() -> None:
    """Set check state for every scene in the list."""
    scene_list = _FakeSceneList(
        [_FakeSceneItem(index=0, checked=False), _FakeSceneItem(index=1, checked=False)]
    )
    reader_core._set_scene_checks(scene_list, 2)
    assert scene_list.item(0).checkState() == 2
    assert scene_list.item(1).checkState() == 2


def test_checked_scene_indices_returns_checked(monkeypatch) -> None:
    """Return only indices with checked state."""
    import qtpy.QtCore as qtcore

    monkeypatch.setattr(qtcore.Qt, "Checked", 2, raising=False)
    monkeypatch.setattr(qtcore.Qt, "UserRole", 32, raising=False)

    scene_list = _FakeSceneList(
        [
            _FakeSceneItem(index=0, checked=True),
            _FakeSceneItem(index=1, checked=False),
            _FakeSceneItem(index=2, checked=True),
        ]
    )
    selected = reader_core._checked_scene_indices(scene_list)
    assert selected == [0, 2]


def test_read_senoquant_reads_only_selected_scenes(monkeypatch) -> None:
    """Load layers only for selected scenes and close image handle."""
    image = _DummyImage(["s0", "s1", "s2"])
    monkeypatch.setattr(reader_core, "_open_bioimage", lambda _path: image)
    monkeypatch.setattr(reader_core, "_select_scene_indices", lambda *_args: [1])

    calls: list[dict] = []

    def _fake_iter_channel_layers(_image, **kwargs):
        calls.append(kwargs)
        return [(f"layer-{kwargs['scene_idx']}", {"name": "x"}, "image")]

    monkeypatch.setattr(reader_core, "_iter_channel_layers", _fake_iter_channel_layers)

    layers = reader_core._read_senoquant("C:/tmp/sample.tif")
    assert [layer[0] for layer in layers] == ["layer-1"]
    assert image.scene_calls == ["s1"]
    assert image.closed is True
    assert calls[0]["base_name"] == "sample.tif"
    assert calls[0]["total_scenes"] == 3


def test_read_senoquant_returns_empty_when_no_scene_selected(monkeypatch) -> None:
    """Return no layers when user selects no scenes and still close image."""
    image = _DummyImage(["s0", "s1"])
    monkeypatch.setattr(reader_core, "_open_bioimage", lambda _path: image)
    monkeypatch.setattr(reader_core, "_select_scene_indices", lambda *_args: [])

    def _unexpected(*_args, **_kwargs):
        raise AssertionError("_iter_channel_layers should not be called")

    monkeypatch.setattr(reader_core, "_iter_channel_layers", _unexpected)
    assert reader_core._read_senoquant("C:/tmp/sample.tif") == []
    assert image.closed is True
