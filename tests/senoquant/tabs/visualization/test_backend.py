"""Tests for visualization backend routing and orchestration."""

from __future__ import annotations

from pathlib import Path
import shutil
import types

from senoquant.tabs.visualization.backend import (
    PlotExportResult,
    VisualizationBackend,
    VisualizationResult,
)
from senoquant.tabs.visualization.plots import PlotConfig


class _Handler:
    """Simple plot handler that writes one output file."""

    def __init__(self, filename: str = "plot.png") -> None:
        self.filename = filename
        self.calls: list[dict] = []

    def plot(
        self,
        temp_dir: Path,
        input_path: Path,
        export_format: str,
        *,
        markers: list[str] | None = None,
        thresholds: dict[str, float] | None = None,
    ) -> list[Path]:
        self.calls.append(
            {
                "temp_dir": temp_dir,
                "input_path": input_path,
                "format": export_format,
                "markers": markers,
                "thresholds": thresholds,
            }
        )
        out = temp_dir / self.filename
        out.write_text("ok")
        return [out]


def test_process_routes_outputs_and_cleans_temp(tmp_path: Path) -> None:
    """Route plot outputs and cleanup temporary exports."""
    backend = VisualizationBackend()
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()

    config = PlotConfig(plot_id="p1", type_name="UMAP")
    handler = _Handler("umap.png")
    context = types.SimpleNamespace(state=config, plot_handler=handler)

    result = backend.process(
        [context],
        input_dir,
        str(output_dir),
        "joined",
        "png",
        markers=["CD3"],
        thresholds={"CD3": 0.5},
        save=True,
        cleanup=True,
    )

    expected = output_dir / "joined.png"
    assert expected.exists()
    assert len(result.plot_outputs) == 1
    assert result.plot_outputs[0].outputs == [expected]
    assert len(handler.calls) == 1
    assert handler.calls[0]["markers"] == ["CD3"]
    assert handler.calls[0]["thresholds"] == {"CD3": 0.5}
    assert not result.temp_root.exists()


def test_process_skips_invalid_context_and_keeps_temp_when_requested(
    tmp_path: Path,
) -> None:
    """Skip non-PlotConfig entries and optionally keep temp outputs."""
    backend = VisualizationBackend()
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()

    invalid = types.SimpleNamespace(state="not-a-plot", plot_handler=_Handler())
    no_plot_method = types.SimpleNamespace(
        state=PlotConfig(plot_id="p2", type_name="Spatial Plot"),
        plot_handler=object(),
    )

    result = backend.process(
        [invalid, no_plot_method],
        input_dir,
        str(output_dir),
        "unused",
        "png",
        save=False,
        cleanup=False,
    )

    assert len(result.plot_outputs) == 1
    assert result.plot_outputs[0].plot_id == "p2"
    assert result.plot_outputs[0].outputs == []
    assert result.temp_root.exists()
    shutil.rmtree(result.temp_root, ignore_errors=True)


def test_save_result_re_routes_existing_outputs(tmp_path: Path) -> None:
    """Save an existing result into a new output folder."""
    backend = VisualizationBackend()
    source_dir = tmp_path / "temp"
    source_dir.mkdir()
    source_file = source_dir / "spatial.svg"
    source_file.write_text("svg")

    export = PlotExportResult(
        plot_id="s1",
        plot_type="Spatial Plot",
        temp_dir=source_dir,
        outputs=[source_file],
    )
    result = VisualizationResult(
        input_root=tmp_path,
        output_root=tmp_path / "old",
        temp_root=tmp_path / "temp_root",
        plot_outputs=[export],
    )

    backend.save_result(result, str(tmp_path / "final"), "saved_name")
    expected = tmp_path / "final" / "saved_name.svg"
    assert expected.exists()
    assert result.output_root == tmp_path / "final"
    assert result.plot_outputs[0].outputs == [expected]


def test_route_outputs_fallback_and_branches(tmp_path: Path, monkeypatch) -> None:
    """Route outputs from explicit and fallback sources, including edge cases."""
    backend = VisualizationBackend()
    out_dir = tmp_path / "final"
    out_dir.mkdir()

    # Fallback file discovery from temp dir.
    fallback_dir = tmp_path / "fallback"
    fallback_dir.mkdir()
    (fallback_dir / "a.png").write_text("a")
    (fallback_dir / "b.svg").write_text("b")

    fallback = PlotExportResult(
        plot_id="f1",
        plot_type="Spatial Plot",
        temp_dir=fallback_dir,
        outputs=[],
    )
    empty = PlotExportResult(
        plot_id="e1",
        plot_type="UMAP",
        temp_dir=tmp_path / "empty",
        outputs=[],
    )
    empty.temp_dir.mkdir()

    # Explicit output list with one existing file.
    explicit_dir = tmp_path / "explicit"
    explicit_dir.mkdir()
    explicit_file = explicit_dir / "one.pdf"
    explicit_file.write_text("one")
    explicit = PlotExportResult(
        plot_id="x1",
        plot_type="Double Expression",
        temp_dir=explicit_dir,
        outputs=[explicit_file, explicit_dir / "missing.pdf"],
    )

    def _copy2(src: str, dest: Path):
        if src.endswith("one.pdf"):
            raise shutil.SameFileError(src, str(dest))
        return shutil.copyfile(src, dest)

    monkeypatch.setattr("senoquant.tabs.visualization.backend.shutil.copy2", _copy2)

    backend._route_plot_outputs(out_dir, [fallback, empty, explicit], output_name="")

    assert len(fallback.outputs) == 2
    assert all(path.exists() for path in fallback.outputs)
    assert {path.name for path in fallback.outputs} == {
        "Spatial_Plot_a.png",
        "Spatial_Plot_b.svg",
    }
    assert empty.outputs == []
    assert explicit.outputs == [out_dir / "Double_Expression_one.pdf"]


def test_route_outputs_with_custom_name_and_helpers(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Use custom output names and helper methods."""
    backend = VisualizationBackend()
    monkeypatch.chdir(tmp_path)

    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "one.png").write_text("1")
    (source_dir / "two.png").write_text("2")

    export = PlotExportResult(
        plot_id="a1",
        plot_type="Type / With Symbols",
        temp_dir=source_dir,
        outputs=[],
    )

    out = tmp_path / "dest"
    out.mkdir()
    backend._route_plot_outputs(out, [export], output_name="custom")
    assert {p.name for p in export.outputs} == {"custom_1.png", "custom_2.png"}

    assert backend._resolve_output_root("", "") == tmp_path
    assert backend._resolve_output_root(str(tmp_path), "named") == tmp_path / "named"
    assert backend._plot_dir_name(export) == "type___with_symbols"

