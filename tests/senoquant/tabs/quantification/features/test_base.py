"""Tests for quantification feature base classes."""

from __future__ import annotations

from pathlib import Path
import types

import pytest

from senoquant.tabs.quantification.features.base import (
    FeatureConfig,
    RefreshingComboBox,
    SenoQuantFeature,
)


def test_quant_feature_base_default_methods() -> None:
    """Exercise default no-op/abstract base hooks."""
    context = types.SimpleNamespace(state=FeatureConfig(type_name="Base"))
    feature = SenoQuantFeature(tab=types.SimpleNamespace(), context=context)

    with pytest.raises(NotImplementedError):
        feature.build()

    assert list(feature.export(Path("/tmp"), "csv")) == []
    assert feature.on_features_changed([]) is None
    assert feature.update_type_options(types.SimpleNamespace(), []) is None


def test_quant_feature_refreshing_combo_refreshes_before_popup(monkeypatch) -> None:
    """Invoke refresh callback before forwarding popup display."""
    popup_calls: list[bool] = []

    def _show_popup(self):
        self._popup_called = True

    monkeypatch.setattr(
        "senoquant.tabs.quantification.features.base.QComboBox.showPopup",
        _show_popup,
        raising=False,
    )

    combo = RefreshingComboBox(refresh_callback=lambda: popup_calls.append(True))
    combo.showPopup()
    assert popup_calls == [True]
    assert getattr(combo, "_popup_called", False) is True

    combo_without_refresh = RefreshingComboBox(refresh_callback=None)
    combo_without_refresh.showPopup()
    assert getattr(combo_without_refresh, "_popup_called", False) is True
