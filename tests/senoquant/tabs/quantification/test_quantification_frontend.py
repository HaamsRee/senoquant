"""Tests for quantification frontend behavior."""

from __future__ import annotations

import types

from qtpy.QtWidgets import QPushButton

from senoquant.tabs.quantification.frontend import QuantificationTab
import senoquant.tabs.quantification.frontend as frontend


class _TextInput:
    """Simple text input stub."""

    def __init__(self, value: str) -> None:
        self._value = value

    def text(self) -> str:
        return self._value


class _FormatCombo:
    """Simple combo stub."""

    def __init__(self, value: str) -> None:
        self._value = value

    def currentText(self) -> str:
        return self._value


def test_process_features_keeps_process_and_save_label() -> None:
    """Use the new run button label when restoring UI state."""
    tab = QuantificationTab.__new__(QuantificationTab)
    tab._backend = types.SimpleNamespace(
        process=lambda *_args, **_kwargs: None
    )
    tab._feature_configs = []
    tab._output_path_input = _TextInput("/tmp/out")
    tab._save_name_input = _TextInput("run")
    tab._format_combo = _FormatCombo("csv")
    tab._process_button = QPushButton()

    captured: dict[str, object] = {}

    def _capture_start_background_run(**kwargs) -> None:
        captured.update(kwargs)

    tab._start_background_run = _capture_start_background_run

    QuantificationTab._process_features(tab)

    assert captured["run_text"] == "Process and save"


def test_notify_flushes_console_output(monkeypatch) -> None:
    """Flush stdout after console notifications are emitted."""
    tab = QuantificationTab.__new__(QuantificationTab)

    notifications: list[object] = []
    flushed = {"value": False}

    class _Notification:
        def __init__(self, message: str, severity) -> None:
            self.message = message
            self.severity = severity

    monkeypatch.setattr(frontend, "show_console_notification", notifications.append)
    monkeypatch.setattr(frontend, "Notification", _Notification)
    monkeypatch.setattr(
        frontend,
        "NotificationSeverity",
        types.SimpleNamespace(WARNING="warning"),
    )
    monkeypatch.setattr(
        frontend,
        "sys",
        types.SimpleNamespace(
            stdout=types.SimpleNamespace(
                flush=lambda: flushed.__setitem__("value", True)
            )
        ),
    )

    QuantificationTab._notify(tab, "Quantification complete.")

    assert len(notifications) == 1
    assert notifications[0].message == "Quantification complete."
    assert flushed["value"] is True
