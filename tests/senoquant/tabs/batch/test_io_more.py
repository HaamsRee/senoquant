"""Extra tests for batch io helpers."""

from __future__ import annotations

import types

import numpy as np

from senoquant.tabs.batch import io as batch_io
from senoquant.tabs.batch.config import BatchChannelConfig


def test_sanitize_label_strips_symbols() -> None:
    """Sanitize label strings for filesystem use.

    Returns
    -------
    None
    """
    assert batch_io.sanitize_label(" A/B ") == "A_B"
    assert batch_io.sanitize_label("***") == "spots"


def test_spot_label_name_numeric_string() -> None:
    """Return numeric suffix for numeric channel names.

    Returns
    -------
    None
    """
    channel_map = [BatchChannelConfig(name="1", index=0)]
    assert batch_io.spot_label_name("1", channel_map) == "spot_labels_1"


def test_load_channel_data_raises_on_bad_index(monkeypatch, tmp_path) -> None:
    """Raise when channel index is out of range.

    Returns
    -------
    None
    """
    class DummyDims:
        def __init__(self) -> None:
            self.C = 1
            self.Z = 1
            self.T = 1

    class DummyImage:
        def __init__(self) -> None:
            self.dims = DummyDims()
            self.scenes = []
            self.physical_pixel_sizes = types.SimpleNamespace(Z=1.0, Y=1.0, X=1.0)

        def get_image_data(self, _order, **_kwargs):
            return np.zeros((4, 4), dtype=np.uint8)

        def close(self):
            return None

    monkeypatch.setattr(batch_io.reader_core, "_open_bioimage", lambda _p: DummyImage())
    try:
        batch_io.load_channel_data(tmp_path / "file.tif", 3, None)
    except ValueError as exc:
        assert "out of range" in str(exc)
