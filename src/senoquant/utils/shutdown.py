"""Centralized shutdown-hook management for SenoQuant widgets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class ShutdownHook:
    """One named shutdown callback.

    Parameters
    ----------
    name : str
        Human-readable hook label.
    callback : callable
        Zero-argument callable invoked during shutdown.
    """

    name: str
    callback: Callable[[], None]


class ShutdownManager:
    """Run registered shutdown callbacks exactly once.

    Notes
    -----
    The manager is intentionally conservative: once shutdown begins, further
    invocations are ignored. This avoids duplicate cancellation attempts while
    multiple close paths race (for example main-window close and widget close).
    """

    def __init__(self) -> None:
        """Initialize empty shutdown hook registry."""
        self._hooks: list[ShutdownHook] = []
        self._has_run = False

    def register(self, name: str, callback: Callable[[], None]) -> None:
        """Register one callback to execute during shutdown.

        Parameters
        ----------
        name : str
            Human-readable callback label.
        callback : callable
            Zero-argument callback to invoke.

        Returns
        -------
        None
            Hook is appended to the manager registry.
        """
        self._hooks.append(ShutdownHook(name=str(name).strip() or "unnamed", callback=callback))

    def run_once(self) -> list[str]:
        """Execute all hooks exactly once and return any error messages.

        Returns
        -------
        list of str
            Non-fatal callback error messages. Empty when all hooks succeed.
        """
        if self._has_run:
            return []
        self._has_run = True

        errors: list[str] = []
        for hook in self._hooks:
            try:
                hook.callback()
            except Exception as exc:  # pragma: no cover - defensive cleanup path
                errors.append(f"{hook.name}: {exc}")
        return errors


__all__ = ["ShutdownHook", "ShutdownManager"]
