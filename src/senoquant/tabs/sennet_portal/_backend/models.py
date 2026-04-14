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
        SenNet manifest paths to transfer for this dataset. A single ``"/"``
        entry means download the whole dataset.
    compatible_extensions : list of str
        Optional extension hints detected from ``compatible_paths`` when the
        transfer scope targets specific files. Empty for whole-dataset
        downloads.
    source_type : str, optional
        Biological source label (for example, Human or Mouse).
    organ : str, optional
        Organ or tissue label associated with the dataset.
    sample_age : str, optional
        Best-effort normalized sample age label for table display.
    sample_age_value : float or None, optional
        Numeric sample age in ``sample_age_unit`` for sorting/filtering.
    sample_age_unit : str, optional
        Unit label for ``sample_age_value`` (``"years"`` or ``"months"``).
    dataset_uuid : str, optional
        Dataset UUID used by downstream transfer layout naming.
    entity_payload : dict of str to Any, optional
        Full Entity API payload associated with the dataset identifier.
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
    sample_age: str = "Unknown"
    sample_age_value: float | None = None
    sample_age_unit: str = ""
    dataset_uuid: str = ""
    entity_payload: dict[str, Any] = field(default_factory=dict)
    query_metadata: dict[str, Any] = field(default_factory=dict)


__all__ = ["SenNetDataset"]
