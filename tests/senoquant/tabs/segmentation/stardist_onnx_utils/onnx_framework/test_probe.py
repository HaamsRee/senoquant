"""Tests for ONNX probe-shape helpers."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from senoquant.tabs.segmentation.stardist_onnx_utils.onnx_framework.inspect.probe import (
    make_probe_image,
)
from senoquant.tabs.segmentation.stardist_onnx_utils.onnx_framework.inspect.valid_sizes import (
    ValidSizePattern,
)


def test_make_probe_image_keeps_divisibility_when_patterns_are_loose(monkeypatch) -> None:
    """Ensure probe sizes remain divisible by div_by even after pattern snapping."""

    def _fake_patterns(_model_path, _input_layout, _ndim):
        return [
            ValidSizePattern(
                period=60,
                residues=(1, 2, 3, 4, 13, 14, 15, 16, 29, 30, 31, 32, 45, 46, 47, 48),
                min_valid=1,
            ),
            ValidSizePattern(
                period=60,
                residues=(1, 2, 3, 4, 13, 14, 15, 16, 29, 30, 31, 32, 45, 46, 47, 48),
                min_valid=1,
            ),
        ]

    monkeypatch.setattr(
        "senoquant.tabs.segmentation.stardist_onnx_utils.onnx_framework.inspect.probe.infer_valid_size_patterns_from_path",
        _fake_patterns,
    )
    monkeypatch.setattr(
        "senoquant.tabs.segmentation.stardist_onnx_utils.onnx_framework.inspect.probe.infer_div_by",
        lambda _path, ndim=None: (16,) * int(ndim or 2),
    )

    probe = make_probe_image(
        np.zeros((227, 303), dtype=np.float32),
        model_path=Path("dummy.onnx"),
        input_layout="NHWC",
    )

    assert probe.shape == (208, 256)
    assert probe.shape[0] % 16 == 0
    assert probe.shape[1] % 16 == 0
