"""Shared frontend widgets and runtime helpers for segmentation UI."""

from __future__ import annotations

from qtpy.QtCore import QObject, Signal
from qtpy.QtWidgets import QComboBox

try:
    from napari.layers import Image, Labels
    from napari.utils.notifications import (
        Notification,
        NotificationSeverity,
        show_console_notification,
    )
except Exception:  # pragma: no cover - optional import for runtime
    Image = None
    Labels = None
    show_console_notification = None
    Notification = None
    NotificationSeverity = None


class RefreshingComboBox(QComboBox):
    """Combo box that refreshes its items when opened."""

    def __init__(self, refresh_callback=None, parent=None) -> None:
        """Create a combo box that refreshes on popup.

        Parameters
        ----------
        refresh_callback : callable or None
            Function invoked before showing the popup.
        parent : QWidget or None
            Optional parent widget.
        """
        super().__init__(parent)
        self._refresh_callback = refresh_callback

    def showPopup(self) -> None:
        """Refresh items before showing the popup."""
        if self._refresh_callback is not None:
            self._refresh_callback()
        super().showPopup()


class _RunWorker(QObject):
    """Worker that executes a callable in a background thread."""

    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, run_callable) -> None:
        """Initialize the worker with a callable.

        Parameters
        ----------
        run_callable : callable
            Callable to execute on the worker thread.
        """
        super().__init__()
        self._run_callable = run_callable

    def run(self) -> None:
        """Execute the callable and emit results."""
        try:
            result = self._run_callable()
        except Exception as exc:  # pragma: no cover - runtime error path
            self.error.emit(str(exc))
            return
        self.finished.emit(result)

