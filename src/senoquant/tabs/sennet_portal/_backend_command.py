"""Command execution mixin for SenNet Portal backend helpers."""

from __future__ import annotations

import subprocess


class SenNetPortalCommandMixin:
    """Mixin containing subprocess execution helpers."""

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
        return subprocess.run(
            args,
            text=True,
            capture_output=True,
            check=False,
        )


__all__ = ["SenNetPortalCommandMixin"]
