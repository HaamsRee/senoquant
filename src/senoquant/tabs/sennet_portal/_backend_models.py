"""Shared backend models for the SenNet Portal tab."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SenNetDataset:
    """Serializable SenNet dataset description for the portal UI.

    Parameters
    ----------
    sennet_id : str
        Primary SenNet identifier for the dataset (for example, ``SNT...``).
    dataset_type : str
        SenNet dataset type label used for filtering and display.
    status : str
        Publication or curation status returned by SenNet.
    access_level : str
        Access level label (for example, public or consortium).
    title : str
        Human-readable title, dataset name, or fallback identifier.
    compatible_paths : list of str
        Dataset-relative file paths that match SenoQuant-supported formats.
    compatible_extensions : list of str
        Unique supported file extensions detected in ``compatible_paths``.
    source_type : str, optional
        Biological source label (for example, Human or Mouse).
    organ : str, optional
        Organ or tissue label associated with the dataset.
    dataset_uuid : str, optional
        Dataset UUID used by downstream transfer layout naming.
    query_metadata : dict of str to Any, optional
        Metadata about the originating search query and filters.
    """

    sennet_id: str
    dataset_type: str
    status: str
    access_level: str
    title: str
    compatible_paths: list[str]
    compatible_extensions: list[str]
    source_type: str = "Unknown"
    organ: str = "Unknown"
    dataset_uuid: str = ""
    query_metadata: dict[str, Any] = field(default_factory=dict)


__all__ = ["SenNetDataset"]
