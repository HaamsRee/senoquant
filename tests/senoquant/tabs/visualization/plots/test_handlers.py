"""Tests for visualization plot handlers."""

from __future__ import annotations

from pathlib import Path
import sys
import types

import numpy as np
import pandas as pd

from senoquant.tabs.visualization.plots import PlotConfig
from senoquant.tabs.visualization.plots.double_expression import DoubleExpressionPlot
from senoquant.tabs.visualization.plots.spatialplot import SpatialPlot
from senoquant.tabs.visualization.plots.umap import UMAPPlot


def _context(type_name: str):
    return types.SimpleNamespace(state=PlotConfig(type_name=type_name))


def _write_csv(path: Path, data: dict[str, list[float]]) -> None:
    pd.DataFrame(data).to_csv(path, index=False)


def test_spatial_plot_success_and_no_intensity_branch(tmp_path: Path) -> None:
    """Generate spatial plots with and without an intensity color column."""
    plot = SpatialPlot(types.SimpleNamespace(), _context("Spatial Plot"))
    input_dir = tmp_path / "input"
    temp_dir = tmp_path / "temp"
    input_dir.mkdir()
    temp_dir.mkdir()

    # Includes intensity columns (colorbar branch).
    _write_csv(
        input_dir / "cells.csv",
        {
            "x_coord": [0, 1, 2],
            "y_coord": [0, 1, 2],
            "A_mean_intensity": [0.1, 0.8, 0.9],
            "B_mean_intensity": [0.4, 0.3, 0.2],
        },
    )
    outputs = list(
        plot.plot(
            temp_dir,
            input_dir,
            "png",
            markers=["A"],
            thresholds={"A": 0.5},
        )
    )
    assert len(outputs) == 1
    assert outputs[0].exists()

    # Only X/Y numeric columns (no intensity branch).
    _write_csv(
        input_dir / "cells.csv",
        {
            "xpos": [0, 1, 2],
            "ypos": [0, 1, 2],
            "label": [1, 1, 1],
        },
    )
    outputs = list(plot.plot(temp_dir, input_dir, "png", markers=None, thresholds=None))
    assert len(outputs) == 1
    assert outputs[0].exists()


