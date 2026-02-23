"""Globus auth and listing mixin for the SenNet Portal backend."""

from __future__ import annotations

import json
import shutil
from typing import Any


class SenNetPortalGlobusMixin:
    """Mixin containing Globus authentication and listing helpers."""

    def _require_globus_login_for_search(self) -> None:
        """Validate Globus CLI availability and login state for dataset search.

        Returns
        -------
        None
            The method returns only when Globus CLI exists and the current
            environment is authenticated.

        Raises
        ------
        RuntimeError
            If Globus CLI is unavailable or the user is not logged in.
        """
        if shutil.which("globus") is None:
            raise RuntimeError(
                "Globus CLI was not found in PATH. Install `globus-cli`, run `globus login`, "
                "and retry the search."
            )
        auth_probe = self._run_command(["globus", "whoami"])
        if auth_probe.returncode != 0:
            raise RuntimeError(
                "Globus login is required for file discovery. Run `globus login` and retry."
            )
        self._globus_ls_ready_cache = True

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

    def _extract_supported_paths_from_globus(
        self,
        dataset_id: str,
        *,
        token: str | None,
    ) -> list[str]:
        """Resolve supported dataset file paths via SenNet Ingest + Globus ls.

        Parameters
        ----------
        dataset_id : str
            SenNet dataset identifier to resolve.
        token : str or None
            Optional bearer token used when calling the Ingest endpoint.

        Returns
        -------
        list of str
            Normalized dataset-relative paths with supported extensions.

        Notes
        -----
        This fallback is used when Search API records do not include a usable
        file list (for example, some ``PhenoCycler`` datasets). It requires:

        - ``globus`` CLI to be installed and in ``PATH``.
        - Active Globus login (`globus whoami` succeeds).
        """
        if not self._can_list_globus_paths():
            return []

        target = self._fetch_globus_target_for_dataset(dataset_id, token=token)
        if target is None:
            return []

        endpoint_uuid, rel_path = target
        candidates = self._list_globus_paths(endpoint_uuid, rel_path)
        supported: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            normalized = self._normalize_manifest_path(candidate)
            if not normalized:
                continue
            if self._matching_supported_extension(normalized) is None:
                continue
            if normalized in seen:
                continue
            seen.add(normalized)
            supported.append(normalized)
        return supported

    def _fetch_globus_target_for_dataset(
        self,
        dataset_id: str,
        *,
        token: str | None,
    ) -> tuple[str, str] | None:
        """Fetch Globus endpoint UUID and dataset root path for a dataset.

        Parameters
        ----------
        dataset_id : str
            SenNet dataset identifier.
        token : str or None
            Optional bearer token for authenticated requests.

        Returns
        -------
        tuple of (str, str) or None
            ``(globus_endpoint_uuid, rel_path)`` when resolvable, otherwise
            ``None``.
        """
        payload = self._post_json(
            f"{self.INGEST_API_URL}/entities/file-system-rel-path",
            payload=[dataset_id],
            token=token,
        )
        if not isinstance(payload, list):
            return None

        for item in payload:
            if not isinstance(item, dict):
                continue
            candidate_id = self._text_value(item.get("id"), item.get("sennet_id"), default="")
            if candidate_id != dataset_id:
                continue
            endpoint_uuid = self._text_value(item.get("globus_endpoint_uuid"), default="")
            rel_path = self._text_value(item.get("rel_path"), default="")
            if endpoint_uuid and rel_path:
                return endpoint_uuid, rel_path
        return None

    def _list_globus_paths(self, endpoint_uuid: str, rel_path: str) -> list[str]:
        """List candidate file paths from Globus for a dataset directory.

        Parameters
        ----------
        endpoint_uuid : str
            Globus endpoint UUID returned by SenNet Ingest.
        rel_path : str
            Dataset directory path on the source Globus endpoint.

        Returns
        -------
        list of str
            Candidate file paths discovered from Globus listing output.
        """
        endpoint_ref = f"{endpoint_uuid}:{rel_path}"
        command = [
            "globus",
            "ls",
            endpoint_ref,
            "--recursive",
            "--recursive-depth-limit",
            "25",
            "--format=JSON",
        ]
        response = self._run_command(command)
        if response.returncode != 0:
            return []

        try:
            payload = json.loads((response.stdout or "").strip() or "{}")
        except Exception:
            return []

        return self._candidate_paths_from_globus_listing(payload, base_path=rel_path)

    def _can_list_globus_paths(self) -> bool:
        """Return whether Globus CLI is available and authenticated.

        Returns
        -------
        bool
            ``True`` when ``globus`` executable exists and ``globus whoami``
            succeeds in the current runtime environment.
        """
        if self._globus_ls_ready_cache is not None:
            return self._globus_ls_ready_cache
        if shutil.which("globus") is None:
            self._globus_ls_ready_cache = False
            return False
        probe = self._run_command(["globus", "whoami"])
        self._globus_ls_ready_cache = probe.returncode == 0
        return self._globus_ls_ready_cache

    def _candidate_paths_from_globus_listing(
        self,
        payload: object,
        *,
        base_path: str,
    ) -> list[str]:
        """Extract file-path candidates from ``globus ls --format=JSON`` data.

        Parameters
        ----------
        payload : object
            Parsed JSON payload from ``globus ls``.
        base_path : str
            Dataset directory used as fallback prefix when entries provide only
            file names.

        Returns
        -------
        list of str
            Candidate file paths that can be normalized and extension-filtered.
        """
        entries: list[object]
        if isinstance(payload, dict):
            raw = payload.get("DATA")
            entries = raw if isinstance(raw, list) else []
        elif isinstance(payload, list):
            entries = payload
        else:
            entries = []

        root = self._normalize_manifest_path(base_path) or "/"
        paths: list[str] = []
        for entry in entries:
            if isinstance(entry, str):
                paths.append(entry)
                continue
            if not isinstance(entry, dict):
                continue
            entry_type = self._text_value(entry.get("type"), default="").lower()
            if entry_type and entry_type != "file":
                continue

            explicit_path = self._text_value(
                entry.get("path"),
                entry.get("source_path"),
                default="",
            )
            if explicit_path:
                paths.append(explicit_path)
                continue

            name = self._text_value(
                entry.get("name"),
                entry.get("filename"),
                default="",
            )
            if not name:
                continue
            if name.startswith("/"):
                paths.append(name)
            else:
                paths.append(f"{root.rstrip('/')}/{name.lstrip('/')}")
        return paths


__all__ = ["SenNetPortalGlobusMixin"]
