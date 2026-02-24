"""Download-transfer mixin for the SenNet Portal backend."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import shutil
import tempfile
from typing import Sequence

from ._backend_command import SenNetPortalCommandMixin
from ._backend_models import SenNetDataset
from ._backend_paths import SenNetPortalPathMixin


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
            ``destination``.

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

            if staging_dir is not None:
                self._merge_directory(staging_dir, destination_path)
        finally:
            shutil.rmtree(manifest_root, ignore_errors=True)
            if staging_dir is not None:
                shutil.rmtree(staging_dir, ignore_errors=True)

        return {
            "dataset_count": len(dataset_list),
            "file_count": len(manifest_lines),
            "destination": str(destination_path),
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
