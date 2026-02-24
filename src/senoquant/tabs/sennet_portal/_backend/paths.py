"""Path extraction and normalization mixin for the SenNet Portal backend."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence
from urllib.parse import unquote, urlparse

from .models import SenNetDataset


class SenNetPortalPathMixin:
    """Mixin containing path extraction, normalization, and matching helpers."""

    def _extract_supported_paths(self, payload: object) -> list[str]:
        """Extract unique compatible file paths from arbitrary nested payloads.

        Parameters
        ----------
        payload : object
            Entity payload or nested structure containing file descriptors.

        Returns
        -------
        list of str
            Normalized dataset-relative file paths with supported extensions.
        """
        candidates = self._extract_candidate_paths(payload)
        supported: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            normalized = self._normalize_manifest_path(candidate)
            if not normalized:
                continue
            if self._matching_supported_extension(normalized) is None:
                continue
            if normalized in seen:
                continue
            seen.add(normalized)
            supported.append(normalized)
        return supported

    def _extract_candidate_paths(self, payload: object) -> list[str]:
        """Collect path-like string values from nested dictionaries/lists.

        Parameters
        ----------
        payload : object
            Nested payload to inspect recursively.

        Returns
        -------
        list of str
            Raw candidate path strings before extension filtering.
        """
        paths: list[str] = []

        def walk(value: object) -> None:
            """Recursively traverse nested values and collect path fields.

            Parameters
            ----------
            value : object
                Nested payload node being visited.

            Returns
            -------
            None
                Candidate paths are accumulated in outer-scope ``paths``.
            """
            if isinstance(value, dict):
                for key, child in value.items():
                    key_lower = str(key).strip().lower()
                    if key_lower in self._PATH_FIELD_NAMES and isinstance(child, str):
                        if self._looks_like_file_path(child):
                            paths.append(child)
                    walk(child)
                return
            if isinstance(value, list):
                for child in value:
                    walk(child)

        walk(payload)
        return paths

    def _looks_like_file_path(self, value: str) -> bool:
        """Heuristically determine whether text resembles a file path.

        Parameters
        ----------
        value : str
            Raw path-like value.

        Returns
        -------
        bool
            ``True`` when the value appears to reference a file path.
        """
        text = value.strip()
        if not text:
            return False
        path_text = self._extract_url_path(text)
        lowered = path_text.lower().rstrip("/")
        if any(lowered.endswith(ext) for ext in self._extension_check_order):
            return True
        if "/" in path_text or "\\" in path_text:
            return "." in Path(path_text).name
        return False

    @staticmethod
    def _extract_url_path(value: str) -> str:
        """Extract and decode path segment from URL-like values.

        Parameters
        ----------
        value : str
            URL or plain path string.

        Returns
        -------
        str
            Decoded URL path for HTTP(S) inputs, otherwise the original value.
        """
        parsed = urlparse(value)
        if parsed.scheme in {"http", "https"}:
            return unquote(parsed.path or "")
        return value

    def _normalize_manifest_path(self, value: str) -> str | None:
        """Normalize path text into SenNet manifest-compatible absolute form.

        Parameters
        ----------
        value : str
            Candidate path value from metadata.

        Returns
        -------
        str or None
            Normalized ``/``-prefixed path, or ``None`` if empty.
        """
        path_text = self._extract_url_path(value).strip()
        if not path_text:
            return None
        normalized = path_text.replace("\\", "/")
        if normalized.startswith("./"):
            normalized = normalized[1:]
        if not normalized.startswith("/"):
            normalized = f"/{normalized.lstrip('/')}"
        return normalized

    def _matching_supported_extension(self, path: str) -> str | None:
        """Return the supported extension that matches a path suffix.

        Parameters
        ----------
        path : str
            Candidate normalized file path.

        Returns
        -------
        str or None
            Matching extension or ``None`` if unsupported.
        """
        lowered = path.lower().rstrip("/")
        for ext in self._extension_check_order:
            if lowered.endswith(ext):
                return ext
        return None

    def _build_manifest_lines(self, datasets: Sequence[SenNetDataset]) -> list[str]:
        """Build unique SenNet CLT manifest lines for selected datasets.

        Parameters
        ----------
        datasets : sequence of SenNetDataset
            Selected datasets with compatible file paths.

        Returns
        -------
        list of str
            Manifest entries in ``<sennet_id> <path>`` format.
        """
        lines: list[str] = []
        seen: set[str] = set()
        for dataset in datasets:
            for path in dataset.compatible_paths:
                normalized_path = self._normalize_manifest_path(path)
                if not normalized_path:
                    continue
                line = f"{dataset.sennet_id} {normalized_path}"
                if line in seen:
                    continue
                seen.add(line)
                lines.append(line)
        return lines


__all__ = ["SenNetPortalPathMixin"]
