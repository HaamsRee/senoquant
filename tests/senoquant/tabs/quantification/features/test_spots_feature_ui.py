"""Tests for spots feature UI behavior."""

from __future__ import annotations

import types

from qtpy.QtWidgets import QComboBox

from tests.conftest import DummyLayout, DummyViewer, Labels
from senoquant.tabs.quantification.features.base import FeatureConfig
from senoquant.tabs.quantification.features.spots.config import (
    SpotsChannelConfig,
    SpotsFeatureData,
    SpotsSegmentationConfig,
)
from senoquant.tabs.quantification.features.spots.dialog import SpotsChannelsDialog
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


def test_spots_dialog_filters_labels_by_metadata_with_suffix_fallback() -> None:
    """Filter cellular/spots labels using metadata first."""
    viewer = DummyViewer(
        [
            Labels([[1]], "cell_from_metadata", metadata={"task": "nuclear"}),
            Labels([[1]], "spot_from_metadata", metadata={"task": "spots"}),
            Labels([[1]], "legacy_cyto_labels"),
            Labels([[1]], "legacy_spot_labels"),
            Labels([[1]], "misleading_spot_labels", metadata={"task": "cytoplasmic"}),
        ]
    )
    dialog = SpotsChannelsDialog.__new__(SpotsChannelsDialog)
    dialog._tab = types.SimpleNamespace(_viewer=viewer)

    cellular_combo = QComboBox()
    dialog._refresh_labels_combo(cellular_combo, filter_type="cellular")
    assert "cell_from_metadata" in cellular_combo._items
    assert "legacy_cyto_labels" in cellular_combo._items
    assert "spot_from_metadata" not in cellular_combo._items
    assert "misleading_spot_labels" in cellular_combo._items

    spots_combo = QComboBox()
    dialog._refresh_labels_combo(spots_combo, filter_type="spots")
    assert "spot_from_metadata" in spots_combo._items
    assert "legacy_spot_labels" in spots_combo._items
    assert "misleading_spot_labels" not in spots_combo._items