def test_spatial_plot_missing_xy_and_exception_paths(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Return empty outputs for invalid input and unexpected read errors."""
    plot = SpatialPlot(types.SimpleNamespace(), _context("Spatial Plot"))
    input_dir = tmp_path / "input"
    temp_dir = tmp_path / "temp"
    input_dir.mkdir()
    temp_dir.mkdir()

    _write_csv(
        input_dir / "bad.csv",
        {
            "A_mean_intensity": [0.1, 0.2],
            "B_mean_intensity": [0.3, 0.4],
        },
    )
    assert list(plot.plot(temp_dir, input_dir, "png")) == []

    def _boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(pd, "read_csv", _boom)
    assert list(plot.plot(temp_dir, input_dir, "png")) == []


def test_umap_plot_success_and_short_circuit_paths(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Generate UMAP plot and exercise no-file/insufficient-feature branches."""
    plot = UMAPPlot(types.SimpleNamespace(), _context("UMAP"))
    input_dir = tmp_path / "input"
    temp_dir = tmp_path / "temp"
    input_dir.mkdir()
    temp_dir.mkdir()

    class _FakeUMAP:
        def __init__(self, n_components: int, random_state: int) -> None:
            self.n_components = n_components
            self.random_state = random_state

        def fit_transform(self, values):
            values = np.asarray(values)
            return values[:, :2]

    monkeypatch.setitem(sys.modules, "umap", types.SimpleNamespace(UMAP=_FakeUMAP))

    _write_csv(
        input_dir / "cells.csv",
        {
            "A_mean_intensity": [0.0, 1.0, 0.5],
            "B_mean_intensity": [0.1, 0.2, 0.3],
            "x": [1, 2, 3],
        },
    )
    outputs = list(
        plot.plot(
            temp_dir,
            input_dir,
            "png",
            markers=["A", "B"],
            thresholds={"A": 0.2},
        )
    )
    assert len(outputs) == 1
    assert outputs[0].exists()

    # Need at least 2 numeric marker columns.
    assert list(plot.plot(temp_dir, input_dir, "png", markers=["A"])) == []

    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    assert list(plot.plot(temp_dir, empty_dir, "png")) == []


def test_umap_plot_exception_path(tmp_path: Path, monkeypatch) -> None:
    """Return empty output when UMAP reducer raises during embedding."""
    plot = UMAPPlot(types.SimpleNamespace(), _context("UMAP"))
    input_dir = tmp_path / "input"
    temp_dir = tmp_path / "temp"
    input_dir.mkdir()
    temp_dir.mkdir()

    _write_csv(
        input_dir / "cells.csv",
        {
            "A_mean_intensity": [0.0, 1.0],
            "B_mean_intensity": [0.1, 0.2],
        },
    )

    class _BadUMAP:
        def __init__(self, *_args, **_kwargs) -> None:
            return None

        def fit_transform(self, _values):
            raise RuntimeError("bad reducer")

    monkeypatch.setitem(sys.modules, "umap", types.SimpleNamespace(UMAP=_BadUMAP))
    assert list(plot.plot(temp_dir, input_dir, "png", markers=["A", "B"])) == []


def test_double_expression_success_and_validation_paths(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Generate double-expression plot and validate early-return branches."""
    plot = DoubleExpressionPlot(types.SimpleNamespace(), _context("Double Expression"))
    input_dir = tmp_path / "input"
    temp_dir = tmp_path / "temp"
    input_dir.mkdir()
    temp_dir.mkdir()

    errors: list[str] = []
    monkeypatch.setattr(
        "senoquant.tabs.visualization.plots.double_expression.show_error",
        lambda message: errors.append(message),
    )

    _write_csv(
        input_dir / "cells.csv",
        {
            "x_coord": [0, 1, 2, 3],
            "y_coord": [0, 1, 2, 3],
            "CD3_mean_intensity": [0.1, 0.8, 0.9, 0.2],
            "CD8_mean_intensity": [0.2, 0.3, 0.9, 0.95],
        },
    )
    outputs = list(
        plot.plot(
            temp_dir,
            input_dir,
            "png",
            markers=["CD3", "CD8"],
            thresholds={"CD3": 0.5, "CD8": 0.5},
        )
    )
    assert len(outputs) == 1
    assert outputs[0].exists()
    assert errors == []

    assert list(plot.plot(temp_dir, input_dir, "png", markers=["CD3"])) == []
    assert any("requires exactly 2 markers" in msg for msg in errors)

    _write_csv(
        input_dir / "cells.csv",
        {"x": [1], "y": [1], "CD3_mean_intensity": [1.0]},
    )
    assert list(plot.plot(temp_dir, input_dir, "png", markers=["CD3", "CD8"])) == []
    assert any("Missing columns for markers" in msg for msg in errors)

    _write_csv(
        input_dir / "cells.csv",
        {
            "CD3_mean_intensity": [1.0],
            "CD8_mean_intensity": [1.0],
        },
    )
    assert list(plot.plot(temp_dir, input_dir, "png", markers=["CD3", "CD8"])) == []
    assert any("Could not find X/Y columns" in msg for msg in errors)


def test_double_expression_exception_path(tmp_path: Path, monkeypatch) -> None:
    """Emit an error notification when unexpected plotting failures occur."""
    plot = DoubleExpressionPlot(types.SimpleNamespace(), _context("Double Expression"))
    input_dir = tmp_path / "input"
    temp_dir = tmp_path / "temp"
    input_dir.mkdir()
    temp_dir.mkdir()

    errors: list[str] = []
    monkeypatch.setattr(
        "senoquant.tabs.visualization.plots.double_expression.show_error",
        lambda message: errors.append(message),
    )

    _write_csv(
        input_dir / "cells.csv",
        {
            "x": [1, 2],
            "y": [3, 4],
            "CD3_mean_intensity": [1.0, 0.0],
            "CD8_mean_intensity": [0.0, 1.0],
        },
    )

    def _boom(*_args, **_kwargs):
        raise RuntimeError("read failure")

    monkeypatch.setattr(pd, "read_csv", _boom)
    assert list(plot.plot(temp_dir, input_dir, "png", markers=["CD3", "CD8"])) == []
    assert any("Error in Double Expression Plot" in msg for msg in errors)

