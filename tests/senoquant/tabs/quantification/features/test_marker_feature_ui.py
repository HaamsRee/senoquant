"""Tests for marker feature UI behavior."""

from __future__ import annotations

import types

from qtpy.QtWidgets import QComboBox

from tests.conftest import DummyLayout, DummyViewer, Image, Labels
from senoquant.tabs.quantification.features.base import FeatureConfig
from senoquant.tabs.quantification.features.marker.config import (
    MarkerChannelConfig,
    MarkerFeatureData,
    MarkerSegmentationConfig,
)
from senoquant.tabs.quantification.features.marker.dialog import MarkerChannelsDialog
from senoquant.tabs.quantification.features.marker.feature import MarkerFeature


class DummyContext:
    """Feature context stub."""

    def __init__(self, state: FeatureConfig) -> None:
        self.state = state
        self.left_dynamic_layout = DummyLayout()


def test_marker_feature_build_and_label_updates() -> None:
    """Build the feature UI and update button labels.

    Returns
    -------
    None
    """
    data = MarkerFeatureData()
    state = FeatureConfig(name="Markers", type_name="Markers", data=data)
    viewer = DummyViewer([Image([[1.0]], "img")])
    tab = types.SimpleNamespace(_viewer=viewer, _enable_rois=False)
    feature = MarkerFeature(tab, DummyContext(state))

    feature.build()
    assert "channels_button" in feature._ui

    feature._update_channels_button_label()
    button = feature._ui["channels_button"]
    assert button.text() == "Add channels"

    data.channels.append(MarkerChannelConfig(name="Ch", channel="img"))
    data.segmentations.append(MarkerSegmentationConfig(label="cells"))
    feature._update_channels_button_label()
    assert button.text() == "Edit channels"
    assert feature._get_image_layer_by_name("img") is not None


def test_marker_feature_opens_dialog() -> None:
    """Create and show the channels dialog.

    Returns
    -------
    None
    """
    data = MarkerFeatureData()
    state = FeatureConfig(name="Markers", type_name="Markers", data=data)
    tab = types.SimpleNamespace(_viewer=None, _enable_rois=False)
    feature = MarkerFeature(tab, DummyContext(state))

    feature._open_channels_dialog()
    assert "channels_dialog" in feature._ui


def test_marker_dialog_filters_labels_by_metadata_with_suffix_fallback() -> None:
    """Filter marker segmentation labels using metadata first."""
    viewer = DummyViewer(
        [
            Labels([[1]], "cell_from_metadata", metadata={"task": "cytoplasmic"}),
            Labels([[1]], "legacy_nuc_labels"),
            Labels([[1]], "misleading_nuc_labels", metadata={"task": "spots"}),
            Labels([[1]], "spot_layer", metadata={"task": "spots"}),
        ]
    )
    dialog = MarkerChannelsDialog.__new__(MarkerChannelsDialog)
    dialog._tab = types.SimpleNamespace(_viewer=viewer)
    combo = QComboBox()

    dialog._refresh_labels_combo(combo)

    assert "cell_from_metadata" in combo._items
    assert "legacy_nuc_labels" in combo._items
    assert "misleading_nuc_labels" not in combo._items
    assert "spot_layer" not in combo._items
