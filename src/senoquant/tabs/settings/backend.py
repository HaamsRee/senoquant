"""Backend logic for the Settings tab."""

from qtpy.QtCore import QObject, Signal


class SettingsBackend(QObject):
    preload_models_changed = Signal(bool)

    def __init__(self) -> None:
        """Initialize settings storage with defaults."""
        super().__init__()
        self._preferences = {"preload_models": True}

    def preload_models_enabled(self) -> bool:
        """Return whether model preload is enabled."""
        return bool(self._preferences.get("preload_models", True))

    def set_preload_models(self, enabled: bool) -> None:
        """Update the preload setting and emit changes.

        Parameters
        ----------
        enabled : bool
            Whether to preload models on startup.
        """
        if self.preload_models_enabled() == enabled:
            return
        self._preferences["preload_models"] = enabled
        self.preload_models_changed.emit(enabled)
