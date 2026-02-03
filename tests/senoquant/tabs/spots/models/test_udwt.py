"""Tests for the UDWT spot detector.

Notes
-----
Focuses on wavelet utility helpers and detector outputs.
"""

from __future__ import annotations

import numpy as np
import pytest

from senoquant.tabs.spots.models.udwt import model as udwt


class DummyLayer:
    """Layer stub with data and rgb flag."""

    def __init__(self, data, rgb: bool = False) -> None:
        self.data = data
        self.rgb = rgb


def test_min_size_computation() -> None:
    """Compute minimum size per dimension.

    Returns
    -------
    None
    """
    assert udwt._min_size(1) == 9
    assert udwt._min_size(2) == 13


def test_ensure_min_size_raises() -> None:
    """Raise when image is too small.

    Returns
    -------
    None
    """
    with pytest.raises(ValueError):
        udwt._ensure_min_size((4, 4), 1)


def test_b3_kernel_base_step() -> None:
    """Return the base kernel for step 1.

    Returns
    -------
    None
    """
    kernel = udwt._b3_kernel(1)
    assert np.allclose(kernel, udwt.BASE_KERNEL)


def test_wavelet_planes_shape() -> None:
    """Compute wavelet planes for simple input.

    Returns
    -------
    None
    """
    image = np.ones((5, 5), dtype=np.float32)
    scales = udwt._atrous_smoothing_scales(image, 1)
    planes = udwt._wavelet_planes(image, scales)
    assert len(planes) == 1
    assert planes[0].shape == image.shape


def test_multiscale_product_requires_planes() -> None:
    """Raise when planes list is empty.

    Returns
    -------
    None
    """
    with pytest.raises(ValueError):
        udwt._multiscale_product([])


def test_detect_2d_returns_labels() -> None:
    """Detect spots on a synthetic 2D image.

    Returns
    -------
    None
    """
    image = np.zeros((9, 9), dtype=np.float32)
    image[4, 4] = 10.0
    params = udwt._Params(num_scales=1, ld=0.0, scale_enabled=(True,), scale_sensitivity=(100.0,))
    labels = udwt._detect_2d(image, params)
    assert labels.shape == image.shape
    assert labels.dtype == np.int32


def test_watershed_instances_splits_touching_regions() -> None:
    """Split a single connected region into multiple instances."""
    binary = np.zeros((11, 11), dtype=bool)
    binary[2:9, 2:5] = True
    binary[2:9, 6:9] = True
    binary[5, 5] = True  # thin bridge so CC sees one object

    cc_labels = udwt._binary_to_instances(binary, connectivity=2)
    ws_labels = udwt._watershed_instances(binary, min_distance=1, connectivity=2)

    assert cc_labels.max() == 1
    assert ws_labels.max() >= 2
    assert ws_labels.dtype == np.int32


def test_watershed_instances_empty_mask() -> None:
    """Return all-zero labels for empty masks."""
    binary = np.zeros((7, 7), dtype=bool)
    labels = udwt._watershed_instances(binary, min_distance=1, connectivity=2)
    assert labels.shape == binary.shape
    assert labels.dtype == np.int32
    assert int(labels.max()) == 0


def test_detector_rejects_rgb() -> None:
    """Reject RGB layers.

    Returns
    -------
    None
    """
    detector = udwt.UDWTDetector()
    with pytest.raises(ValueError):
        detector.run(layer=DummyLayer(np.zeros((5, 5, 3)), rgb=True))


def test_detector_force_2d_stack() -> None:
    """Run 2D per-slice detection on a 3D stack.

    Returns
    -------
    None
    """
    detector = udwt.UDWTDetector()
    data = np.zeros((3, 9, 9), dtype=np.float32)
    data[:, 4, 4] = 10.0
    result = detector.run(
        layer=DummyLayer(data),
        settings={
            "force_2d": True,
            "ld": 0.0,
            "scale_2_enabled": False,
            "scale_3_enabled": False,
        },
    )
    assert result["mask"].shape == data.shape
