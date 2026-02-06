"""Backend logic for the Visualization tab."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable
import shutil
import tempfile

from .plots import PlotConfig


@dataclass
class PlotExportResult:
    """Output metadata for a single plot export.

    Attributes
    ----------
    plot_id : str
        Stable identifier for the exported plot instance.
    plot_type : str
        Plot type name used for routing (e.g., ``"UMAP"``).
    temp_dir : Path
        Temporary directory where the plot wrote its outputs.
    outputs : list of Path
        Explicit file paths returned by the plot processor.
    """

    plot_id: str
    plot_type: str
    temp_dir: Path
    outputs: list[Path] = field(default_factory=list)


@dataclass
class VisualizationResult:
    """Aggregated output information for a visualization run.

    Attributes
    ----------
    input_root : Path
        Root input directory.
    output_root : Path
        Root output directory for the run.
    temp_root : Path
        Temporary root directory used during processing.
    plot_outputs : list of PlotExportResult
        Per-plot export metadata for the run.
    """
    input_root: Path
    output_root: Path
    temp_root: Path
    plot_outputs: list[PlotExportResult]


class VisualizationBackend:
    """Backend orchestrator for visualization exports.

    Notes
    -----
    Feature export routines live with their feature implementations. The
    backend iterates through configured feature contexts, asks each feature
    handler to export into a temporary directory, and then routes those
    outputs into a final output structure.
    """

    def __init__(self) -> None:
        """Initialize the backend state.

        Attributes
        ----------
        metrics : list
            Placeholder container for computed metrics.
        """
        self.metrics: list[object] = []

    def process(
        self,
        plots: Iterable[object],
        input_path: Path,
        output_path: str,
        output_name: str,
        export_format: str,
        markers: list[str] | None = None,
        thresholds: dict[str, float] | None = None,
        save: bool = True,
        cleanup: bool = True,
    ) -> VisualizationResult:
        """Run plot exports and route their outputs.

        Parameters
        ----------
        plots : iterable of object
            Plot UI contexts with ``state`` and ``plot_handler``.
            Each handler should implement ``plot(temp_dir, input_path, export_format)``.
        input_path : Path
            Path to the input folder containing quantification files.
        output_path : str
            Base output folder path.
        output_name : str
            Folder name used to group exported outputs.
        export_format : str
            File format requested by the user (``"png"`` or ``"svg"``).
        markers : list of str, optional
            List of selected markers to include.
        thresholds : dict, optional
            Dictionary of {marker_name: threshold_value} for filtering.
        save : bool, optional
            Whether to save (route) the outputs to the final destination immediately.
        cleanup : bool, optional
            Whether to delete temporary export folders after routing.

        Returns
        -------
        VisualizationResult
            Output metadata for the completed run.

        Notes
        -----
        If a plot export does not return explicit output paths, the backend
        will move all files found in the plot's temp directory. This allows
        plot implementations to either return specific files or simply write
        into the provided temporary directory.
        """
        input_path = Path(input_path)
        
        plot_input = input_path
        if input_path.is_file():
            input_root = input_path.parent
            plot_input = input_path.parent
        else:
            input_root = input_path

        # Treat `output_path` as the folder and `output_name` as an optional
        # filename base. Resolve output_root without using output_name so
        # output_name can be applied as a file name rather than a subfolder.
        output_root = self._resolve_output_root(output_path, "")
        output_root.mkdir(parents=True, exist_ok=True)
        temp_root = Path(tempfile.mkdtemp(prefix="senoquant-plot-"))

        plot_outputs: list[PlotExportResult] = []
        for context in plots:
            plot = getattr(context, "state", None)
            handler = getattr(context, "plot_handler", None)
            if not isinstance(plot, PlotConfig):
                continue
            print(f"[Backend] Processing plot: {plot.type_name}")
            print(f"[Backend] Handler: {handler}")
            print(f"[Backend] Handler has plot method: {hasattr(handler, 'plot') if handler else False}")
            temp_dir = temp_root / plot.plot_id
            temp_dir.mkdir(parents=True, exist_ok=True)
            outputs: list[Path] = []
            if handler is not None and hasattr(handler, "plot"):
                print(f"[Backend] Calling handler.plot() with input_path={plot_input}, format={export_format}")
                outputs = [
                    Path(path)
                    for path in handler.plot(
                        temp_dir, 
                        plot_input, 
                        export_format,
                        markers=markers,
                        thresholds=thresholds
                    )
                ]
                print(f"[Backend] Handler returned {len(outputs)} outputs: {outputs}")
            else:
                print(f"[Backend] Skipping: handler is None or has no plot method")
            plot_outputs.append(
                PlotExportResult(
                    plot_id=plot.plot_id,
                    plot_type=plot.type_name,
                    temp_dir=temp_dir,
                    outputs=outputs,
                )
            )

        if save:
            print(f"[Backend] About to route {len(plot_outputs)} plot outputs")
            self._route_plot_outputs(output_root, plot_outputs, output_name)
        if cleanup:
            shutil.rmtree(temp_root, ignore_errors=True)
        return VisualizationResult(
            input_root=input_root,
            output_root=output_root,
            temp_root=temp_root,
            plot_outputs=plot_outputs,
        )

    def save_result(
        self, 
        result: VisualizationResult, 
        output_path: str, 
        output_name: str
    ) -> None:
        """Save an existing visualization result to the specified output.

        This moves/copies files from the result's temporary directory (or previous location)
        to the new output path.
        """
        output_root = self._resolve_output_root(output_path, "")
        output_root.mkdir(parents=True, exist_ok=True)
        result.output_root = output_root
        self._route_plot_outputs(output_root, result.plot_outputs, output_name)

    def _resolve_output_root(self, output_path: str, output_name: str) -> Path:
        """Resolve the final output root directory.

        Parameters
        ----------
        output_path : str
            Base output folder path.
        output_name : str
            Folder name used to group exported outputs.

        Returns
        -------
        Path
            Resolved output directory path.
        """
        if output_path and output_path.strip():
            base = Path(output_path)
        else:
            # Default to repository root (current working directory)
            base = Path.cwd()
        if output_name and output_name.strip():
            return base / output_name
        return base

    def _route_plot_outputs(
        self,
        output_root: Path,
        plot_outputs: Iterable[PlotExportResult],
        output_name: str = "",
    ) -> None:
        """Move plot outputs from temp folders to the final location.

        Parameters
        ----------
        output_root : Path
            Destination root folder.
        plot_outputs : iterable of PlotExportResult
            Export results to route.

        Notes
        -----
        When a plot returns no explicit output list, all files present
        in the temporary directory are routed instead. Subdirectories are
        not traversed.
        """
        for plot_output in plot_outputs:
            print(f"[Backend] Routing {plot_output.plot_type} to {output_root}")
            final_paths: list[Path] = []
            outputs = plot_output.outputs
            # Choose source list: explicit outputs if provided, otherwise files
            # from the temp directory.
            source_files: list[Path] = []
            if outputs:
                source_files = [p for p in outputs if Path(p).exists()]
            else:
                source_files = [p for p in plot_output.temp_dir.glob("*") if p.is_file()]

            if not source_files:
                print(f"[Backend]   No files to route for {plot_output.plot_type}")
                plot_output.outputs = []
                continue

            # If the caller provided output_name, use it as the base filename.
            for idx, src in enumerate(source_files):
                src = Path(src)
                ext = src.suffix
                if output_name and output_name.strip():
                    # If multiple files, append an index to avoid collisions.
                    if len(source_files) == 1:
                        dest_name = f"{output_name}{ext}"
                    else:
                        dest_name = f"{output_name}_{idx+1}{ext}"
                else:
                    # Fallback: prefix with plot type for clarity
                    safe_type = plot_output.plot_type.replace(' ', '_')
                    dest_name = f"{safe_type}_{src.name}"
                dest = output_root / dest_name
                print(f"[Backend]   Copying {src} -> {dest}")
                try:
                    shutil.copy2(str(src), dest)
                except shutil.SameFileError:
                    print(f"[Backend]   Skipping copy: source and destination are the same ({dest})")
                final_paths.append(dest)

            # Update plot_output.outputs to point at final routed files
            plot_output.outputs = final_paths

    def _plot_dir_name(self, plot_output: PlotExportResult) -> str:
        """Build a filesystem-friendly folder name for a plot.

        Parameters
        ----------
        plot_output : PlotExportResult
            Export result metadata.

        Returns
        -------
        str
            Directory name for the plot outputs.

        Notes
        -----
        Non-alphanumeric characters are replaced to avoid filesystem issues.
        """
        name = plot_output.plot_type.strip()
        safe = "".join(
            char if char.isalnum() or char in "-_ " else "_" for char in name
        )
        return safe.replace(" ", "_").lower()
