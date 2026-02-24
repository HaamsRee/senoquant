"""Globus auth and file discovery mixin for the SenNet Portal backend."""

from __future__ import annotations

import shutil

from ._backend_api import SenNetPortalApiMixin
from ._backend_command import SenNetPortalCommandMixin
from ._backend_metadata import SenNetPortalMetadataMixin
from ._backend_paths import SenNetPortalPathMixin


class SenNetPortalGlobusMixin(
    SenNetPortalCommandMixin,
    SenNetPortalApiMixin,
    SenNetPortalMetadataMixin,
    SenNetPortalPathMixin,
):
    """Mixin containing Globus auth helpers and param-search file lookup."""

    def gcp_installation_status(self) -> tuple[bool, str]:
        """Return local Globus Connect Personal availability status.

        Returns
        -------
        tuple of (bool, str)
            A tuple where the first value indicates whether GCP appears
            available, and the second value contains a detail string.
        """
        if shutil.which("globus") is None:
            return False, "Globus CLI not found"

        local_id = self._run_command(["globus", "endpoint", "local-id"])
        if local_id.returncode != 0:
            stderr = (local_id.stderr or "").strip()
            stdout = (local_id.stdout or "").strip()
            detail = stderr or stdout or "Unable to verify Globus Connect Personal."
            if "No Globus Connect Personal installation found" in detail:
                return False, "Globus Connect Personal not installed"
            return False, detail

        endpoint_id_lines = (local_id.stdout or "").strip().splitlines()
        endpoint_id = endpoint_id_lines[0].strip() if endpoint_id_lines else ""
        if endpoint_id:
            return True, endpoint_id
        return False, "Globus Connect Personal not installed"

    def login_globus(self) -> None:
        """Run interactive Globus CLI login flow.

        Returns
        -------
        None
            The method returns when login command exits successfully.

        Raises
        ------
        RuntimeError
            If Globus CLI is unavailable or login command fails.
        """
        if shutil.which("globus") is None:
            raise RuntimeError(
                "Globus CLI was not found in PATH. Install `globus-cli` and retry."
            )

        login = self._run_command(["globus", "login"])
        if login.returncode != 0:
            stderr = (login.stderr or "").strip()
            stdout = (login.stdout or "").strip()
            detail = stderr or stdout or "Unknown Globus login error."
            raise RuntimeError(f"Globus login failed: {detail}")

        # Force re-validation after login.
        self._globus_ls_ready_cache = None

    def logout_globus(self) -> None:
        """Run Globus CLI logout flow for the current profile.

        Returns
        -------
        None
            The method returns when logout command exits successfully.

        Raises
        ------
        RuntimeError
            If Globus CLI is unavailable or logout command fails.
        """
        if shutil.which("globus") is None:
            raise RuntimeError(
                "Globus CLI was not found in PATH. Install `globus-cli` and retry."
            )

        logout = self._run_command(["globus", "logout", "--yes"])
        if logout.returncode != 0:
            stderr = (logout.stderr or "").strip()
            stdout = (logout.stdout or "").strip()
            detail = stderr or stdout or "Unknown Globus logout error."
            raise RuntimeError(f"Globus logout failed: {detail}")

        self._globus_ls_ready_cache = False

    def globus_login_status(self) -> tuple[bool, str]:
        """Return Globus CLI installation and authentication status.

        Returns
        -------
        tuple of (bool, str)
            A tuple where the first value indicates whether the user is logged
            in, and the second value contains a human-readable status detail.
        """
        if shutil.which("globus") is None:
            self._globus_ls_ready_cache = False
            return False, "Globus CLI not found"

        whoami = self._run_command(["globus", "whoami"])
        if whoami.returncode != 0:
            self._globus_ls_ready_cache = False
            return False, "Not logged in"

        identity = (whoami.stdout or "").strip().splitlines()
        detail = identity[0].strip() if identity else "Logged in"
        self._globus_ls_ready_cache = True
        return True, detail

    def _extract_supported_paths_from_param_search_files(
        self,
        dataset_id: str,
        *,
        token: str | None,
    ) -> list[str]:
        """Resolve supported dataset file paths via parameterized file search.

        Parameters
        ----------
        dataset_id : str
            SenNet dataset identifier to resolve (``dataset_sennet_id``).
        token : str or None
            Optional bearer token used when querying Search API.

        Returns
        -------
        list of str
            Normalized dataset-relative paths with supported extensions.

        Notes
        -----
        The Search API endpoint ``/param-search/files`` returns per-file records
        with ``rel_path`` and ``file_extension`` fields. This method extracts
        compatible paths from that payload.
        """
        payload = self._fetch_json(
            self.PARAM_SEARCH_FILES_URL,
            params={"dataset_sennet_id": dataset_id},
            token=token,
        )
        if not isinstance(payload, list):
            return []
        return self._extract_supported_paths(payload)


__all__ = ["SenNetPortalGlobusMixin"]
