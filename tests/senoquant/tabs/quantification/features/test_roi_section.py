"""Tests for ROI configuration rows."""

from __future__ import annotations

from types import SimpleNamespace

from tests.conftest import DummyLayout

from senoquant.tabs.quantification.features.roi import ROISection


def test_deleting_equal_roi_row_keeps_survivors_bound_to_state() -> None:
    """Editing visible rows after deletion updates the stored ROI list."""
    rois = []
    tab = SimpleNamespace(
        _feature_index=lambda _context: 0,
        _features_layout=DummyLayout(),
        _apply_features_layout=lambda: None,
        _features_scroll_area=None,
        _configure_combo=lambda _combo: None,
        _viewer=None,
        window=lambda: None,
    )
    context = SimpleNamespace(right_layout=DummyLayout())
    section = ROISection(tab, context, rois)
    section.build()

    for _ in range(3):
        section._add_row()
    first, middle, last = (roi for _widget, roi in section._items)
    assert first == middle == last

    section._remove_row(section._items[1][0])
    assert len(rois) == 2
    assert rois[0] is first
    assert rois[1] is last

    first.name = "First"
    last.name = "Last"
    assert [roi.name for roi in rois] == ["First", "Last"]

    section.clear()
    assert not section._items
    assert not rois
