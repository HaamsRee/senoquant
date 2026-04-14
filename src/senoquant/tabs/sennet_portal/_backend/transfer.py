"""Download-transfer mixin for the SenNet Portal backend."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
import shutil
import tempfile
from typing import Sequence

from senoquant.utils.path_io import is_remote, normalize_uri

from .command import SenNetPortalCommandMixin
from .models import SenNetDataset
from .transfer_finalize import SenNetPortalTransferFinalizeMixin
from .transfer_status import aggregate_task_status, extract_task_ids


class SenNetPortalTransferMixin(SenNetPortalCommandMixin, SenNetPortalTransferFinalizeMixin):
    """Mixin containing SenNet CLT transfer and filesystem merge logic."""

    def download_datasets(
        self,
        datasets: Sequence[SenNetDataset],
        destination: str | Path,
    ) -> dict[str, object]:
        """Download selected dataset manifest paths via ``sennet-clt``.

        Parameters
        ----------
        datasets : sequence of SenNetDataset
            Selected datasets whose manifest paths should be transferred.
        destination : str or pathlib.Path
            Local destination directory where downloaded files should end up.

        Returns
        -------
        dict of str to object
            Summary payload with ``dataset_count``, ``file_count``, and
            ``destination`` plus submitted Globus ``task_ids`` and
            ``download_scope``.

        Raises
        ------
        ValueError
            If no valid datasets were provided.
        RuntimeError
            If the CLT is missing, authentication is unavailable, or transfer
            execution fails.
        """
        dataset_list = [item for item in datasets if isinstance(item, SenNetDataset)]
        if not dataset_list:
            raise ValueError("Select at least one dataset to download.")

        if shutil.which("sennet-clt") is None:
            raise RuntimeError(
                "sennet-clt was not found in PATH. Install it and run `sennet-clt login`."
            )

        manifest_lines = self._build_manifest_lines(dataset_list)
        if not manifest_lines:
            raise RuntimeError(
                "No transfer manifest paths were available for the selected datasets."
            )
        download_scope = self._download_scope(dataset_list)
        destination_uri = normalize_uri(destination)
        destination_is_remote = is_remote(destination_uri)
        destination_path = (
            None
            if destination_is_remote
            else Path(destination_uri).expanduser().resolve()
        )
        if destination_path is not None:
            destination_path.mkdir(parents=True, exist_ok=True)
        clt_destination, transfer_root = self._resolve_transfer_target(
            destination_uri=destination_uri,
            destination_is_remote=destination_is_remote,
            local_destination=destination_path,
        )
        temporary_transfer_root = self._is_temporary_transfer_root(
            destination_is_remote=destination_is_remote,
            transfer_root=transfer_root,
            local_destination=destination_path,
        )

        auth_check = self._run_command(["sennet-clt", "whoami"])
        if auth_check.returncode != 0:
            raise RuntimeError(
                "SenNet authentication not available. Run `sennet-clt login` first."
            )

        manifest_root = Path(tempfile.mkdtemp(prefix="senoquant-sennet-manifest-"))
        manifest_path = manifest_root / "manifest.tsv"
        manifest_path.write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")

        try:
            command = [
                "sennet-clt",
                "transfer",
                str(manifest_path),
                "--destination",
                clt_destination,
            ]
            transfer = self._run_command(command)
            if transfer.returncode != 0:
                stderr = (transfer.stderr or "").strip()
                stdout = (transfer.stdout or "").strip()
                detail = stderr or stdout or "Unknown transfer error."
                raise RuntimeError(f"sennet-clt transfer failed: {detail}")
            task_ids = extract_task_ids(transfer.stdout, transfer.stderr)
        except Exception:
            if temporary_transfer_root:
                shutil.rmtree(transfer_root, ignore_errors=True)
            raise
        finally:
            shutil.rmtree(manifest_root, ignore_errors=True)

        if task_ids:
            self._register_pending_download(
                task_ids=task_ids,
                transfer_root=transfer_root,
                destination_uri=destination_uri,
                datasets=dataset_list,
                cleanup_transfer_root=temporary_transfer_root,
            )
        else:
            self._finalize_transfer_output(transfer_root, destination_uri, dataset_list)

        return {
            "dataset_count": len(dataset_list),
            "file_count": 0 if download_scope == "dataset" else len(manifest_lines),
            "destination": destination_uri,
            "task_ids": task_ids,
            "download_scope": download_scope,
        }

    @staticmethod
    def _download_scope(datasets: Sequence[SenNetDataset]) -> str:
        """Return aggregate download scope for a selected dataset list."""
        if datasets and all(dataset.compatible_paths == ["/"] for dataset in datasets):
            return "dataset"
        return "file"

    def download_tasks_status(self, task_ids: Sequence[str]) -> dict[str, object]:
        """Return aggregate live status for one or more Globus task IDs.

        Parameters
        ----------
        task_ids : sequence of str
            Globus transfer task identifiers.

        Returns
        -------
        dict of str to object
            Aggregated task status including progress counters, speed, and
            completion flags for UI polling.

        Raises
        ------
        ValueError
            If no task IDs were provided.
        RuntimeError
            If Globus CLI is unavailable or task details cannot be queried.
        """
        cleaned_ids = [str(task_id).strip() for task_id in task_ids if str(task_id).strip()]
        if not cleaned_ids:
            raise ValueError("No task IDs were provided for progress polling.")
        if shutil.which("globus") is None:
            raise RuntimeError("Globus CLI not found in PATH.")

        payloads: list[dict[str, object]] = []
        for task_id in cleaned_ids:
            command = ["globus", "task", "show", task_id, "--format", "json"]
            result = self._run_command(command)
            if result.returncode != 0:
                stderr = (result.stderr or "").strip()
                stdout = (result.stdout or "").strip()
                detail = stderr or stdout or "Unknown task status error."
                raise RuntimeError(f"Failed to query task {task_id}: {detail}")
            try:
                payload = json.loads((result.stdout or "").strip())
            except Exception as exc:
                raise RuntimeError(f"Task {task_id} returned invalid JSON output.") from exc
            if not isinstance(payload, dict):
                raise RuntimeError(f"Task {task_id} returned unexpected output shape.")
            payloads.append(payload)

        status = aggregate_task_status(payloads)
        if bool(status.get("all_complete", False)):
            self._finalize_pending_download(
                task_ids=cleaned_ids,
                all_succeeded=bool(status.get("all_succeeded", False)),
            )
        return status

    def cancel_download_tasks(self, task_ids: Sequence[str]) -> None:
        """Cancel active Globus tasks associated with current download session.

        Parameters
        ----------
        task_ids : sequence of str
            Task IDs to cancel.

        Returns
        -------
        None
            Cancellation is attempted best-effort for each task ID.
        """
        self._cancel_running_commands()
        cleaned_ids = [str(task_id).strip() for task_id in task_ids if str(task_id).strip()]
        if not cleaned_ids:
            return
        payload = self._pending_downloads.pop(self._task_key(cleaned_ids), None)
        self._cleanup_pending_transfer_root(payload)
        if shutil.which("globus") is None:
            return
        for task_id in cleaned_ids:
            self._run_command(["globus", "task", "cancel", task_id])

    def _resolve_transfer_target(
        self,
        *,
        destination_uri: str,
        destination_is_remote: bool,
        local_destination: Path | None,
    ) -> tuple[str, Path]:
        """Resolve CLT destination argument and local transfer root directory.

        Parameters
        ----------
        destination_uri : str
            Normalized user-selected destination path/URI.
        destination_is_remote : bool
            Whether the destination targets a remote filesystem.
        local_destination : pathlib.Path or None
            Resolved local destination path when destination is local.

        Returns
        -------
        tuple of (str, pathlib.Path)
            CLT destination argument and local transfer-root directory.
        """
        if destination_is_remote:
            staging_root = self._new_staging_dir()
            return str(staging_root.relative_to(self._home_dir())), staging_root

        if local_destination is None:
            raise RuntimeError(f"Could not resolve local destination: {destination_uri}")

        clt_destination, staging_dir = self._resolve_clt_destination(local_destination)
        return clt_destination, (staging_dir or local_destination)

    @staticmethod
    def _is_temporary_transfer_root(
        *,
        destination_is_remote: bool,
        transfer_root: Path,
        local_destination: Path | None,
    ) -> bool:
        """Return whether transfer root is temporary and safe to delete on error.

        Parameters
        ----------
        destination_is_remote : bool
            Whether destination is remote.
        transfer_root : pathlib.Path
            Local directory used as CLT transfer target.
        local_destination : pathlib.Path or None
            Requested local destination when applicable.

        Returns
        -------
        bool
            ``True`` when ``transfer_root`` is temporary staging storage.
        """
        if destination_is_remote:
            return True
        if local_destination is None:
            return True
        return transfer_root.resolve() != local_destination.resolve()

    def _register_pending_download(
        self,
        *,
        task_ids: Sequence[str],
        transfer_root: Path,
        destination_uri: str,
        datasets: Sequence[SenNetDataset],
        cleanup_transfer_root: bool,
    ) -> None:
        """Persist pending download context for post-transfer finalization.

        Parameters
        ----------
        task_ids : sequence of str
            Globus task IDs submitted by ``sennet-clt``.
        transfer_root : pathlib.Path
            Local transfer root written by CLT.
        destination_uri : str
            User-selected final destination.
        datasets : sequence of SenNetDataset
            Dataset rows included in the transfer request.
        cleanup_transfer_root : bool
            Whether ``transfer_root`` is temporary staging and should be
            deleted when the transfer is canceled.

        Returns
        -------
        None
            Pending context is stored in-memory and keyed by task IDs.
        """
        key = self._task_key(task_ids)
        self._pending_downloads[key] = {
            "transfer_root": str(transfer_root),
            "destination_uri": destination_uri,
            "datasets": list(datasets),
            "cleanup_transfer_root": bool(cleanup_transfer_root),
        }

    def _finalize_pending_download(
        self,
        *,
        task_ids: Sequence[str],
        all_succeeded: bool,
    ) -> None:
        """Finalize pending download output when tracked tasks are terminal.

        Parameters
        ----------
        task_ids : sequence of str
            Task IDs associated with one submitted transfer.
        all_succeeded : bool
            Whether all terminal task states indicate success.

        Returns
        -------
        None
            Pending context is removed after completion; successful transfers
            are finalized to destination.
        """
        key = self._task_key(task_ids)
        payload = self._pending_downloads.pop(key, None)
        if not isinstance(payload, dict):
            return
        if not all_succeeded:
            return

        transfer_root = Path(str(payload.get("transfer_root", ""))).expanduser().resolve()
        destination_uri = str(payload.get("destination_uri", "")).strip()
        if not destination_uri:
            return
        datasets_payload = payload.get("datasets")
        if not isinstance(datasets_payload, list):
            return
        datasets = [item for item in datasets_payload if isinstance(item, SenNetDataset)]
        self._finalize_transfer_output(transfer_root, destination_uri, datasets)

    @staticmethod
    def _task_key(task_ids: Sequence[str]) -> tuple[str, ...]:
        """Return canonical tuple key for task-ID collection.

        Parameters
        ----------
        task_ids : sequence of str
            Task identifiers to normalize.

        Returns
        -------
        tuple of str
            Deduplicated lowercase task IDs sorted for stable dictionary keys.
        """
        unique = {str(task_id).strip().lower() for task_id in task_ids if str(task_id).strip()}
        return tuple(sorted(unique))

    @staticmethod
    def _cleanup_pending_transfer_root(payload: object) -> None:
        """Delete temporary pending transfer roots when cancellation occurs.

        Parameters
        ----------
        payload : object
            Pending download payload popped from internal tracking map.

        Returns
        -------
        None
            Deletes the tracked transfer root when marked as temporary staging.
        """
        if not isinstance(payload, dict):
            return
        if not bool(payload.get("cleanup_transfer_root", False)):
            return
        transfer_root_text = str(payload.get("transfer_root", "")).strip()
        if not transfer_root_text:
            return
        transfer_root = Path(transfer_root_text).expanduser().resolve()
        shutil.rmtree(transfer_root, ignore_errors=True)

    def _resolve_clt_destination(self, destination: Path) -> tuple[str, Path | None]:
        """Resolve transfer destination argument accepted by ``sennet-clt``.

        Parameters
        ----------
        destination : pathlib.Path
            Requested local output directory.

        Returns
        -------
        tuple of (str, pathlib.Path or None)
            Relative destination for CLT and optional staging directory used
            when the requested destination is outside the home directory.
        """
        home = self._home_dir()
        try:
            relative = destination.relative_to(home)
        except ValueError:
            timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            staging = home / "sennet-downloads" / f"senoquant-{timestamp}"
            staging.mkdir(parents=True, exist_ok=True)
            return str(staging.relative_to(home)), staging

        rel_text = str(relative)
        return (rel_text if rel_text else "."), None

    def _new_staging_dir(self) -> Path:
        """Create and return a local staging directory under the user home.

        Returns
        -------
        pathlib.Path
            Freshly created local staging directory used for CLT output.
        """
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        staging = self._home_dir() / "sennet-downloads" / f"senoquant-{timestamp}"
        staging.mkdir(parents=True, exist_ok=True)
        return staging

    @staticmethod
    def _home_dir() -> Path:
        """Return normalized user home directory.

        Returns
        -------
        pathlib.Path
            Expanded and resolved home directory path.
        """
        return Path.home().expanduser().resolve()

__all__ = ["SenNetPortalTransferMixin"]
