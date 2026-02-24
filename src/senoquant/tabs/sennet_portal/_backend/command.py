"""Command execution mixin for SenNet Portal backend helpers."""

from __future__ import annotations

import contextlib
import subprocess
import threading
import time


class SenNetPortalCommandMixin:
    """Mixin containing subprocess execution helpers."""

    def _initialize_command_state(self) -> None:
        """Initialize command-process tracking used for cancellation.

        Returns
        -------
        None
            Mutable process registry and synchronization lock are initialized.
        """
        self._active_commands: set[subprocess.Popen[str]] = set()
        self._active_commands_lock = threading.Lock()

    def _run_command(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        """Execute a subprocess command and capture text output.

        Parameters
        ----------
        args : list of str
            Argument vector for subprocess execution.

        Returns
        -------
        subprocess.CompletedProcess of str
            Completed process with captured ``stdout`` and ``stderr``.
        """
        process = subprocess.Popen(
            args,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        lock = self._active_commands_lock
        with lock:
            self._active_commands.add(process)
        try:
            stdout, stderr = process.communicate()
            return subprocess.CompletedProcess(
                args=args,
                returncode=int(process.returncode or 0),
                stdout=stdout,
                stderr=stderr,
            )
        finally:
            with lock:
                self._active_commands.discard(process)

    def _cancel_running_commands(self) -> None:
        """Terminate any currently running subprocess commands.

        Returns
        -------
        None
            Active tracked processes are terminated or force-killed.
        """
        lock = self._active_commands_lock
        with lock:
            processes = list(self._active_commands)
        if not processes:
            return

        for process in processes:
            if process.poll() is not None:
                continue
            with contextlib.suppress(Exception):
                process.terminate()

        deadline = time.monotonic() + 2.0
        for process in processes:
            if process.poll() is not None:
                continue
            timeout = max(0.0, deadline - time.monotonic())
            with contextlib.suppress(Exception):
                process.wait(timeout=timeout)
            if process.poll() is not None:
                continue
            with contextlib.suppress(Exception):
                process.kill()


__all__ = ["SenNetPortalCommandMixin"]
