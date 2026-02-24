"""Tests for SenNet Portal command-process tracking helpers."""

from __future__ import annotations

from senoquant.tabs.sennet_portal.backend import SenNetPortalBackend
from senoquant.tabs.sennet_portal._backend import command as command_module


def test_run_command_tracks_process_and_captures_output(
    monkeypatch,
) -> None:
    """Track active process lifecycle and return captured text output."""
    backend = SenNetPortalBackend()

    class _FakePopen:
        def __init__(self, args, *, text, stdout, stderr) -> None:
            self.args = list(args)
            self.returncode = 0
            self._communicated = False
            assert text is True
            assert stdout is not None
            assert stderr is not None

        def communicate(self):
            self._communicated = True
            self.returncode = 7
            return "stdout-text", "stderr-text"

        def poll(self):
            if not self._communicated:
                return None
            return self.returncode

    monkeypatch.setattr(command_module.subprocess, "Popen", _FakePopen)

    result = backend._run_command(["fake", "command"])

    assert result.returncode == 7
    assert result.stdout == "stdout-text"
    assert result.stderr == "stderr-text"
    assert len(backend._active_commands) == 0


def test_cancel_running_commands_noops_when_no_active_processes() -> None:
    """Return quickly when no active commands are tracked."""
    backend = SenNetPortalBackend()
    backend._active_commands.clear()
    backend._cancel_running_commands()
    assert backend._active_commands == set()


def test_cancel_running_commands_terminates_and_kills_as_needed() -> None:
    """Terminate running commands and force-kill stubborn processes."""
    backend = SenNetPortalBackend()

    class _FakeProcess:
        def __init__(self, *, running: bool, exits_on_wait: bool) -> None:
            self._running = running
            self._exits_on_wait = exits_on_wait
            self.terminate_calls = 0
            self.wait_calls: list[float] = []
            self.kill_calls = 0

        def poll(self):
            return None if self._running else 0

        def terminate(self) -> None:
            self.terminate_calls += 1

        def wait(self, timeout: float) -> None:
            self.wait_calls.append(timeout)
            if self._exits_on_wait:
                self._running = False

        def kill(self) -> None:
            self.kill_calls += 1
            self._running = False

    graceful = _FakeProcess(running=True, exits_on_wait=True)
    stubborn = _FakeProcess(running=True, exits_on_wait=False)
    stopped = _FakeProcess(running=False, exits_on_wait=False)
    backend._active_commands = {graceful, stubborn, stopped}

    backend._cancel_running_commands()

    assert graceful.terminate_calls == 1
    assert len(graceful.wait_calls) == 1
    assert graceful.kill_calls == 0
    assert graceful.poll() == 0

    assert stubborn.terminate_calls == 1
    assert len(stubborn.wait_calls) == 1
    assert stubborn.kill_calls == 1
    assert stubborn.poll() == 0

    assert stopped.terminate_calls == 0
    assert stopped.wait_calls == []
    assert stopped.kill_calls == 0
