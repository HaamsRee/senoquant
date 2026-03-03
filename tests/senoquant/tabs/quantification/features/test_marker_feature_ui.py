"""Tests for marker feature UI behavior."""

from __future__ import annotations

import types

import pytest
from qtpy.QtWidgets import QComboBox

from tests.conftest import DummyLayout, DummyViewer, Image, Labels
from senoquant.tabs.quantification.features.base import FeatureConfig, RefreshingComboBox
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
    assert button.text() == "Add channel(s)"

    data.channels.append(MarkerChannelConfig(name="Ch", channel="img"))
    data.segmentations.append(MarkerSegmentationConfig(label="cells"))
    feature._update_channels_button_label()
    assert button.text() == "Edit channel(s)"
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


def test_marker_dialog_auto_populate_button_enablement() -> None:
    """Enable auto-populate only when channel/segmentation is configured."""
    data = MarkerFeatureData()
    state = FeatureConfig(name="Markers", type_name="Markers", data=data)
    viewer = DummyViewer([Image([[1.0]], "img_a")])
    tab = types.SimpleNamespace(
        _viewer=viewer,
        _enable_rois=False,
        _enable_thresholds=False,
        _configure_combo=lambda _combo: None,
    )
    feature = MarkerFeature(tab, DummyContext(state))
    dialog = MarkerChannelsDialog(feature)

    assert dialog._auto_populate_button.isEnabled() is False

    dialog._add_channel()
    row = dialog._rows[-1]
    row._channel_combo.setCurrentText("img_a")
    assert dialog._auto_populate_button.isEnabled() is True

    row._channel_combo.setCurrentText("")
    assert dialog._auto_populate_button.isEnabled() is False

    dialog._add_segmentation()
    seg_row = dialog._segmentation_rows[-1]
    seg_row._labels_combo.setCurrentText("cells")
    assert dialog._auto_populate_button.isEnabled() is True


def test_marker_dialog_auto_populate_asserts_when_channel_row_missing() -> None:
    """Fail fast when channel configs and rows diverge."""
    data = MarkerFeatureData(channels=[MarkerChannelConfig(name="", channel="img_a")])
    state = FeatureConfig(name="Markers", type_name="Markers", data=data)
    viewer = DummyViewer([Image([[1.0]], "img_a"), Image([[2.0]], "img_b")])
    tab = types.SimpleNamespace(
        _viewer=viewer,
        _enable_rois=False,
        _enable_thresholds=False,
        _configure_combo=lambda _combo: None,
    )
    feature = MarkerFeature(tab, DummyContext(state))
    dialog = MarkerChannelsDialog(feature)

    data.channels.append(MarkerChannelConfig(name="", channel="img_b"))

    with pytest.raises(AssertionError, match="Invariant violated"):
        dialog._auto_populate_channels()


def test_marker_dialog_adds_distinct_blank_rows_to_state() -> None:
    """Keep multiple blank channel/segmentation rows in persisted state."""
    data = MarkerFeatureData()
    state = FeatureConfig(name="Markers", type_name="Markers", data=data)
    viewer = DummyViewer(
        [
            Image([[1.0]], "img_a"),
            Labels([[1]], "cells_nuc_labels"),
        ]
    )
    tab = types.SimpleNamespace(
        _viewer=viewer,
        _enable_rois=False,
        _enable_thresholds=False,
        _configure_combo=lambda _combo: None,
    )
    feature = MarkerFeature(tab, DummyContext(state))
    dialog = MarkerChannelsDialog(feature)

    dialog._add_channel()
    dialog._add_channel()
    assert len(dialog._rows) == 2
    assert len(data.channels) == 2
    assert data.channels[0] is dialog._rows[0].data
    assert data.channels[1] is dialog._rows[1].data
    assert data.channels[0] is not data.channels[1]

    dialog._rows[1]._name_input.setText("Second")
    assert data.channels[1].name == "Second"

    dialog._add_segmentation()
    dialog._add_segmentation()
    assert len(dialog._segmentation_rows) == 2
    assert len(data.segmentations) == 2
    assert data.segmentations[0] is dialog._segmentation_rows[0].data
    assert data.segmentations[1] is dialog._segmentation_rows[1].data
    assert data.segmentations[0] is not data.segmentations[1]

    dialog._segmentation_rows[1]._labels_combo.setCurrentText("cells_nuc_labels")
    assert data.segmentations[1].label == "cells_nuc_labels"


