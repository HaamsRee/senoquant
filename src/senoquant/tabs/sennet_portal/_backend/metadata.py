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

    @staticmethod
    def _dataset_uuid_from_payload(payload: dict[str, Any]) -> str:
        """Extract dataset UUID from SenNet payload when available.

        Parameters
        ----------
        payload : dict of str to Any
            Dataset summary or entity payload.

        Returns
        -------
        str
            UUID value or an empty string when unavailable.
        """
        value = payload.get("uuid")
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

    def _source_type_from_payload(self, payload: dict[str, Any]) -> str:
        """Extract source type from SenNet dataset payload schema.

        Parameters
        ----------
        payload : dict of str to Any
            Dataset summary payload from SenNet Search API.

        Returns
        -------
        str
            Source type value (for example, Human or Mouse), or ``"Unknown"``.

        Notes
        -----
        Live SenNet dataset records expose source type under
        ``sources[*].source_type``.
        """
        sources = payload.get("sources")
        if isinstance(sources, list):
            for source in sources:
                if isinstance(source, dict):
                    value = source.get("source_type")
                    if isinstance(value, str) and value.strip():
                        return value.strip()

        source = payload.get("source")
        if isinstance(source, dict):
            value = source.get("source_type")
            if isinstance(value, str) and value.strip():
                return value.strip()

        direct = payload.get("source_type")
        if isinstance(direct, str) and direct.strip():
            return direct.strip()
        return "Unknown"

    def _organ_from_payload(self, payload: dict[str, Any], *, token: str | None) -> str:
        """Extract organ and resolve UBERON IDs to SenNet organ terms.

        Parameters
        ----------
        payload : dict of str to Any
            Dataset summary payload from SenNet Search API.
        token : str or None
            Optional bearer token for ontology API requests.

        Returns
        -------
        str
            Organ term (for example, Pancreas), or ``"Unknown"``.

        Notes
        -----
        Live SenNet dataset records typically expose organ IDs under
        ``origin_samples[*].organ`` as UBERON IDs. This method resolves those
        IDs using the HuBMAP ontology endpoint configured for SenNet.
        """
        organ_uberon = self._organ_uberon_from_payload(payload)
        if not organ_uberon:
            return "Unknown"

        mapping = self._sennet_organs_lookup(token=token)
        mapped = mapping.get(organ_uberon)
        if mapped:
            return mapped

        fallback = self._organ_hierarchy_from_payload(payload)
        if fallback:
            return fallback
        return organ_uberon

    @staticmethod
    def _organ_uberon_from_payload(payload: dict[str, Any]) -> str:
        """Extract organ UBERON ID from SenNet dataset payload.

        Parameters
        ----------
        payload : dict of str to Any
            Dataset summary payload from SenNet Search API.

        Returns
        -------
        str
            UBERON identifier or empty string when unavailable.
        """
        origin_samples = payload.get("origin_samples")
        if isinstance(origin_samples, list):
            for sample in origin_samples:
                if isinstance(sample, dict):
                    value = sample.get("organ")
                    if isinstance(value, str) and value.strip():
                        return value.strip()

        direct = payload.get("organ")
        if isinstance(direct, str) and direct.strip():
            return direct.strip()
        return ""

    @staticmethod
    def _organ_hierarchy_from_payload(payload: dict[str, Any]) -> str:
        """Extract human-readable organ hierarchy string from payload.

        Parameters
        ----------
        payload : dict of str to Any
            Dataset summary payload from SenNet Search API.

        Returns
        -------
        str
            Organ hierarchy label or empty string when unavailable.
        """
        origin_samples = payload.get("origin_samples")
        if isinstance(origin_samples, list):
            for sample in origin_samples:
                if isinstance(sample, dict):
                    value = sample.get("organ_hierarchy")
                    if isinstance(value, str) and value.strip():
                        return value.strip()
        direct = payload.get("organ_hierarchy")
        if isinstance(direct, str) and direct.strip():
            return direct.strip()
        return ""

    def _sennet_organs_lookup(self, *, token: str | None) -> dict[str, str]:
        """Return cached mapping from UBERON IDs to SenNet organ terms.

        Parameters
        ----------
        token : str or None
            Optional bearer token for ontology API requests.

        Returns
        -------
        dict of str to str
            Mapping ``UBERON:... -> term`` for SenNet application context.
        """
        cached = getattr(self, "_organ_term_lookup_cache", None)
        if isinstance(cached, dict) and cached:
            return cached

        try:
            payload = self._fetch_json(
                self.ORGANS_API_URL,
                params={"application_context": "SENNET"},
                token=token,
            )
        except Exception:
            payload = []

        lookup: dict[str, str] = {}
        if isinstance(payload, list):
            for item in payload:
                if not isinstance(item, dict):
                    continue
                organ_uberon = item.get("organ_uberon")
                term = item.get("term")
                if isinstance(organ_uberon, str) and organ_uberon.strip():
                    if isinstance(term, str) and term.strip():
                        lookup[organ_uberon.strip()] = term.strip()

        self._organ_term_lookup_cache = lookup
        return lookup

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
