"""Tests for batch spot size filtering."""

from senoquant.tabs.batch.config import (
    BatchJobConfig,
    BatchSpotsConfig,
)


def test_batch_config_serialization_with_spot_filters() -> None:
    """Test that spot size filters are correctly serialized/deserialized."""
    job = BatchJobConfig(
        input_path="/test/input",
        output_path="/test/output",
        spots=BatchSpotsConfig(
            enabled=True,
            detector="ufish",
            channels=["DAPI"],
            settings={"threshold": 0.5},
            min_size=10,
            max_size=500,
        ),
    )

    # Serialize to dict
    config_dict = job.to_dict()
    assert config_dict["spots"]["min_size"] == 10
    assert config_dict["spots"]["max_size"] == 500

    # Deserialize back
    restored = BatchJobConfig.from_dict(config_dict)
    assert restored.spots.min_size == 10
    assert restored.spots.max_size == 500


def test_batch_spots_config_defaults() -> None:
    """Test default values for spot size filters."""
    config = BatchSpotsConfig()
    assert config.min_size == 0
    assert config.max_size == 0
    assert not config.enabled


def test_batch_spots_config_with_filters() -> None:
    """Test creating BatchSpotsConfig with size filters."""
    config = BatchSpotsConfig(
        enabled=True,
        detector="ufish",
        channels=["Channel 0", "Channel 1"],
        settings={"threshold": 0.5},
        min_size=5,
        max_size=100,
    )
    assert config.enabled
    assert config.detector == "ufish"
    assert config.channels == ["Channel 0", "Channel 1"]
    assert config.settings == {"threshold": 0.5}
    assert config.min_size == 5
    assert config.max_size == 100
