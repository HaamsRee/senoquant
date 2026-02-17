"""Tests for prediction model base class defaults."""

from __future__ import annotations

from pathlib import Path

import pytest

from senoquant.tabs.prediction.models.base import SenoQuantPredictionModel


def test_prediction_model_base_rejects_empty_name(tmp_path: Path) -> None:
    """Require non-empty model names."""
    with pytest.raises(ValueError, match="non-empty"):
        SenoQuantPredictionModel("", models_root=tmp_path)


def test_prediction_model_base_default_hooks_and_paths(tmp_path: Path) -> None:
    """Expose default behavior for optional hooks and path helpers."""
    model = SenoQuantPredictionModel("demo", models_root=tmp_path)

    assert model.class_path == tmp_path / "demo" / "model.py"
    assert model.display_order() is None
    assert model.build_widget(parent=None, viewer=None) is None
    assert model.collect_widget_settings(settings_widget=None) == {}

    with pytest.raises(NotImplementedError, match="not implemented"):
        model.run()
