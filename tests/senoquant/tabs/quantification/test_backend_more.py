"""Additional tests for quantification backend routing."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from senoquant.tabs.quantification.backend import FeatureExportResult, QuantificationBackend
from senoquant.tabs.quantification.features.base import FeatureConfig


class _DummyHandler:
    def __init__(self, filename: str) -> None:
        self._filename = filename

    def export(self, temp_dir: Path, _format: str):
        output = temp_dir / self._filename
        output.write_text("remote-data", encoding="utf-8")
        return [output]


class _DummyContext:
    def __init__(self, feature: FeatureConfig, handler) -> None:
        self.state = feature
        self.feature_handler = handler


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


def test_process_routes_outputs_to_memory_filesystem() -> None:
    """Route exports to a remote memory:// output root."""
    fsspec = pytest.importorskip("fsspec")
    fs = fsspec.filesystem("memory")

    root_name = f"quant-{uuid4().hex}"
    output_root = f"memory://{root_name}"
    backend = QuantificationBackend()
    feature = FeatureConfig(feature_id="remote", name="Remote Feature", type_name="Markers")
    contexts = [_DummyContext(feature, _DummyHandler("remote.csv"))]

    result = backend.process(
        contexts,
        output_path=output_root,
        output_name="run",
        export_format="csv",
        cleanup=True,
    )

    assert result.output_root == f"{output_root}/run"
    assert fs.exists(f"{root_name}/run/remote_feature/remote.csv") or fs.exists(
        f"/{root_name}/run/remote_feature/remote.csv"
    )
