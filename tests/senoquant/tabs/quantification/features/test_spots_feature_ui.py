"""Tests for spots feature UI behavior."""

from __future__ import annotations

import types

from tests.conftest import DummyLayout
from senoquant.tabs.quantification.features.base import FeatureConfig
from senoquant.tabs.quantification.features.spots.config import (
    SpotsChannelConfig,
    SpotsFeatureData,
    SpotsSegmentationConfig,
)
from senoquant.tabs.quantification.features.spots.feature import SpotsFeature


class DummyContext:
    """Feature context stub."""

    def __init__(self, state: FeatureConfig) -> None:
        self.state = state
        self.left_dynamic_layout = DummyLayout()


def test_spots_feature_build_and_toggle() -> None:
    """Build the feature UI and toggle colocalization.

    Returns
    -------
    None
    """
    data = SpotsFeatureData()
    state = FeatureConfig(name="Spots", type_name="Spots", data=data)
    tab = types.SimpleNamespace(_viewer=None, _enable_rois=False)
    feature = SpotsFeature(tab, DummyContext(state))

    feature.build()
    assert "channels_button" in feature._ui
    assert "colocalization_checkbox" in feature._ui

    feature._set_export_colocalization(True)
    assert data.export_colocalization is True

    feature._update_channels_button_label()
    button = feature._ui["channels_button"]
    assert button.text() == "Add channels"

    data.channels.append(
        SpotsChannelConfig(name="Ch1", channel="img", spots_segmentation="spots")
    )
    data.segmentations.append(SpotsSegmentationConfig(label="cells"))
    feature._update_channels_button_label()
    assert button.text() == "Edit channels"


def test_spots_feature_opens_dialog() -> None:
    """Create and show the channels dialog.

    Returns
    -------
    None
    """
    data = SpotsFeatureData()
    state = FeatureConfig(name="Spots", type_name="Spots", data=data)
    tab = types.SimpleNamespace(_viewer=None, _enable_rois=False)
    feature = SpotsFeature(tab, DummyContext(state))

    feature._open_channels_dialog()
    assert "channels_dialog" in feature._ui
