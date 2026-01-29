"""Tests for quantification backend routing.

Notes
-----
Validates output folder naming and export routing behavior.
"""

from __future__ import annotations

from pathlib import Path

from senoquant.tabs.quantification.backend import (
    FeatureExportResult,
    QuantificationBackend,
)
from senoquant.tabs.quantification.features.base import FeatureConfig


class DummyHandler:
    """Handler stub that writes a file and returns its path."""

    def __init__(self, filename: str) -> None:
        self._filename = filename

    def export(self, temp_dir: Path, _format: str):
        path = temp_dir / self._filename
        path.write_text("data")
        return [path]


class DummyContext:
    """Feature context stub for backend processing."""

    def __init__(self, feature: FeatureConfig, handler) -> None:
        self.state = feature
        self.feature_handler = handler


def test_feature_dir_name_sanitizes() -> None:
    """Sanitize feature names into folder names.

    Returns
    -------
    None
    """
    backend = QuantificationBackend()
    feature = FeatureConfig(name="My Feature!*", type_name="Markers")
    feature_output = FeatureExportResult(
        feature_id=feature.feature_id,
        feature_type=feature.type_name,
        feature_name=feature.name,
        temp_dir=Path("/tmp"),
        outputs=[],
    )
    output = backend._feature_dir_name(feature_output)
    assert output == "my_feature__"


def test_process_routes_outputs(tmp_path: Path) -> None:
    """Route outputs into per-feature folders.

    Returns
    -------
    None
    """
    backend = QuantificationBackend()
    feature_a = FeatureConfig(feature_id="a", name="Feature A", type_name="Markers")
    feature_b = FeatureConfig(feature_id="b", name="Feature B", type_name="Spots")
    contexts = [
        DummyContext(feature_a, DummyHandler("a.csv")),
        DummyContext(feature_b, DummyHandler("b.csv")),
    ]

    result = backend.process(
        contexts,
        output_path=str(tmp_path),
        output_name="",
        export_format="csv",
        cleanup=False,
    )

    feature_dirs = [path for path in result.output_root.iterdir() if path.is_dir()]
    assert len(feature_dirs) == 2
    assert any((d / "a.csv").exists() for d in feature_dirs)
    assert any((d / "b.csv").exists() for d in feature_dirs)
