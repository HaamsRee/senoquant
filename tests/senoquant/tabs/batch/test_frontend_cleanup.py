"""Tests for Batch frontend cleanup and row lifecycle behavior."""

from __future__ import annotations

from tests.conftest import DummyLayer, DummyViewer
from senoquant.tabs.batch.config import BatchChannelConfig, BatchJobConfig
import senoquant.tabs.batch.frontend as batch_frontend
from senoquant.tabs.batch.frontend import BatchTab


class _WidgetSpy:
    def __init__(self) -> None:
        self.parent_cleared = False
        self.delete_later_called = False

    def setParent(self, parent) -> None:
        self.parent_cleared = parent is None

    def deleteLater(self) -> None:
        self.delete_later_called = True


class _LayoutSpy:
    def __init__(self) -> None:
        self.removed: list[object] = []

    def removeWidget(self, widget) -> None:
        self.removed.append(widget)


class _Signal:
    def __init__(self) -> None:
        self._callbacks: list[object] = []

    def connect(self, callback) -> None:
        self._callbacks.append(callback)

    def emit(self, *args, **kwargs) -> None:
        for callback in list(self._callbacks):
            try:
                callback(*args, **kwargs)
            except TypeError:
                callback()


class _ThreadSpy:
    instances: list["_ThreadSpy"] = []

    def __init__(self, *_args, **_kwargs) -> None:
        self.started = _Signal()
        self.finished = _Signal()
        self.quit_called = False
        self.wait_called = False
        self.delete_later_called = False
        self.__class__.instances.append(self)

    def start(self) -> None:
        self.started.emit()

    def quit(self) -> None:
        self.quit_called = True
        self.finished.emit()

    def wait(self) -> None:
        self.wait_called = True

    def deleteLater(self) -> None:
        self.delete_later_called = True


class _WorkerSpy:
    def __init__(self, result: object) -> None:
        self._result = result
        self.progress = _Signal()
        self.finished = _Signal()
        self.failed = _Signal()
        self.delete_later_called = False
        self.thread = None

    def moveToThread(self, thread) -> None:
        self.thread = thread

    def run(self) -> None:
        self.finished.emit(self._result)

    def deleteLater(self) -> None:
        self.delete_later_called = True


def test_batch_channel_rows_auto_add_after_last_delete() -> None:
    """Deleting the last channel row should recreate a default channel row."""
    viewer = DummyViewer([DummyLayer(None, "img")])
    tab = BatchTab(napari_viewer=viewer)

    assert len(tab._channel_rows) == 1
    tab._remove_channel_row(tab._channel_rows[0])

    assert len(tab._channel_rows) == 1
    assert [config.name for config in tab._channel_configs] == ["0"]
    assert [config.index for config in tab._channel_configs] == [0]


def test_batch_apply_empty_job_keeps_channel_row() -> None:
    """Applying an empty job config should still leave one channel row visible."""
    viewer = DummyViewer([DummyLayer(None, "img")])
    tab = BatchTab(napari_viewer=viewer)
    tab._quant_tab.load_feature_configs = lambda _features: None

    tab.apply_job_config(BatchJobConfig(channel_map=[]))

    assert len(tab._channel_rows) == 1
    assert [config.name for config in tab._channel_configs] == ["0"]


def test_batch_clear_channel_rows_uses_delete_later_cleanup() -> None:
    """Clearing channel rows should remove, detach, and delete dynamic widgets."""
    tab = BatchTab.__new__(BatchTab)
    layout = _LayoutSpy()
    first = _WidgetSpy()
    second = _WidgetSpy()
    tab._channels_layout = layout
    tab._channel_rows = [{"widget": first}, {"widget": second}]
    tab._channel_configs = [BatchChannelConfig(name="Ch0", index=0)]

    tab._clear_channel_rows()

    assert layout.removed == [first, second]
    assert first.parent_cleared is True
    assert second.parent_cleared is True
    assert first.delete_later_called is True
    assert second.delete_later_called is True
    assert tab._channel_rows == []
    assert tab._channel_configs == []


def test_batch_clear_spot_channel_rows_uses_delete_later_cleanup() -> None:
    """Clearing spot-channel rows should remove, detach, and delete widgets."""
    tab = BatchTab.__new__(BatchTab)
    layout = _LayoutSpy()
    first = _WidgetSpy()
    second = _WidgetSpy()
    tab._spot_channels_layout = layout
    tab._spot_channel_rows = [{"widget": first}, {"widget": second}]

    tab._clear_spot_channel_rows()

    assert layout.removed == [first, second]
    assert first.parent_cleared is True
    assert second.parent_cleared is True
    assert first.delete_later_called is True
    assert second.delete_later_called is True
    assert tab._spot_channel_rows == []


def test_batch_background_run_cleans_up_thread_and_worker(monkeypatch) -> None:
    """Background run should delete thread/worker via thread-finished cleanup."""
    viewer = DummyViewer([DummyLayer(None, "img")])
    tab = BatchTab(napari_viewer=viewer)
    worker = _WorkerSpy(result={"ok": True})
    results: list[object] = []

    _ThreadSpy.instances.clear()
    monkeypatch.setattr(batch_frontend, "QThread", _ThreadSpy)

    tab._start_background_run(
        run_button=tab._run_button,
        run_text="Run batch",
        worker=worker,
        on_success=lambda result: results.append(result),
    )

    assert results == [{"ok": True}]
    assert len(_ThreadSpy.instances) == 1
    thread = _ThreadSpy.instances[0]
    assert thread.quit_called is True
    assert thread.wait_called is True
    assert thread.delete_later_called is True
    assert worker.delete_later_called is True
    assert tab._active_workers == []
