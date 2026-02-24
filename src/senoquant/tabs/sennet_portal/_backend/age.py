"""Age estimation and normalization helpers for SenNet metadata payloads."""

from __future__ import annotations

from datetime import datetime
import re
from typing import Any, Iterable


class SenNetPortalAgeMixin:
    """Mixin containing best-effort sample age extraction helpers."""

    def _sample_age_from_payload(
        self,
        *,
        summary_payload: dict[str, Any],
        entity_payload: dict[str, Any],
        source_type: str,
    ) -> tuple[str, float | None, str]:
        """Estimate display age from mapped/source metadata.

        Parameters
        ----------
        summary_payload : dict of str to Any
            Dataset summary payload from Search API.
        entity_payload : dict of str to Any
            Dataset entity payload from Entity API.
        source_type : str
            Source type label used for unit preference.

        Returns
        -------
        tuple of (str, float or None, str)
            Display label, numeric value, and unit label. Units are normalized
            to years by default and months for mouse sources.
        """
        for payload in (entity_payload, summary_payload):
            for source in self._candidate_source_records(payload):
                years = self._source_age_years(source)
                if years is None:
                    continue
                unit = "months" if source_type.strip().lower() == "mouse" else "years"
                value = years * 12.0 if unit == "months" else years
                text = f"{self._format_number(value)} {unit}"
                return text, value, unit
        return "Unknown", None, ""

    @staticmethod
    def _candidate_source_records(payload: dict[str, Any]) -> Iterable[dict[str, Any]]:
        """Yield source-like records from dataset/entity payload."""
        sources = payload.get("sources")
        if isinstance(sources, list):
            for item in sources:
                if isinstance(item, dict):
                    yield item
        ancestors = payload.get("direct_ancestors")
        if isinstance(ancestors, list):
            for item in ancestors:
                if not isinstance(item, dict):
                    continue
                source = item.get("source")
                if isinstance(source, dict):
                    yield source

    def _source_age_years(self, source_payload: dict[str, Any]) -> float | None:
        """Extract source age estimate as years from one source payload."""
        mapped = source_payload.get("mapped_metadata")
        if isinstance(mapped, dict):
            age = mapped.get("age")
            years = self._age_value_to_years(age)
            if years is not None:
                return years

        metadata = source_payload.get("metadata")
        if isinstance(metadata, dict):
            lifespan = metadata.get("local_lifespan_data")
            years = self._age_value_to_years(lifespan)
            if years is not None:
                return years
            birth = metadata.get("date_of_birth_or_fertilization")
            death = metadata.get("date_of_death")
            return self._age_from_birth_death(birth, death)
        return None

    def _age_value_to_years(self, value: object) -> float | None:
        """Convert age-like metadata value to years."""
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, dict):
            unit = str(value.get("unit", "")).strip()
            raw_value = value.get("value")
            candidate: object = raw_value[0] if isinstance(raw_value, list) and raw_value else raw_value
            parsed = self._numeric_age(candidate)
            if parsed is None:
                parsed = self._numeric_age(value.get("value_display"))
            return self._convert_age_to_years(parsed, unit)
        if isinstance(value, str):
            parsed = self._numeric_age(value)
            unit = self._unit_from_text(value)
            return self._convert_age_to_years(parsed, unit)
        return None

    def _age_from_birth_death(self, birth: object, death: object) -> float | None:
        """Estimate age in years from date-of-birth and date-of-death strings."""
        if not isinstance(birth, str) or not isinstance(death, str):
            return None
        formats = ("%Y/%m/%d %I:%M:%S %p", "%Y-%m-%d")
        for date_format in formats:
            try:
                start = datetime.strptime(birth.strip(), date_format)
                end = datetime.strptime(death.strip(), date_format)
            except ValueError:
                continue
            days = abs((end - start).days)
            return days / 365.25
        return None

    @staticmethod
    def _numeric_age(value: object) -> float | None:
        """Extract first numeric token from a scalar value."""
        if isinstance(value, (int, float)):
            return float(value)
        if not isinstance(value, str):
            return None
        match = re.search(r"[-+]?\d*\.?\d+", value)
        if match is None:
            return None
        return float(match.group(0))

    @staticmethod
    def _unit_from_text(text: str) -> str:
        """Infer age unit token from free-text age values."""
        normalized = text.lower()
        for token in ("year", "yr", "month", "mo", "week", "day"):
            if token in normalized:
                return token
        return "year"

    @staticmethod
    def _convert_age_to_years(value: float | None, unit: str) -> float | None:
        """Convert one numeric age in arbitrary units to years."""
        if value is None:
            return None
        normalized = unit.lower().strip()
        if normalized.startswith(("month", "mo")):
            return value / 12.0
        if normalized.startswith("week"):
            return value / 52.1775
        if normalized.startswith("day"):
            return value / 365.25
        return value

    @staticmethod
    def _format_number(value: float) -> str:
        """Format age values with up to one decimal place."""
        return f"{value:.1f}".rstrip("0").rstrip(".")


__all__ = ["SenNetPortalAgeMixin"]
