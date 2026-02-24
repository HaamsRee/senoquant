"""Transfer-finalization helpers for SenNet Portal downloads."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
import shutil
from typing import Any, Sequence

from senoquant.utils.path_io import (
    copy_local_to_target,
    is_remote,
    join,
    mkdirs,
    normalize_uri,
    write_json,
)

from .models import SenNetDataset
from .paths import SenNetPortalPathMixin


class SenNetPortalTransferFinalizeMixin(SenNetPortalPathMixin):
    """Mixin containing post-transfer routing and metadata-writing helpers."""

    def _finalize_transfer_output(
        self,
        transfer_root: Path,
        destination: str | Path,
        datasets: Sequence[SenNetDataset],
    ) -> None:
        """Route completed transfer output to destination and write metadata.

        Parameters
        ----------
        transfer_root : pathlib.Path
            Local filesystem directory where ``sennet-clt`` wrote files.
        destination : str or pathlib.Path
            User-selected final destination, local or remote.
        datasets : sequence of SenNetDataset
            Dataset metadata rows included in the transfer request.

        Returns
        -------
        None
            Files are routed to the final destination and metadata JSON files
            are written into dataset-specific folders.
        """
        destination_uri = normalize_uri(destination)
        if is_remote(destination_uri):
            self._copy_tree_local_to_target(transfer_root, destination_uri)
            self._write_dataset_metadata_files_remote(destination_uri, datasets)
            shutil.rmtree(transfer_root, ignore_errors=True)
            return

        destination_path = Path(destination_uri).expanduser().resolve()
        destination_path.mkdir(parents=True, exist_ok=True)
        if transfer_root.resolve() != destination_path:
            self._merge_directory(transfer_root, destination_path)
            shutil.rmtree(transfer_root, ignore_errors=True)
        self._write_dataset_metadata_files_local(destination_path, datasets)

    def _copy_tree_local_to_target(self, source_root: Path, destination_uri: str) -> None:
        """Copy all files from a local tree into a local-or-remote destination.

        Parameters
        ----------
        source_root : pathlib.Path
            Local source directory containing downloaded files.
        destination_uri : str
            Destination root path/URI.

        Returns
        -------
        None
            Every file under ``source_root`` is copied to the destination while
            preserving relative paths.
        """
        if not source_root.exists():
            return
        mkdirs(destination_uri)
        for file_path in sorted(source_root.rglob("*")):
            if not file_path.is_file():
                continue
            relative = file_path.relative_to(source_root).as_posix()
            target = join(destination_uri, relative)
            copy_local_to_target(file_path, target)

    def _write_dataset_metadata_files_local(
        self,
        destination: Path,
        datasets: Sequence[SenNetDataset],
    ) -> None:
        """Write dataset metadata JSON files into local output folders.

        Parameters
        ----------
        destination : pathlib.Path
            Local destination directory containing dataset output folders.
        datasets : sequence of SenNetDataset
            Dataset rows included in the transfer request.

        Returns
        -------
        None
            Sidecar JSON files are created in matching dataset folders.
        """
        generated_at = datetime.now(UTC).isoformat()
        for dataset in datasets:
            payload = self._dataset_metadata_payload(dataset, generated_at=generated_at)
            for folder in self._dataset_output_dirs(destination, dataset):
                folder.mkdir(parents=True, exist_ok=True)
                metadata_path = folder / "sennet_dataset_metadata.json"
                metadata_path.write_text(
                    json.dumps(payload, indent=2, sort_keys=True),
                    encoding="utf-8",
                )

    def _write_dataset_metadata_files_remote(
        self,
        destination_uri: str,
        datasets: Sequence[SenNetDataset],
    ) -> None:
        """Write dataset metadata JSON files for a remote destination root.

        Parameters
        ----------
        destination_uri : str
            Remote destination root URI.
        datasets : sequence of SenNetDataset
            Dataset rows included in the transfer request.

        Returns
        -------
        None
            Sidecar JSON files are written to expected dataset folders using
            remote-path helpers.
        """
        generated_at = datetime.now(UTC).isoformat()
        for dataset in datasets:
            payload = self._dataset_metadata_payload(dataset, generated_at=generated_at)
            folder_name = self._expected_dataset_folder_name(dataset)
            metadata_path = join(destination_uri, folder_name, "sennet_dataset_metadata.json")
            write_json(metadata_path, payload)

    @staticmethod
    def _dataset_metadata_payload(
        dataset: SenNetDataset,
        *,
        generated_at: str,
    ) -> dict[str, Any]:
        """Build the saved metadata payload for one dataset.

        Parameters
        ----------
        dataset : SenNetDataset
            Dataset row being persisted.
        generated_at : str
            ISO timestamp used as metadata generation time.

        Returns
        -------
        dict of str to Any
            Serializable metadata payload written to JSON.
        """
        return {
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

    @staticmethod
    def _expected_dataset_folder_name(dataset: SenNetDataset) -> str:
        """Return expected dataset folder name emitted by ``sennet-clt``.

        Parameters
        ----------
        dataset : SenNetDataset
            Dataset metadata row.

        Returns
        -------
        str
            Expected dataset output folder name.
        """
        if dataset.dataset_uuid.strip():
            return f"{dataset.sennet_id}-{dataset.dataset_uuid}"
        return dataset.sennet_id

    @staticmethod
    def _dataset_output_dirs(destination: Path, dataset: SenNetDataset) -> list[Path]:
        """Resolve local output directories associated with a dataset transfer.

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


__all__ = ["SenNetPortalTransferFinalizeMixin"]
