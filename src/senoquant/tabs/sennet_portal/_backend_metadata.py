"""Metadata normalization mixin for the SenNet Portal backend."""

from __future__ import annotations

from typing import Any, Iterable, Sequence


class SenNetPortalMetadataMixin:
    """Mixin containing payload normalization and metadata helpers."""

    def _iter_dataset_records(self, payload: object) -> Iterable[dict[str, Any]]:
        """Yield normalized dataset-like records from SenNet payloads.

        Parameters
        ----------
        payload : object
            Raw response payload from SenNet endpoints.

        Yields
        ------
        dict of str to Any
            Dataset records normalized to the best-available dictionary shape.

        Notes
        -----
        This parser intentionally targets the observed SenNet response shapes:

        - ``param-search`` endpoints return a top-level list of records.
        - ``/search`` endpoint returns Elasticsearch-style
          ``{"hits": {"hits": [...]}}`` payloads.
        """
        if isinstance(payload, list):
            for item in payload:
                record = self._record_from_item(item)
                if record is not None:
                    yield record
            return

        if not isinstance(payload, dict):
            return

        hits_wrapper = payload.get("hits")
        if isinstance(hits_wrapper, list):
            for item in hits_wrapper:
                record = self._record_from_item(item)
                if record is not None:
                    yield record
            return

        if isinstance(hits_wrapper, dict):
            inner_hits = hits_wrapper.get("hits")
            if isinstance(inner_hits, list):
                for item in inner_hits:
                    record = self._record_from_item(item)
                    if record is not None:
                        yield record
                return

        record = self._record_from_item(payload)
        if record is not None:
            yield record

    @staticmethod
    def _record_from_item(item: object) -> dict[str, Any] | None:
        """Normalize a candidate item into a dataset dictionary.

        Parameters
        ----------
        item : object
            Candidate payload item.

        Returns
        -------
        dict of str to Any or None
            Dictionary data when available, otherwise ``None``.
        """
        if not isinstance(item, dict):
            return None
        source = item.get("_source")
        if isinstance(source, dict):
            return source
        return item

    @staticmethod
    def _dataset_id_from_payload(payload: dict[str, Any]) -> str:
        """Extract dataset identifier from SenNet payload.

        Parameters
        ----------
        payload : dict of str to Any
            Dataset summary or entity payload.

        Returns
        -------
        str
            ``sennet_id`` value or an empty string when unavailable.
        """
        value = payload.get("sennet_id")
        if isinstance(value, str) and value.strip():
            return value.strip()
        return ""

    def _dataset_title(
        self,
        summary_payload: dict[str, Any],
        entity_payload: dict[str, Any],
        dataset_id: str,
    ) -> str:
        """Resolve a user-facing dataset title from available metadata.

        Parameters
        ----------
        summary_payload : dict of str to Any
            Dataset summary record from search results.
        entity_payload : dict of str to Any
            Detailed entity payload for the dataset.
        dataset_id : str
            Fallback identifier used when no title-like fields are found.

        Returns
        -------
        str
            Title-like value suitable for UI display.
        """
        metadata = entity_payload.get("metadata")
        summary_metadata = summary_payload.get("metadata")
        if isinstance(metadata, dict):
            for key in ("title", "dataset_name", "description"):
                value = metadata.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        if isinstance(summary_metadata, dict):
            for key in ("title", "dataset_name", "description"):
                value = summary_metadata.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return dataset_id

    @staticmethod
    def _text_value(*values: object, default: str) -> str:
        """Return the first non-empty string from candidate values.

        Parameters
        ----------
        *values : object
            Candidate values to inspect.
        default : str
            Fallback value when no non-empty strings are present.

        Returns
        -------
        str
            First normalized non-empty string or ``default``.
        """
        for value in values:
            if isinstance(value, str) and value.strip():
                return value.strip()
        return default

    def _is_antibody_based_imaging(self, payload: dict[str, Any]) -> bool:
        """Check whether a record is tagged as antibody-based imaging.

        Parameters
        ----------
        payload : dict of str to Any
            Dataset summary payload from SenNet search endpoints.

        Returns
        -------
        bool
            ``True`` when ``dataset_type_hierarchy.first_level`` includes the
            literal SenNet first-level category ``"Antibody-based imaging"``.
        """
        hierarchy = payload.get("dataset_type_hierarchy")
        first_levels: list[str] = []
        if isinstance(hierarchy, dict):
            raw_first = hierarchy.get("first_level")
            if isinstance(raw_first, str):
                first_levels = [raw_first]
            elif isinstance(raw_first, list):
                first_levels = [str(value) for value in raw_first]
        elif isinstance(hierarchy, list):
            first_levels = [str(value) for value in hierarchy]

        target = self.ANTIBODY_FIRST_LEVEL.lower()
        return any(level.strip().lower() == target for level in first_levels)

    def _matches_requested_dataset_type(
        self,
        payload: dict[str, Any],
        requested_types: Sequence[str],
    ) -> bool:
        """Return whether payload dataset type is one of the requested types.

        Parameters
        ----------
        payload : dict of str to Any
            Dataset summary or entity payload.
        requested_types : sequence of str
            Dataset types requested by the caller.

        Returns
        -------
        bool
            ``True`` when payload dataset type is in requested types.
        """
        current = self._text_value(payload.get("dataset_type"), default="")
        requested = {str(name).strip() for name in requested_types if str(name).strip()}
        if not requested:
            return True
        return current in requested


__all__ = ["SenNetPortalMetadataMixin"]
