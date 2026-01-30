"""Tests for settings backend."""

from __future__ import annotations

from senoquant.tabs.settings.backend import SettingsBackend


def test_settings_backend_initialization() -> None:
    """Test SettingsBackend initializes with defaults.

    Returns
    -------
    None
    """
    backend = SettingsBackend()
    assert backend.preload_models_enabled() is True


def test_settings_backend_set_preload_models() -> None:
    """Test setting preload_models preference.

    Returns
    -------
    None
    """
    backend = SettingsBackend()
    signal_calls: list[bool] = []

    def on_changed(enabled: bool) -> None:
        signal_calls.append(enabled)

    backend.preload_models_changed.connect(on_changed)

    # Change from True to False
    backend.set_preload_models(False)
    assert backend.preload_models_enabled() is False
    assert len(signal_calls) == 1
    assert signal_calls[0] is False

    # Try to set to same value (should not emit signal)
    backend.set_preload_models(False)
    assert len(signal_calls) == 1  # No new signal emitted

    # Change from False to True
    backend.set_preload_models(True)
    assert backend.preload_models_enabled() is True
    assert len(signal_calls) == 2
    assert signal_calls[1] is True
