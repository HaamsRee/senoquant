"""Tests for reader core functions."""

import pytest

from senoquant.reader import core


def test_colormap_cycle_returns_iterator():
    """Test that _colormap_cycle returns an iterator."""
    cycle = core._colormap_cycle()
    assert hasattr(cycle, "__iter__")
    assert hasattr(cycle, "__next__")


def test_colormap_cycle_cycles_through_colors():
    """Test that _colormap_cycle cycles through the expected colors."""
    cycle = core._colormap_cycle()
    expected = ["blue", "green", "red", "yellow", "cyan", "bop blue", "bop orange", "bop purple"]
    for color in expected:
        assert next(cycle) == color
    # After 8, it should cycle back to blue
    assert next(cycle) == "blue"


def test_all_channels_same_color_same():
    """Test _all_channels_same_color returns True when all colors are the same."""
    channel_colors = [
        {"colors": [[0, 0, 0, 1], [1, 1, 1, 1]], "name": "channel_0_white"},
        {"colors": [[0, 0, 0, 1], [1, 1, 1, 1]], "name": "channel_1_white"},
    ]
    assert core._all_channels_same_color(channel_colors) is True


def test_all_channels_same_color_different():
    """Test _all_channels_same_color returns False when colors differ."""
    channel_colors = [
        {"colors": [[0, 0, 0, 1], [1, 0, 0, 1]], "name": "channel_0_red"},
        {"colors": [[0, 0, 0, 1], [0, 1, 0, 1]], "name": "channel_1_green"},
    ]
    assert core._all_channels_same_color(channel_colors) is False


def test_all_channels_same_color_empty():
    """Test _all_channels_same_color returns False for empty list."""
    assert core._all_channels_same_color([]) is False


def test_all_channels_same_color_all_none():
    """Test _all_channels_same_color returns False when all are None."""
    assert core._all_channels_same_color([None, None]) is False


def test_all_channels_same_color_mixed():
    """Test _all_channels_same_color with mix of None and valid colors."""
    # With one None and one valid, there's only one valid color to compare
    # so it returns True (vacuously all same)
    channel_colors = [
        None,
        {"colors": [[0, 0, 0, 1], [1, 0, 0, 1]], "name": "channel_0_red"},
    ]
    assert core._all_channels_same_color(channel_colors) is True


def test_get_channel_colors_from_ome_no_ome():
    """Test _get_channel_colors_from_ome returns empty when no OME metadata."""
    # Create a mock image without OME metadata
    class MockImage:
        def __init__(self):
            self._ome_metadata = None

        @property
        def ome_metadata(self):
            return self._ome_metadata

    image = MockImage()
    result = core._get_channel_colors_from_ome(image)
    assert result == []


def test_get_channel_colors_from_ome_no_images():
    """Test _get_channel_colors_from_ome returns empty when no images in OME."""
    class MockOME:
        images = None

    class MockImage:
        def __init__(self):
            self._ome_metadata = MockOME()

        @property
        def ome_metadata(self):
            return self._ome_metadata

    image = MockImage()
    result = core._get_channel_colors_from_ome(image)
    assert result == []


def test_get_channel_colors_from_ome_no_pixels():
    """Test _get_channel_colors_from_ome returns empty when no pixels."""
    class MockPixelsImage:
        images = []

    class MockImage:
        def __init__(self):
            self._ome_metadata = MockPixelsImage()

        @property
        def ome_metadata(self):
            return self._ome_metadata

    image = MockImage()
    result = core._get_channel_colors_from_ome(image)
    assert result == []