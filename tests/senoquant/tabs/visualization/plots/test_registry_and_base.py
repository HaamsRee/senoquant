"""Tests for visualization plot registry and base classes."""

from __future__ import annotations

import types

import pytest

from senoquant.tabs.visualization.plots import (
    _iter_subclasses,
    build_plot_data,
    get_feature_registry,
)
from senoquant.tabs.visualization.plots.base import (
    PlotConfig,
    PlotData,
    RefreshingComboBox,
    SenoQuantPlot,
)
from senoquant.tabs.visualization.plots.spatialplot import SpatialPlotData
from senoquant.tabs.visualization.plots.umap import UMAPData


def test_build_plot_data_known_and_unknown_types() -> None:
    """Build typed plot data for known keys and fallback for unknown."""
    assert isinstance(build_plot_data("UMAP"), UMAPData)
    assert isinstance(build_plot_data("Spatial Plot"), SpatialPlotData)
    assert isinstance(build_plot_data("Unknown Plot"), PlotData)


def test_feature_registry_contains_expected_types_in_order() -> None:
    """Discover plot handlers and preserve order metadata."""
    registry = get_feature_registry()
    assert list(registry.keys())[:3] == [
        "Spatial Plot",
        "UMAP",
        "Double Expression",
    ]


def test_iter_subclasses_recurses_and_skips_empty_feature_type() -> None:
    """Walk nested subclasses and ignore classes without feature_type."""

    class _NoTypePlot(SenoQuantPlot):
        pass

    class _NestedPlot(_NoTypePlot):
        feature_type = "Nested"
        order = 999

    all_subclasses = list(_iter_subclasses(SenoQuantPlot))
    assert _NoTypePlot in all_subclasses
    assert _NestedPlot in all_subclasses

    registry = get_feature_registry()
    assert "" not in registry
    assert "Nested" in registry


def test_base_plot_methods_and_refresh_combo(monkeypatch) -> None:
    """Exercise default base behavior and popup refresh callback."""
    context = types.SimpleNamespace(state=PlotConfig(type_name="Base"))
    base = SenoQuantPlot(types.SimpleNamespace(), context)

    with pytest.raises(NotImplementedError):
        base.build()

    assert list(base.plot(types.SimpleNamespace(), types.SimpleNamespace(), "png")) == []
    assert base.on_features_changed([]) is None
    assert base.update_type_options(types.SimpleNamespace(), []) is None

    popup_calls: list[bool] = []

    def _show_popup(self):
        self._popup_called = True

    monkeypatch.setattr(
        "senoquant.tabs.visualization.plots.base.QComboBox.showPopup",
        _show_popup,
        raising=False,
    )
    combo = RefreshingComboBox(refresh_callback=lambda: popup_calls.append(True))
    combo.showPopup()
    assert popup_calls == [True]
    assert getattr(combo, "_popup_called", False) is True
