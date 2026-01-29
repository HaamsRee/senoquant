"""Tests for quantification feature registry discovery.

Notes
-----
Validates that feature classes are discoverable and data factories work.
"""

from __future__ import annotations

from senoquant.tabs.quantification.features import build_feature_data, get_feature_registry


def test_get_feature_registry_contains_known_features() -> None:
    """Discover known feature types.

    Returns
    -------
    None
    """
    registry = get_feature_registry()
    assert "Markers" in registry
    assert "Spots" in registry


def test_build_feature_data_defaults() -> None:
    """Build feature data instances from names.

    Returns
    -------
    None
    """
    markers = build_feature_data("Markers")
    spots = build_feature_data("Spots")
    assert markers.__class__.__name__.endswith("MarkerFeatureData")
    assert spots.__class__.__name__.endswith("SpotsFeatureData")
