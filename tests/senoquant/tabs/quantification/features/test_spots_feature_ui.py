"""Tests for spots feature UI behavior."""

from __future__ import annotations

import types

from qtpy.QtWidgets import QComboBox

from tests.conftest import DummyLayout, DummyViewer, Image, Labels
from senoquant.tabs.quantification.features.base import FeatureConfig, RefreshingComboBox
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


def test_spots_dialog_auto_populate_button_enablement() -> None:
    """Enable auto-populate only when channel/segmentation is configured."""
    data = SpotsFeatureData()
    state = FeatureConfig(name="Spots", type_name="Spots", data=data)
    viewer = DummyViewer([Image([[1.0]], "img_a")])
    tab = types.SimpleNamespace(
        _viewer=viewer,
        _enable_rois=False,
        _configure_combo=lambda _combo: None,
    )
    feature = SpotsFeature(tab, DummyContext(state))
    dialog = SpotsChannelsDialog(feature)

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


def test_spots_dialog_auto_populates_channels_and_spot_layer_matches() -> None:
    """Auto-populate resolves names and matching spot-label layers."""
    data = SpotsFeatureData()
    state = FeatureConfig(name="Spots", type_name="Spots", data=data)
    viewer = DummyViewer(
        [
            Image(
                [[1.0]],
                "img_a",
                metadata={
                    "path": "/tmp/test.lif",
                    "scene_info": {"scene_index": 0},
                    "channel_index": 0,
                    "channel_names": ["DAPI", "TXR"],
                },
            ),
            Image(
                [[2.0]],
                "img_b",
                metadata={
                    "path": "/tmp/test.lif",
                    "scene_info": {"scene_index": 0},
                    "channel_index": 1,
                    "channel_names": ["DAPI", "TXR"],
                },
            ),
            Labels(
                [[1]],
                "img_a_spot_labels",
                metadata={
                    "task": "spots",
                    "path": "/tmp/test.lif",
                    "scene_info": {"scene_index": 0},
                    "channel_index": 0,
                },
            ),
            Labels(
                [[1]],
                "img_b_spot_labels",
                metadata={
                    "task": "spots",
                    "path": "/tmp/test.lif",
                    "scene_info": {"scene_index": 0},
                    "channel_index": 1,
                },
            ),
        ]
    )
    tab = types.SimpleNamespace(
        _viewer=viewer,
        _enable_rois=False,
        _configure_combo=lambda _combo: None,
    )
    feature = SpotsFeature(tab, DummyContext(state))
    dialog = SpotsChannelsDialog(feature)

    dialog._auto_populate_channels()

    channels_by_layer = {channel.channel: channel for channel in data.channels}
    assert set(channels_by_layer) == {"img_a", "img_b"}
    assert channels_by_layer["img_a"].name == "DAPI"
    assert channels_by_layer["img_a"].spots_segmentation == "img_a_spot_labels"
    assert channels_by_layer["img_b"].name == "TXR"
    assert channels_by_layer["img_b"].spots_segmentation == "img_b_spot_labels"

    dialog._auto_populate_channels()
    channels_by_layer = {channel.channel: channel for channel in data.channels}
    assert len(channels_by_layer) == 2


def test_spots_dialog_auto_populates_channels_without_spot_labels() -> None:
    """Auto-populate still adds channels/names when no spots labels exist."""
    data = SpotsFeatureData(segmentations=[SpotsSegmentationConfig(label="cells")])
    state = FeatureConfig(name="Spots", type_name="Spots", data=data)
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
        _configure_combo=lambda _combo: None,
    )
    feature = SpotsFeature(tab, DummyContext(state))
    dialog = SpotsChannelsDialog(feature)

    assert dialog._auto_populate_button.isEnabled() is True
    dialog._auto_populate_channels()

    channels_by_layer = {channel.channel: channel for channel in data.channels}
    assert set(channels_by_layer) == {"img_a", "img_b"}
    assert channels_by_layer["img_a"].name == "DAPI"
    assert channels_by_layer["img_a"].spots_segmentation == ""
    assert channels_by_layer["img_b"].name == "TXR"
    assert channels_by_layer["img_b"].spots_segmentation == ""


def test_spots_dialog_auto_populates_existing_empty_channel_combo() -> None:
    """Auto-populate assigns channel combo selection for existing empty rows."""
    data = SpotsFeatureData(
        segmentations=[SpotsSegmentationConfig(label="cells")],
        channels=[SpotsChannelConfig(name="", channel="", spots_segmentation="")],
    )
    state = FeatureConfig(name="Spots", type_name="Spots", data=data)
    viewer = DummyViewer(
        [
            Image(
                [[1.0]],
                "img_a",
                metadata={
                    "path": "/tmp/test.lif",
                    "scene_info": {"scene_index": 0},
                    "channel_index": 0,
                    "channel_names": ["DAPI", "TXR"],
                },
            ),
            Image(
                [[2.0]],
                "img_b",
                metadata={
                    "path": "/tmp/test.lif",
                    "scene_info": {"scene_index": 0},
                    "channel_index": 1,
                    "channel_names": ["DAPI", "TXR"],
                },
            ),
            Labels(
                [[1]],
                "img_a_spot_labels",
                metadata={
                    "task": "spots",
                    "path": "/tmp/test.lif",
                    "scene_info": {"scene_index": 0},
                    "channel_index": 0,
                },
            ),
            Labels(
                [[1]],
                "img_b_spot_labels",
                metadata={
                    "task": "spots",
                    "path": "/tmp/test.lif",
                    "scene_info": {"scene_index": 0},
                    "channel_index": 1,
                },
            ),
        ]
    )
    tab = types.SimpleNamespace(
        _viewer=viewer,
        _enable_rois=False,
        _configure_combo=lambda _combo: None,
    )
    feature = SpotsFeature(tab, DummyContext(state))
    dialog = SpotsChannelsDialog(feature)

    assert data.channels[0].channel == ""
    dialog._auto_populate_channels()

    assert data.channels[0].channel == "img_a"
    assert dialog._rows[0]._channel_combo.currentText() == "img_a"
    assert dialog._rows[0]._channel_combo.findText("img_a") != -1
    assert data.channels[0].name == "DAPI"
    assert data.channels[0].spots_segmentation == "img_a_spot_labels"
    assert dialog._rows[0]._segmentation_combo.findText("img_a_spot_labels") != -1
    channels_by_layer = {channel.channel: channel for channel in data.channels}
    assert set(channels_by_layer) == {"img_a", "img_b"}


def test_spots_dialog_preserves_channel_when_combo_rejects_unknown_text(
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

    data = SpotsFeatureData(
        channels=[
            SpotsChannelConfig(
                name="DAPI", channel="img_a", spots_segmentation="img_a_spot_labels"
            )
        ]
    )
    state = FeatureConfig(name="Spots", type_name="Spots", data=data)
    viewer = DummyViewer(
        [
            Image([[1.0]], "img_a"),
            Labels([[1]], "img_a_spot_labels", metadata={"task": "spots"}),
        ]
    )
    tab = types.SimpleNamespace(
        _viewer=viewer,
        _enable_rois=False,
        _configure_combo=lambda _combo: None,
    )
    feature = SpotsFeature(tab, DummyContext(state))
    dialog = SpotsChannelsDialog(feature)

    assert data.channels[0].channel == "img_a"
    assert dialog._rows[0]._channel_combo.currentText() == "img_a"
