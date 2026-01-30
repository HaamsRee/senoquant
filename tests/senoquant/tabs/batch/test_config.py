"""Tests for batch configuration serialization.

Notes
-----
Ensures batch config dataclasses round-trip through JSON payloads.
"""

from __future__ import annotations

from senoquant.tabs.batch.config import (
    BatchChannelConfig,
    BatchJobConfig,
    BatchQuantificationConfig,
)
from senoquant.tabs.quantification.features.base import FeatureConfig
from senoquant.tabs.quantification.features.marker.config import (
    MarkerChannelConfig,
    MarkerFeatureData,
    MarkerSegmentationConfig,
)
from senoquant.tabs.quantification.features.spots.config import (
    SpotsChannelConfig,
    SpotsFeatureData,
    SpotsSegmentationConfig,
)


def test_batch_job_config_round_trip(tmp_path) -> None:
    """Round-trip serialize/deserialize batch config.

    Returns
    -------
    None
    """
    marker_data = MarkerFeatureData(
        segmentations=[MarkerSegmentationConfig(label="cells")],
        channels=[MarkerChannelConfig(name="DAPI", channel="nuclei")],
    )
    spots_data = SpotsFeatureData(
        segmentations=[SpotsSegmentationConfig(label="cells")],
        channels=[SpotsChannelConfig(name="Spot", channel="spot", spots_segmentation="spots")],
        export_colocalization=True,
    )
    features = [
        FeatureConfig(
            feature_id="marker-1",
            name="Markers",
            type_name="Markers",
            data=marker_data,
        ),
        FeatureConfig(
            feature_id="spots-1",
            name="Spots",
            type_name="Spots",
            data=spots_data,
        ),
    ]
    job = BatchJobConfig(
        input_path="/input",
        output_path="/output",
        channel_map=[BatchChannelConfig(name="DAPI", index=0)],
        quantification=BatchQuantificationConfig(enabled=True, features=features),
    )

    payload = job.to_dict()
    restored = BatchJobConfig.from_dict(payload)

    assert restored.input_path == "/input"
    assert restored.output_path == "/output"
    assert restored.channel_map[0].name == "DAPI"
    assert restored.quantification.features[0].feature_id == "marker-1"

    save_path = tmp_path / "job.json"
    job.save(str(save_path))
    loaded = BatchJobConfig.load(str(save_path))
    assert loaded.quantification.enabled is True

def test_batch_channel_config_basic() -> None:
    """Test BatchChannelConfig creation and access.

    Returns
    -------
    None
    """
    config = BatchChannelConfig(name="DAPI", index=0)
    assert config.name == "DAPI"
    assert config.index == 0


def test_batch_job_config_defaults() -> None:
    """Test BatchJobConfig with default values.

    Returns
    -------
    None
    """
    config = BatchJobConfig()
    assert config.input_path == ""
    assert config.output_path == ""
    assert config.extensions == []
    assert config.include_subfolders is False
    assert config.overwrite is False
    assert config.nuclear.enabled is False
    assert config.cytoplasmic.enabled is False
    assert config.spots.enabled is False


def test_batch_job_config_multiple_extensions() -> None:
    """Test BatchJobConfig with multiple file extensions.

    Returns
    -------
    None
    """
    config = BatchJobConfig(
        input_path="/data",
        output_path="/results",
        extensions=["tif", "lif", "nd2"],
    )
    assert len(config.extensions) == 3
    assert "tif" in config.extensions


def test_batch_job_config_with_nuclear_segmentation() -> None:
    """Test BatchJobConfig with nuclear segmentation enabled.

    Returns
    -------
    None
    """
    from senoquant.tabs.batch.config import BatchSegmentationConfig

    config = BatchJobConfig(
        nuclear=BatchSegmentationConfig(
            enabled=True,
            model="default_2d",
            channel="DAPI",
            settings={"min_score_threshold": 0.5},
        ),
    )
    assert config.nuclear.enabled is True
    assert config.nuclear.model == "default_2d"
    assert config.nuclear.settings["min_score_threshold"] == 0.5


def test_batch_job_config_with_cyto_segmentation() -> None:
    """Test BatchJobConfig with cytoplasmic segmentation enabled.

    Returns
    -------
    None
    """
    from senoquant.tabs.batch.config import BatchCytoplasmicConfig

    config = BatchJobConfig(
        cytoplasmic=BatchCytoplasmicConfig(
            enabled=True,
            model="nuclear_dilation",
            channel="GFP",
            nuclear_channel="DAPI",
        ),
    )
    assert config.cytoplasmic.enabled is True
    assert config.cytoplasmic.model == "nuclear_dilation"
    assert config.cytoplasmic.nuclear_channel == "DAPI"


def test_batch_job_config_with_spots() -> None:
    """Test BatchJobConfig with spot detection enabled.

    Returns
    -------
    None
    """
    from senoquant.tabs.batch.config import BatchSpotsConfig

    config = BatchJobConfig(
        spots=BatchSpotsConfig(
            enabled=True,
            detector="udwt",
            channels=["RFP", "Cy5"],
        ),
    )
    assert config.spots.enabled is True
    assert config.spots.detector == "udwt"
    assert len(config.spots.channels) == 2