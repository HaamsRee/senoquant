"""Search orchestration mixin for the SenNet Portal backend."""

from __future__ import annotations

from typing import Any, Sequence

from ._backend_globus import SenNetPortalGlobusMixin
from ._backend_models import SenNetDataset


class SenNetPortalSearchMixin(SenNetPortalGlobusMixin):
    """Mixin containing dataset-search orchestration logic."""

    def search_datasets(
        self,
        *,
        dataset_types: Sequence[str] | None = None,
        token: str | None = None,
        max_results: int = 40,
        status: str = "Published",
    ) -> list[SenNetDataset]:
        """Find antibody-imaging datasets with supported image files.

        Parameters
        ----------
        dataset_types : sequence of str or None, optional
            SenNet dataset-type labels to query. If ``None`` the backend uses
            ``ANTIBODY_DATASET_TYPES``.
        token : str or None, optional
            Optional bearer token for authenticated API access.
        max_results : int, optional
            Maximum number of compatible datasets to return.
        status : str, optional
            Dataset status filter sent to the Search API.

        Returns
        -------
        list of SenNetDataset
            Compatible dataset records ordered by discovery time.

        Notes
        -----
        A dataset is considered compatible when it passes all checks:

        - Matches antibody-focused dataset criteria.
        - Has at least one file path with a supported extension from
          ``/param-search/files`` records.
        """
        requested_types = list(dataset_types or self.ANTIBODY_DATASET_TYPES)
        if not requested_types:
            return []
        limit = max(1, int(max_results))

        seen_ids: set[str] = set()
        datasets: list[SenNetDataset] = []
        for dataset_type in requested_types:
            payload = self._post_json(
                self.SEARCH_API_URL,
                payload=self._dataset_search_body(
                    dataset_type=str(dataset_type).strip(),
                    status=str(status).strip(),
                    size=max(200, limit),
                ),
                token=token,
            )
            for record in self._iter_dataset_records(payload):
                dataset_id = self._dataset_id_from_payload(record)
                if not dataset_id or dataset_id in seen_ids:
                    continue
                seen_ids.add(dataset_id)

                # Filter order:
                # 1) Must be Antibody-based imaging by first-level hierarchy.
                # 2) Must match requested dataset type(s).
                if not self._is_antibody_based_imaging(record):
                    continue
                if not self._matches_requested_dataset_type(record, requested_types):
                    continue

                compatible_paths = self._extract_supported_paths_from_param_search_files(
                    dataset_id,
                    token=token,
                )
                if not compatible_paths:
                    continue

                extensions = sorted(
                    {
                        ext
                        for path in compatible_paths
                        for ext in [self._matching_supported_extension(path)]
                        if ext is not None
                    }
                )
                datasets.append(
                    SenNetDataset(
                        sennet_id=dataset_id,
                        dataset_type=self._text_value(
                            record.get("dataset_type"),
                            default="Unknown",
                        ),
                        status=self._text_value(
                            record.get("status"),
                            default="Unknown",
                        ),
                        access_level=self._text_value(
                            record.get("access_level"),
                            record.get("data_access_level"),
                            default="Unknown",
                        ),
                        title=self._dataset_title(record, record, dataset_id),
                        compatible_paths=compatible_paths,
                        compatible_extensions=extensions,
                    )
                )
                if len(datasets) >= limit:
                    return datasets

        return datasets

    def _dataset_search_body(self, *, dataset_type: str, status: str, size: int) -> dict[str, Any]:
        """Build Elasticsearch request body for dataset search.

        Parameters
        ----------
        dataset_type : str
            SenNet dataset type to include in results.
        status : str
            SenNet status to include in results.
        size : int
            Maximum number of hits to request.

        Returns
        -------
        dict of str to Any
            Search API request payload.
        """
        return {
            "size": max(1, int(size)),
            "query": {
                "bool": {
                    "must": [
                        {"term": {"entity_type.keyword": "Dataset"}},
                        {
                            "term": {
                                "dataset_type_hierarchy.first_level.keyword": self.ANTIBODY_FIRST_LEVEL
                            }
                        },
                        {"term": {"dataset_type.keyword": dataset_type}},
                        {"term": {"status.keyword": status}},
                    ]
                }
            },
        }


__all__ = ["SenNetPortalSearchMixin"]
