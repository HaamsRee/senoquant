"""Shared helpers for app-owned output naming."""

from __future__ import annotations

import re
from typing import Iterable

from pathvalidate import sanitize_filename

_SEPARATOR_RE = re.compile(r"[\s\-]+")
_NON_TOKEN_RE = re.compile(r"[^\w]+", flags=re.UNICODE)
_UNDERSCORE_RE = re.compile(r"_+")


def sanitize_name_token(value: object | None, *, fallback: str = "item") -> str:
    """Return a filesystem- and header-safe token for generated names."""

    raw = "" if value is None else str(value)
    normalized = _normalize_token(raw)
    if normalized:
        return normalized

    fallback_token = _normalize_token(fallback)
    return fallback_token or "item"


def assign_unique_name_tokens(
    values: Iterable[object | None], *, fallback: str = "item"
) -> list[str]:
    """Return deterministic unique tokens for sibling names."""

    tokens: list[str] = []
    used: set[str] = set()
    next_suffix: dict[str, int] = {}
    for value in values:
        base = sanitize_name_token(value, fallback=fallback)
        token = base
        suffix = next_suffix.get(base, 2)
        while token in used:
            token = f"{base}__{suffix}"
            suffix += 1
        next_suffix[base] = suffix
        used.add(token)
        tokens.append(token)
    return tokens


def build_name_token_map(
    values: Iterable[object | None], *, fallback: str = "item"
) -> dict[str, str]:
    """Return a stable token map for unique raw values in encounter order."""

    unique_values: list[str] = []
    seen: set[str] = set()
    for value in values:
        raw = "" if value is None else str(value)
        if raw in seen:
            continue
        seen.add(raw)
        unique_values.append(raw)
    tokens = assign_unique_name_tokens(unique_values, fallback=fallback)
    return dict(zip(unique_values, tokens, strict=True))


def _normalize_token(value: str) -> str:
    sanitized = sanitize_filename(
        value.strip(),
        replacement_text="_",
        platform="universal",
    )
    sanitized = _SEPARATOR_RE.sub("_", sanitized)
    sanitized = _NON_TOKEN_RE.sub("_", sanitized)
    sanitized = _UNDERSCORE_RE.sub("_", sanitized)
    return sanitized.strip("_")
