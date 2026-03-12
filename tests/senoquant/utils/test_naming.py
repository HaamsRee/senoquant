"""Tests for shared naming helpers."""

from __future__ import annotations

from senoquant.utils.naming import (
    assign_unique_name_tokens,
    build_name_token_map,
    sanitize_name_token,
)


def test_sanitize_name_token_normalizes_invalid_chars() -> None:
    """Normalize separators and invalid characters while preserving case."""

    assert sanitize_name_token("Type / With Symbols") == "Type_With_Symbols"


def test_sanitize_name_token_uses_fallback_for_blank_values() -> None:
    """Use the provided fallback when the input collapses to an empty token."""

    assert sanitize_name_token("   ", fallback="scene") == "scene"


def test_assign_unique_name_tokens_deduplicates_collisions() -> None:
    """Append deterministic suffixes when sibling tokens collide."""

    assert assign_unique_name_tokens(["A/A", "A A", "A-A"]) == [
        "A_A",
        "A_A__2",
        "A_A__3",
    ]


def test_build_name_token_map_reuses_first_token_for_duplicate_raw_values() -> None:
    """Keep duplicate raw names mapped to the first resolved token."""

    assert build_name_token_map(["A/A", "A A", "A/A"]) == {
        "A/A": "A_A",
        "A A": "A_A__2",
    }
