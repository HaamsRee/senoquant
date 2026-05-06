"""Tests for the RMP spot detector helpers.

Notes
-----
Exercises normalization, padding, and marker/segmentation helpers.
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy import ndimage as ndi

from senoquant.tabs.spots.models.rmp import model as rmp
from senoquant.tabs.spots.models.rmp import anisotropy as rmp_anisotropy
from senoquant.tabs.spots.models.rmp import markers as rmp_markers


class DummyLayer:
    """Layer stub with data and rgb flag."""

    def __init__(self, data, rgb: bool = False) -> None:
        self.data = data
        self.rgb = rgb


def test_normalize_image_constant() -> None:
    """Normalize constant image to zeros.

    Returns
    -------
    None
    """
    data = np.ones((4, 4), dtype=np.float32)
    normalized = rmp._normalize_image(data)
    assert np.allclose(normalized, 0.0)


def test_pad_tensor_for_rotation_grows_canvas() -> None:
    """Pad tensor so rotations keep content."""
    data = np.zeros((4, 6), dtype=np.float32)
    device = rmp._torch_device()
    tensor = rmp._to_image_tensor(data, device=device)
    padded, (pad_y, pad_x) = rmp._pad_tensor_for_rotation(tensor)
    assert int(padded.shape[-2]) >= data.shape[0]
    assert int(padded.shape[-1]) >= data.shape[1]
    assert pad_y >= 0 and pad_x >= 0


def test_pad_xy_to_chunk_multiple_pads_2d_and_restores_with_crop() -> None:
    """Pad 2D image to chunk multiples and allow exact crop-back."""
    data = np.arange(35, dtype=np.float32).reshape(5, 7)

    padded, crop_slices = rmp._pad_xy_to_chunk_multiple(
        data,
        chunk_size=(4, 4),
    )

    assert padded.shape == (8, 8)
    restored = padded[crop_slices]
    assert restored.shape == data.shape
    assert np.array_equal(restored, data)


def test_pad_xy_to_chunk_multiple_pads_3d_xy_only() -> None:
    """Pad 3D stack along trailing Y/X axes only."""
    data = np.arange(3 * 5 * 7, dtype=np.float32).reshape(3, 5, 7)

    padded, crop_slices = rmp._pad_xy_to_chunk_multiple(
        data,
        chunk_size=(4, 4),
    )

    assert padded.shape == (3, 8, 8)
    restored = padded[crop_slices]
    assert restored.shape == data.shape
    assert np.array_equal(restored, data)


def test_markers_from_local_maxima_empty() -> None:
    """Return empty markers when no local maxima cross threshold."""
    enhanced = np.zeros((4, 4), dtype=np.float32)
    markers = rmp._markers_from_local_maxima(enhanced, threshold=0.5)
    assert markers.shape == enhanced.shape
    assert markers.max() == 0


def test_markers_from_local_maxima_filters_low_relative_intensity() -> None:
    """Reject weak peaks when their intensity is too low relative to the image."""
    enhanced = np.zeros((9, 9), dtype=np.float32)
    enhanced[2, 2] = 1.0
    enhanced[6, 6] = 0.06

    markers = rmp._markers_from_local_maxima(enhanced, threshold=0.05)

    assert markers[2, 2] > 0
    assert markers[6, 6] == 0
    assert markers.max() == 1


def test_markers_from_local_maxima_filters_low_relative_prominence() -> None:
    """Reject peaks that are bright but not sufficiently prominent locally."""
    enhanced = np.zeros((11, 11), dtype=np.float32)
    enhanced[2, 2] = 1.0
    enhanced[6:9, 6:9] = 0.92
    enhanced[7, 7] = 1.0

    markers = rmp._markers_from_local_maxima(enhanced, threshold=0.5)

    assert markers[2, 2] > 0
    assert markers[7, 7] == 0
    assert markers.max() == 1


def test_markers_from_local_maxima_prefers_component_center() -> None:
    """Reject boundary peak in favor of component-centered peak."""
    enhanced = np.zeros((15, 15), dtype=np.float32)
    enhanced[4:11, 4:11] = 0.7
    enhanced[7, 7] = 1.2
    enhanced[4, 7] = 1.0

    markers = rmp._markers_from_local_maxima(enhanced, threshold=0.6)

    assert markers[7, 7] > 0
    assert markers[4, 7] == 0
    assert markers.max() == 1


def test_markers_from_local_maxima_uses_reference_image_for_peak_scoring() -> None:
    """Score local maxima from reference values while masking by enhanced threshold."""
    enhanced = np.zeros((11, 11), dtype=np.float32)
    enhanced[3:8, 3:8] = 0.7
    enhanced[5, 4] = 1.0
    enhanced[5, 6] = 1.0

    reference = np.zeros_like(enhanced)
    reference[3:8, 3:8] = 0.4
    reference[5, 4] = 0.25
    reference[5, 6] = 1.0

    markers = rmp._markers_from_local_maxima(
        enhanced,
        threshold=0.6,
        reference_image=reference,
    )

    assert markers[5, 6] > 0
    assert markers[5, 4] == 0


def test_local_edt_matches_full_volume_component_distance() -> None:
    """Local component EDT should match full-volume normalized component distance."""
    foreground = np.zeros((6, 8, 9), dtype=bool)
    foreground[0:3, 1:4, 2:5] = True
    foreground[3:6, 5:8, 6:9] = True
    valid_component_mask = foreground.copy()
    valid_component_mask[1, 2, 3] = False

    structure = ndi.generate_binary_structure(3, 1)
    component_labels, num_components = ndi.label(foreground, structure=structure)
    distance_to_boundary = ndi.distance_transform_edt(foreground)
    label_ids = np.arange(num_components + 1, dtype=np.int32)
    max_distance_by_label = np.asarray(
        ndi.maximum(
            distance_to_boundary,
            labels=component_labels,
            index=label_ids,
        ),
        dtype=np.float32,
    )
    component_scale = max_distance_by_label[component_labels]
    expected = np.zeros(foreground.shape, dtype=np.float32)
    expected[valid_component_mask] = (
        distance_to_boundary[valid_component_mask]
        / np.maximum(component_scale[valid_component_mask], rmp_markers.EPS)
    )

    actual = rmp_markers._normalized_component_distance_local_edt(
        component_labels,
        valid_component_mask,
    )

    assert np.allclose(actual, expected)


def test_local_minimum_at_coords_matches_minimum_filter() -> None:
    """Coordinate-local minima should match a 3-pixel nearest-mode minimum filter."""
    image = np.arange(3 * 5 * 6, dtype=np.float32).reshape(3, 5, 6)
    image[1, 2, 3] = -5.0
    coords = np.asarray(
        [
            [0, 0, 0],
            [1, 2, 3],
            [2, 4, 5],
        ],
        dtype=np.int64,
    )
    expected = ndi.minimum_filter(image, size=3, mode="nearest")[tuple(coords.T)]

    actual = rmp_markers._local_minimum_at_coords(image, coords)

    assert np.allclose(actual, expected)


def test_estimate_apparent_z_anisotropy_ratio_detects_elongation() -> None:
    """Estimate anisotropy ratio > 1 for clearly z-elongated synthetic spots."""
    shape = (28, 48, 48)
    zz, yy, xx = np.indices(shape, dtype=np.float32)
    volume = np.zeros(shape, dtype=np.float32)
    centers = [(7, 12, 12), (7, 12, 36), (7, 36, 24),
               (14, 12, 24), (14, 24, 12), (14, 24, 36),
               (14, 36, 24), (21, 12, 12), (21, 12, 36),
               (21, 24, 24), (21, 36, 12), (21, 36, 36)]
    sigma_z = 2.5
    sigma_xy = 1.0
    for cz, cy, cx in centers:
        spot = np.exp(
            -(
                ((zz - cz) ** 2) / (2.0 * sigma_z**2)
                + ((yy - cy) ** 2 + (xx - cx) ** 2) / (2.0 * sigma_xy**2)
            )
        )
        volume += spot.astype(np.float32)

    ratio = rmp._estimate_apparent_z_anisotropy_ratio(volume)
    assert ratio is not None
    assert ratio > 1.2


def test_candidate_local_maxima_coords_matches_maximum_filter() -> None:
    """Candidate-local maxima should match the old 3x3x3 max-filter criterion."""
    image = np.zeros((5, 6, 7), dtype=np.float32)
    image[0, 0, 0] = 3.0
    image[2, 3, 4] = 5.0
    image[2, 3, 5] = 4.0
    image[4, 5, 6] = 2.0
    candidate_mask = np.zeros_like(image, dtype=bool)
    candidate_mask[0, 0, 0] = True
    candidate_mask[2, 3, 4] = True
    candidate_mask[2, 3, 5] = True
    candidate_mask[4, 5, 6] = True

    expected_mask = candidate_mask & (
        image >= ndi.maximum_filter(image, size=(3, 3, 3), mode="nearest")
    )
    actual_coords = rmp_anisotropy._candidate_local_maxima_coords(
        image,
        candidate_mask,
    )
    actual_mask = np.zeros_like(candidate_mask)
    actual_mask[tuple(actual_coords.T)] = True

    assert np.array_equal(actual_mask, expected_mask)


def test_spot_call_with_anisotropy_correction_preserves_shape() -> None:
    """Anisotropy-corrected spot call should return labels in original shape."""
    shape = (20, 24, 24)
    zz, yy, xx = np.indices(shape, dtype=np.float32)
    image = np.exp(
        -(
            ((zz - 10.0) ** 2) / (2.0 * 2.5**2)
            + ((yy - 12.0) ** 2 + (xx - 12.0) ** 2) / (2.0 * 1.0**2)
        )
    ).astype(np.float32)

    labels = rmp._spot_call_with_anisotropy_correction(image, threshold=0.2)
    assert labels.shape == image.shape
    assert labels.dtype == np.int32


def test_segment_from_markers_empty_foreground() -> None:
    """Return zeros when threshold removes all foreground."""
    enhanced = np.zeros((4, 4), dtype=np.float32)
    markers = np.zeros((4, 4), dtype=np.int32)
    labels = rmp._segment_from_markers(enhanced, markers, threshold=0.5)
    assert labels.shape == enhanced.shape
    assert labels.max() == 0


@pytest.mark.parametrize("legacy_setting", [True, False])
def test_rmp_detector_denoises_input_and_top_hat(
    monkeypatch,
    legacy_setting: bool,
) -> None:
    """Always denoise input and top-hat, even when legacy setting is present."""
    image = np.zeros((9, 9), dtype=np.float32)
    image[4, 4] = 1.0
    calls: list[tuple[np.ndarray, bool]] = []

    monkeypatch.setattr(rmp, "layer_data_asarray", lambda layer: np.asarray(layer.data))
    monkeypatch.setattr(
        rmp,
        "_normalize_image",
        lambda array: np.asarray(array, dtype=np.float32),
    )

    def fake_wavelet_denoise(
        array: np.ndarray,
        *,
        enabled: bool,
        sigma: float | None = None,
    ) -> np.ndarray:
        _ = sigma
        arr = np.asarray(array, dtype=np.float32)
        calls.append((arr.copy(), enabled))
        if enabled:
            return arr + 10.0
        return arr

    monkeypatch.setattr(rmp, "wavelet_denoise_input", fake_wavelet_denoise)
    monkeypatch.setattr(rmp, "_dask_available", lambda: False)
    monkeypatch.setattr(rmp, "_distributed_available", lambda: False)
    monkeypatch.setattr(
        rmp,
        "_compute_top_hat_nd",
        lambda array, config, **_: np.asarray(array, dtype=np.float32) + 5.0,
    )
    captured_top_hat: dict[str, np.ndarray] = {}
    captured_reference: dict[str, np.ndarray] = {}

    def fake_postprocess(
        top_hat: np.ndarray,
        config,
        *,
        reference_image: np.ndarray | None = None,
    ) -> tuple[np.ndarray, np.ndarray]:
        _ = config
        arr = np.asarray(top_hat, dtype=np.float32)
        captured_top_hat["value"] = arr
        captured_reference["value"] = np.asarray(reference_image, dtype=np.float32)
        return np.zeros_like(arr, dtype=np.int32), arr

    monkeypatch.setattr(rmp, "_postprocess_top_hat", fake_postprocess)

    detector = rmp.RMPDetector()
    result = detector.run(
        layer=DummyLayer(image),
        settings={"enable_denoising": legacy_setting},
    )

    assert result["mask"].shape == image.shape
    assert len(calls) == 2
    assert calls[0][1] is True
    assert calls[1][1] is True
    expected_top_hat_input = calls[0][0] + 10.0 + 5.0
    assert np.allclose(calls[1][0], expected_top_hat_input)
    expected_postprocess_input = calls[1][0] + 10.0
    assert np.allclose(captured_top_hat["value"], expected_postprocess_input)
    expected_reference = calls[0][0] + 10.0
    assert np.allclose(captured_reference["value"], expected_reference)


def test_rmp_detector_pads_tiled_input_then_crops_before_postprocess(
    monkeypatch,
) -> None:
    """Pad tiled input to chunk multiples and crop top-hat back to original shape."""
    image = np.zeros((17, 19), dtype=np.float32)
    captured_shapes: dict[str, tuple[int, ...]] = {}

    monkeypatch.setattr(rmp, "layer_data_asarray", lambda layer: np.asarray(layer.data))
    monkeypatch.setattr(
        rmp,
        "_normalize_image",
        lambda array: np.asarray(array, dtype=np.float32),
    )
    monkeypatch.setattr(
        rmp,
        "wavelet_denoise_input",
        lambda array, *, enabled, sigma=None: np.asarray(array, dtype=np.float32),
    )
    monkeypatch.setattr(rmp, "_dask_available", lambda: True)
    monkeypatch.setattr(rmp, "_distributed_available", lambda: False)

    def fake_compute_top_hat_nd(
        array: np.ndarray,
        config,
        *,
        use_tiled: bool,
        use_distributed: bool,
    ) -> np.ndarray:
        _ = config
        captured_shapes["top_hat_input"] = tuple(array.shape)
        assert use_tiled is True
        assert use_distributed is False
        return np.ones_like(array, dtype=np.float32)

    monkeypatch.setattr(rmp, "_compute_top_hat_nd", fake_compute_top_hat_nd)

    def fake_postprocess(
        top_hat: np.ndarray,
        config,
        *,
        reference_image: np.ndarray | None = None,
    ) -> tuple[np.ndarray, np.ndarray]:
        _ = config
        assert reference_image is not None
        captured_shapes["top_hat_for_postprocess"] = tuple(top_hat.shape)
        captured_shapes["reference_image"] = tuple(np.asarray(reference_image).shape)
        labels = np.zeros_like(reference_image, dtype=np.int32)
        return labels, np.asarray(top_hat, dtype=np.float32)

    monkeypatch.setattr(rmp, "_postprocess_top_hat", fake_postprocess)

    detector = rmp.RMPDetector()
    result = detector.run(layer=DummyLayer(image), settings={})

    expected_padded_shape = (
        rmp.RMP_TILE_CHUNK_SIZE[0],
        rmp.RMP_TILE_CHUNK_SIZE[1],
    )
    assert captured_shapes["top_hat_input"] == expected_padded_shape
    assert captured_shapes["top_hat_for_postprocess"] == image.shape
    assert captured_shapes["reference_image"] == image.shape
    assert result["mask"].shape == image.shape