def test_marker_dialog_auto_populates_names_and_missing_rows() -> None:
    """Auto-populate fills names and adds missing channel rows."""
    data = MarkerFeatureData(
        channels=[MarkerChannelConfig(name="", channel="img_a")]
    )
    state = FeatureConfig(name="Markers", type_name="Markers", data=data)
    viewer = DummyViewer(
        [
            Image(
                [[1.0]],
                "img_a",
                metadata={"channel_names": ["DAPI", "TXR"], "channel_index": 0},
            ),
            Image(
                [[2.0]],
                "img_b",
                metadata={"channel_names": ["DAPI", "TXR"], "channel_index": 1},
            ),
        ]
    )
    tab = types.SimpleNamespace(
        _viewer=viewer,
        _enable_rois=False,
        _enable_thresholds=False,
        _configure_combo=lambda _combo: None,
    )
    feature = MarkerFeature(tab, DummyContext(state))
    dialog = MarkerChannelsDialog(feature)

    dialog._auto_populate_channels()

    channels_by_layer = {channel.channel: channel for channel in data.channels}
    assert set(channels_by_layer) == {"img_a", "img_b"}
    assert channels_by_layer["img_a"].name == "DAPI"
    assert channels_by_layer["img_b"].name == "TXR"

    dialog._auto_populate_channels()
    channels_by_layer = {channel.channel: channel for channel in data.channels}
    assert len(channels_by_layer) == 2
    assert channels_by_layer["img_a"].name == "DAPI"
    assert channels_by_layer["img_b"].name == "TXR"


def test_marker_dialog_auto_populates_existing_empty_channel_combo() -> None:
    """Auto-populate assigns layer selection for pre-existing empty rows."""
    data = MarkerFeatureData(
        segmentations=[MarkerSegmentationConfig(label="cells")],
        channels=[MarkerChannelConfig(name="", channel="")],
    )
    state = FeatureConfig(name="Markers", type_name="Markers", data=data)
    viewer = DummyViewer(
        [
            Image(
                [[1.0]],
                "img_a",
                metadata={"channel_names": ["DAPI", "TXR"], "channel_index": 0},
            ),
            Image(
                [[2.0]],
                "img_b",
                metadata={"channel_names": ["DAPI", "TXR"], "channel_index": 1},
            ),
        ]
    )
    tab = types.SimpleNamespace(
        _viewer=viewer,
        _enable_rois=False,
        _enable_thresholds=False,
        _configure_combo=lambda _combo: None,
    )
    feature = MarkerFeature(tab, DummyContext(state))
    dialog = MarkerChannelsDialog(feature)

    assert data.channels[0].channel == ""
    dialog._auto_populate_channels()

    assert data.channels[0].channel == "img_a"
    assert dialog._rows[0]._channel_combo.currentText() == "img_a"
    assert dialog._rows[0]._channel_combo.findText("img_a") != -1
    assert data.channels[0].name == "DAPI"
    channels_by_layer = {channel.channel: channel for channel in data.channels}
    assert set(channels_by_layer) == {"img_a", "img_b"}


def test_marker_dialog_preserves_channel_when_combo_rejects_unknown_text(
    monkeypatch,
) -> None:
    """Do not wipe stored channel during row init before combo items exist."""
    original_set_current_text = RefreshingComboBox.setCurrentText

    def strict_set_current_text(self, text: str) -> None:
        if text in getattr(self, "_items", []):
            original_set_current_text(self, text)
            return
        self._current_text = ""
        self.currentTextChanged.emit("")

    monkeypatch.setattr(
        RefreshingComboBox, "setCurrentText", strict_set_current_text
    )

    data = MarkerFeatureData(channels=[MarkerChannelConfig(name="DAPI", channel="img_a")])
    state = FeatureConfig(name="Markers", type_name="Markers", data=data)
    viewer = DummyViewer([Image([[1.0]], "img_a")])
    tab = types.SimpleNamespace(
        _viewer=viewer,
        _enable_rois=False,
        _enable_thresholds=False,
        _configure_combo=lambda _combo: None,
    )
    feature = MarkerFeature(tab, DummyContext(state))
    dialog = MarkerChannelsDialog(feature)

    assert data.channels[0].channel == "img_a"
    assert dialog._rows[0]._channel_combo.currentText() == "img_a"
