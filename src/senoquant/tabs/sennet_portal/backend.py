"""Backend entrypoint for SenNet dataset discovery and downloads."""

from __future__ import annotations

from senoquant.reader.supported_extensions import supported_image_extensions

from ._backend_models import SenNetDataset
from ._backend_search import SenNetPortalSearchMixin
from ._backend_transfer import SenNetPortalTransferMixin


class SenNetPortalBackend(
    SenNetPortalSearchMixin,
    SenNetPortalTransferMixin,
):
    """Discover and download SenNet datasets that SenoQuant can ingest.

    Notes
    -----
    Discovery combines the SenNet Search API and parameterized file search:

    1. Search returns candidate dataset records.
    2. Records are filtered for antibody-based imaging.
    3. File compatibility is resolved from ``/param-search/files`` records.

    Downloads are executed through ``sennet-clt`` manifest transfers.
    """

    SEARCH_DATASETS_URL = "https://search.api.sennetconsortium.org/param-search/datasets"
    SEARCH_API_URL = "https://search.api.sennetconsortium.org/search"
    PARAM_SEARCH_FILES_URL = "https://search.api.sennetconsortium.org/param-search/files"
    ENTITY_API_URL = "https://entity.api.sennetconsortium.org"
    ORGANS_API_URL = "https://ontology.api.hubmapconsortium.org/organs"

    # SenNet dataset-type terms commonly used for antibody-based imaging.
    ANTIBODY_DATASET_TYPES = (
        "2D Imaging Mass Cytometry",
        "3D Imaging Mass Cytometry",
        "CODEX",
        "Confocal microscopy",
        "MIBI",
        "PhenoCycler",
        "Thick section Multiphoton MxIF",
    )
    ANTIBODY_FIRST_LEVEL = "Antibody-based imaging"

    _PATH_FIELD_NAMES = {
        "rel_path",
        "path",
        "file_path",
        "file_name",
        "filename",
        "name",
        "uri",
        "url",
    }

    def __init__(self, *, request_timeout: float = 30.0) -> None:
        """Initialize API and extension-matching settings.

        Parameters
        ----------
        request_timeout : float, optional
            Timeout in seconds for each HTTP request to SenNet APIs.

        Returns
        -------
        None
            This initializer stores configuration on the instance.
        """
        self._request_timeout = float(request_timeout)
        self._supported_image_extensions = supported_image_extensions()
        self._extension_check_order = tuple(
            sorted(self._supported_image_extensions, key=len, reverse=True)
        )
        self._globus_ls_ready_cache: bool | None = None
        self._organ_term_lookup_cache: dict[str, str] = {}


__all__ = ["SenNetDataset", "SenNetPortalBackend"]
