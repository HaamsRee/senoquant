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
