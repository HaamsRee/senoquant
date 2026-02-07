"""Additional tests for quantification backend routing."""

from __future__ import annotations

from pathlib import Path

from senoquant.tabs.quantification.backend import FeatureExportResult, QuantificationBackend


def test_route_feature_outputs_moves_all(tmp_path: Path) -> None:
    """Move all files when outputs list is empty.

    Returns
    -------
    None
    """
    backend = QuantificationBackend()
    output_root = tmp_path / "out"
    output_root.mkdir()
    temp_dir = tmp_path / "temp"
    temp_dir.mkdir()
    (temp_dir / "a.csv").write_text("data")
    (temp_dir / "b.csv").write_text("data")

    feature_output = FeatureExportResult(
        feature_id="id",
        feature_type="Markers",
        feature_name="Feature",
        temp_dir=temp_dir,
        outputs=[],
    )
    backend._route_feature_outputs(output_root, [feature_output])
    moved = list(output_root.rglob("*.csv"))
    assert len(moved) == 2


def test_route_feature_outputs_moves_unlisted_files_with_explicit_outputs(
    tmp_path: Path,
) -> None:
    """Also move temp files not returned in explicit outputs list."""
    backend = QuantificationBackend()
    output_root = tmp_path / "out"
    output_root.mkdir()
    temp_dir = tmp_path / "temp"
    temp_dir.mkdir()

    listed = temp_dir / "cells.csv"
    listed.write_text("cells")
    unlisted = temp_dir / "spots_mask.npy"
    unlisted.write_bytes(b"mask")

    feature_output = FeatureExportResult(
        feature_id="id",
        feature_type="Spots",
        feature_name="Feature",
        temp_dir=temp_dir,
        outputs=[listed],
    )
    backend._route_feature_outputs(output_root, [feature_output])

    feature_dir = output_root / "feature"
    assert (feature_dir / "cells.csv").exists()
    assert (feature_dir / "spots_mask.npy").exists()
