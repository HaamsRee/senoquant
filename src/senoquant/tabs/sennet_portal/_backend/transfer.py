"""Download-transfer mixin for the SenNet Portal backend."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
import re
import shutil
import tempfile
from typing import Sequence

from .command import SenNetPortalCommandMixin
from .models import SenNetDataset
from .paths import SenNetPortalPathMixin


class SenNetPortalTransferMixin(SenNetPortalCommandMixin, SenNetPortalPathMixin):
    """Mixin containing SenNet CLT transfer and filesystem merge logic."""

    def download_datasets(
        self,
        datasets: Sequence[SenNetDataset],
        destination: str | Path,
    ) -> dict[str, object]:
        """Download selected dataset file paths via ``sennet-clt`` manifest mode.

        Parameters
        ----------
        datasets : sequence of SenNetDataset
            Selected datasets whose compatible paths should be transferred.
        destination : str or pathlib.Path
            Local destination directory where downloaded files should end up.

        Returns
        -------
        dict of str to object
            Summary payload with ``dataset_count``, ``file_count``, and
            ``destination`` plus submitted Globus ``task_ids``.

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
                "No compatible file paths were available for the selected datasets."
            )

        destination_path = Path(destination).expanduser().resolve()
        destination_path.mkdir(parents=True, exist_ok=True)
        clt_destination, staging_dir = self._resolve_clt_destination(destination_path)

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
            task_ids = self._extract_task_ids(transfer.stdout, transfer.stderr)

            if staging_dir is not None:
                self._merge_directory(staging_dir, destination_path)
            self._write_dataset_metadata_files(destination_path, dataset_list)
        finally:
            shutil.rmtree(manifest_root, ignore_errors=True)
            if staging_dir is not None:
                shutil.rmtree(staging_dir, ignore_errors=True)

        return {
            "dataset_count": len(dataset_list),
            "file_count": len(manifest_lines),
            "destination": str(destination_path),
            "task_ids": task_ids,
        }

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

        return self._aggregate_task_status(payloads)

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
        cleaned_ids = [str(task_id).strip() for task_id in task_ids if str(task_id).strip()]
        if not cleaned_ids:
            return
        if shutil.which("globus") is None:
            return
        for task_id in cleaned_ids:
            self._run_command(["globus", "task", "cancel", task_id])

    @staticmethod
    def _extract_task_ids(stdout: str | None, stderr: str | None) -> list[str]:
        """Extract Globus transfer task IDs from ``sennet-clt`` output text.

        Parameters
        ----------
        stdout : str or None
            Standard output emitted by ``sennet-clt transfer``.
        stderr : str or None
            Standard error emitted by ``sennet-clt transfer``.

        Returns
        -------
        list of str
            Unique task identifiers in appearance order.
        """
        text = "\n".join(part for part in ((stdout or ""), (stderr or "")) if part).strip()
        if not text:
            return []
        matches = re.findall(
            r"Task ID:\s*([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})",
            text,
            flags=re.IGNORECASE,
        )
        unique: list[str] = []
        seen: set[str] = set()
        for task_id in matches:
            normalized = task_id.lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            unique.append(normalized)
        return unique

    @staticmethod
    def _aggregate_task_status(tasks: Sequence[dict[str, object]]) -> dict[str, object]:
        """Aggregate per-task Globus payloads into one progress summary.

        Parameters
        ----------
        tasks : sequence of dict of str to object
            Raw JSON payloads from ``globus task show --format json``.

        Returns
        -------
        dict of str to object
            Unified status payload for frontend polling.
        """
        terminal_states = {"SUCCEEDED", "FAILED", "CANCELED", "EXPIRED"}
        total_subtasks = 0
        completed_subtasks = 0
        files = 0
        speed_bps = 0
        bytes_transferred = 0
        statuses: list[str] = []
        task_rows: list[dict[str, object]] = []

        for payload in tasks:
            status = str(payload.get("status", "")).upper().strip()
            statuses.append(status)
            subtasks_total = int(payload.get("subtasks_total", 0) or 0)
            subtasks_pending = int(payload.get("subtasks_pending", 0) or 0)
            subtasks_retrying = int(payload.get("subtasks_retrying", 0) or 0)
            total_subtasks += subtasks_total
            completed_subtasks += max(0, subtasks_total - subtasks_pending - subtasks_retrying)
            files += int(payload.get("files", 0) or 0)
            speed_bps += int(payload.get("effective_bytes_per_second", 0) or 0)
            bytes_transferred += int(payload.get("bytes_transferred", 0) or 0)
            task_rows.append(
                {
                    "task_id": str(payload.get("task_id", "")).strip(),
                    "status": status,
                    "files": int(payload.get("files", 0) or 0),
                    "subtasks_total": subtasks_total,
                    "subtasks_pending": subtasks_pending,
                    "subtasks_succeeded": int(payload.get("subtasks_succeeded", 0) or 0),
                    "subtasks_failed": int(payload.get("subtasks_failed", 0) or 0),
                    "speed_bps": int(payload.get("effective_bytes_per_second", 0) or 0),
                    "bytes_transferred": int(payload.get("bytes_transferred", 0) or 0),
                }
            )

        progress_percent = (
            int(round((completed_subtasks / total_subtasks) * 100))
            if total_subtasks > 0
            else 0
        )
        all_complete = all(status in terminal_states for status in statuses)
        any_failed = any(status in {"FAILED", "CANCELED", "EXPIRED"} for status in statuses)
        if all(status == "SUCCEEDED" for status in statuses):
            overall = "SUCCEEDED"
        elif all_complete and any_failed:
            overall = "FAILED"
        elif any(status == "ACTIVE" for status in statuses):
            overall = "ACTIVE"
        else:
            overall = statuses[0] if statuses else "UNKNOWN"

        return {
            "task_count": len(tasks),
            "overall_status": overall,
            "all_complete": all_complete,
            "all_succeeded": all_complete and not any_failed,
            "any_failed": any_failed,
            "progress_percent": max(0, min(100, progress_percent)),
            "files": files,
            "subtasks_total": total_subtasks,
            "subtasks_completed": completed_subtasks,
            "speed_bps": speed_bps,
            "bytes_transferred": bytes_transferred,
            "tasks": task_rows,
        }

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

    def _write_dataset_metadata_files(
        self,
        destination: Path,
        datasets: Sequence[SenNetDataset],
    ) -> None:
        """Write dataset metadata JSON files into dataset output folders.

        Parameters
        ----------
        destination : pathlib.Path
            Destination directory containing SenNet CLT output folders.
        datasets : sequence of SenNetDataset
            Dataset rows included in the transfer request.

        Returns
        -------
        None
            Sidecar JSON files are created in matching dataset folders.
        """
        generated_at = datetime.now(UTC).isoformat()
        for dataset in datasets:
            for folder in self._dataset_output_dirs(destination, dataset):
                folder.mkdir(parents=True, exist_ok=True)
                payload = {
                    "generated_at_utc": generated_at,
                    "generated_by": "SenoQuant SenNet Portal",
                    "dataset": {
                        "sennet_id": dataset.sennet_id,
                        "dataset_uuid": dataset.dataset_uuid,
                        "dataset_type": dataset.dataset_type,
                        "source_type": dataset.source_type,
                        "organ": dataset.organ,
                        "sample_age": dataset.sample_age,
                        "sample_age_value": dataset.sample_age_value,
                        "sample_age_unit": dataset.sample_age_unit,
                        "status": dataset.status,
                        "access_level": dataset.access_level,
                        "title": dataset.title,
                    },
                    "sennet_entity_payload": dataset.entity_payload,
                    "compatible_paths": dataset.compatible_paths,
                    "compatible_extensions": dataset.compatible_extensions,
                }
                metadata_path = folder / "sennet_dataset_metadata.json"
                metadata_path.write_text(
                    json.dumps(payload, indent=2, sort_keys=True),
                    encoding="utf-8",
                )

    @staticmethod
    def _dataset_output_dirs(destination: Path, dataset: SenNetDataset) -> list[Path]:
        """Resolve output directories associated with a dataset transfer.

        Parameters
        ----------
        destination : pathlib.Path
            Root transfer destination directory.
        dataset : SenNetDataset
            Dataset metadata used to identify target subfolders.

        Returns
        -------
        list of pathlib.Path
            Candidate dataset directories where metadata JSON should be stored.
        """
        expected_dirs: list[Path] = []
        prefix = f"{dataset.sennet_id}-"
        if dataset.dataset_uuid.strip():
            expected_dirs.append(destination / f"{dataset.sennet_id}-{dataset.dataset_uuid}")

        if destination.exists():
            for child in destination.iterdir():
                if not child.is_dir():
                    continue
                if child.name == dataset.sennet_id or child.name.startswith(prefix):
                    expected_dirs.append(child)

        unique: list[Path] = []
        seen: set[Path] = set()
        for path in expected_dirs:
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            unique.append(path)
        if not unique:
            unique.append(destination / dataset.sennet_id)
        return unique

    @staticmethod
    def _home_dir() -> Path:
        """Return normalized user home directory.

        Returns
        -------
        pathlib.Path
            Expanded and resolved home directory path.
        """
        return Path.home().expanduser().resolve()

    def _merge_directory(self, source: Path, destination: Path) -> None:
        """Recursively move contents from ``source`` into ``destination``.

        Parameters
        ----------
        source : pathlib.Path
            Directory containing staged transfer output.
        destination : pathlib.Path
            Final destination directory for merged files.

        Returns
        -------
        None
            Files are moved in place; duplicate names are deduplicated.
        """
        if not source.exists():
            return
        destination.mkdir(parents=True, exist_ok=True)
        for child in source.iterdir():
            target = destination / child.name
            if child.is_dir():
                self._merge_directory(child, target)
                child.rmdir()
                continue
            resolved_target = self._dedupe_path(target)
            resolved_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(child), str(resolved_target))

    @staticmethod
    def _dedupe_path(target: Path) -> Path:
        """Return a non-conflicting output path by appending numeric suffixes.

        Parameters
        ----------
        target : pathlib.Path
            Desired output file path.

        Returns
        -------
        pathlib.Path
            Original path when unused, else first available suffixed variant.
        """
        if not target.exists():
            return target
        suffix = "".join(target.suffixes)
        stem = target.name[: -len(suffix)] if suffix else target.name
        counter = 1
        while True:
            candidate = target.with_name(f"{stem}_{counter}{suffix}")
            if not candidate.exists():
                return candidate
            counter += 1


__all__ = ["SenNetPortalTransferMixin"]
