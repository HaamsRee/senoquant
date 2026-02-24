"""Background-task and notification helpers for the SenNet Portal frontend."""

from __future__ import annotations

import sys

from qtpy.QtCore import QObject, QThread, Signal
from qtpy.QtWidgets import QPushButton

try:
    from napari.utils.notifications import (
        Notification,
        NotificationSeverity,
        show_console_notification,
    )
except Exception:  # pragma: no cover - optional import for runtime
    show_console_notification = None
    Notification = None
    NotificationSeverity = None


class _RunWorker(QObject):
    """Worker that executes a callable in a background thread.

    Parameters
    ----------
    run_callable : callable
        Callable to execute inside the worker thread.
    """

    finished = Signal(object)
    error = Signal(str)

    def __init__(self, run_callable) -> None:
        """Store callable used during worker execution.

        Parameters
        ----------
        run_callable : callable
            Callable returning result payload or raising an exception.

        Returns
        -------
        None
            Callable is stored for later execution.
        """
        super().__init__()
        self._run_callable = run_callable

    def run(self) -> None:
        """Execute worker callable and emit finished or error signal.

        Returns
        -------
        None
            Emits ``finished`` on success or ``error`` on failure.
        """
        try:
            result = self._run_callable()
        except Exception as exc:
            self.error.emit(str(exc))
            return
        self.finished.emit(result)


class SenNetPortalBackgroundMixin:
    """Mixin containing reusable worker-thread orchestration helpers."""

    def _run_background(
        self,
        *,
        button: QPushButton,
        busy_text: str,
        run_callable,
        on_success,
        on_error_prefix: str,
    ) -> None:
        """Run an arbitrary callable on a worker thread and manage UI state.

        Parameters
        ----------
        button : QPushButton
            Button that initiated the background task.
        busy_text : str
            Temporary button label shown while work is running.
        run_callable : callable
            Function executed on the worker thread.
        on_success : callable
            Callback invoked with worker result payload.
        on_error_prefix : str
            Prefix used when reporting worker failures.

        Returns
        -------
        None
            Thread and worker lifecycle are managed internally.
        """
        button.setEnabled(False)
        original_text = button.text()
        button.setText(busy_text)

        thread = QThread(self)
        worker = _RunWorker(run_callable)
        worker.moveToThread(thread)

        def handle_success(payload) -> None:
            """Handle worker success payload on the GUI thread.

            Parameters
            ----------
            payload : object
                Result emitted by the worker.

            Returns
            -------
            None
                Delegates to caller callback and restores button state.
            """
            on_success(payload)
            self._finish_background(thread, worker, button, original_text)

        def handle_error(message: str) -> None:
            """Handle worker error signal on the GUI thread.

            Parameters
            ----------
            message : str
                Error message emitted by worker.

            Returns
            -------
            None
                Reports error and restores button state.
            """
            self._notify(f"{on_error_prefix}: {message}")
            self._finish_background(thread, worker, button, original_text)

        thread.started.connect(worker.run)
        worker.finished.connect(handle_success)
        worker.error.connect(handle_error)
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(worker.deleteLater)

        self._active_workers.append((thread, worker))
        thread.start()

    def _finish_background(
        self,
        thread: QThread,
        worker: QObject,
        button: QPushButton,
        original_text: str,
    ) -> None:
        """Restore UI state after a background thread exits.

        Parameters
        ----------
        thread : QThread
            Worker thread that completed.
        worker : QObject
            Worker object associated with ``thread``.
        button : QPushButton
            Trigger button to re-enable.
        original_text : str
            Button label to restore.

        Returns
        -------
        None
            UI state and active-worker registry are updated.
        """
        button.setEnabled(True)
        button.setText(original_text)
        if bool(getattr(self, "_download_locked", False)):
            self._download_button.setEnabled(False)
        else:
            self._download_button.setEnabled(bool(self._datasets))
        try:
            self._active_workers.remove((thread, worker))
        except ValueError:
            pass

    def _notify(self, message: str) -> None:
        """Update status text and emit napari warning notification when available.

        Parameters
        ----------
        message : str
            Message text to display and emit.

        Returns
        -------
        None
            Status label and optional napari console notifications are updated.
        """
        self._status_label.setText(message)
        if (
            show_console_notification is not None
            and Notification is not None
            and NotificationSeverity is not None
        ):
            try:
                show_console_notification(
                    Notification(message, severity=NotificationSeverity.WARNING)
                )
            except Exception:
                # Notification plumbing can fail in constrained test/runtime envs.
                pass
            try:
                sys.stdout.flush()
            except Exception:  # pragma: no cover - best-effort flush
                pass


__all__ = ["SenNetPortalBackgroundMixin", "_RunWorker"]
