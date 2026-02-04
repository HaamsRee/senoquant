"""Spatial plot handler for visualization."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .base import PlotData, SenoQuantPlot


class SpatialPlotData(PlotData):
    """Configuration data for spatial plot."""

    pass


class SpatialPlot(SenoQuantPlot):
    """Spatial scatter plot handler for coordinate and intensity data."""

    feature_type = "Spatial Plot"
    order = 0

    def build(self) -> None:
        """Build the UI for spatial plot configuration."""
        # Minimal UI for now; can add controls for marker selection, colormaps, etc. later
        pass

    def plot(
        self, 
        temp_dir: Path, 
        input_path: Path, 
        export_format: str,
        markers: list[str] | None = None,
        thresholds: dict[str, float] | None = None,
    ) -> Iterable[Path]:
        """Generate spatial plot from input CSV.

        Parameters
        ----------
        temp_dir : Path
            Temporary directory to write plot output.
        input_path : Path
            Path to input CSV file or folder containing CSV files.
        export_format : str
            Output format ("png", "svg", or "pdf").
        markers : list of str, optional
            List of selected markers to include.
        thresholds : dict, optional
            Dictionary of {marker_name: threshold_value} for filtering.

        Returns
        -------
        iterable of Path
            Paths to generated plot files.
        """
        try:
            try:
                import pandas as pd
            except ImportError:
                print("[SpatialPlot] pandas is not installed; skipping plot generation.")
                return []
            try:
                import matplotlib.pyplot as plt
            except ImportError:
                print(
                    "[SpatialPlot] matplotlib is not installed; skipping plot generation."
                )
                return []

            print(f"[SpatialPlot] Starting with input_path={input_path}")
            # Find the first data file (CSV or Excel) in the input folder
            data_files = list(input_path.glob("*.csv")) + list(input_path.glob("*.xlsx")) + list(input_path.glob("*.xls"))
            print(f"[SpatialPlot] Found {len(data_files)} data files")
            if not data_files:
                print(f"[SpatialPlot] No CSV/Excel files found in {input_path}")
                return []
            
            data_file = data_files[0]
            print(f"[SpatialPlot] Reading {data_file}")
            if data_file.suffix.lower() in ('.xlsx', '.xls'):
                df = pd.read_excel(data_file)
            else:
                df = pd.read_csv(data_file)
            print(f"[SpatialPlot] Loaded dataframe with shape {df.shape}")
            if df.empty:
                print(f"[SpatialPlot] DataFrame is empty")
                return []
            
            print(df.head())

            # Apply thresholds if provided
            if thresholds:
                for marker, thresh in thresholds.items():
                    col_name = f"{marker}_mean_intensity"
                    if col_name in df.columns:
                        # Clip values below threshold to 0
                        df.loc[df[col_name] < thresh, col_name] = 0

            # Filter columns based on selected markers (optional, but good for cleanup)
            if markers is not None:
                # We want to ensure we don't pick a deselected marker as the intensity column
                valid_marker_cols = [f"{m}_mean_intensity" for m in markers]
                # Keep non-marker columns (like coords) + valid marker columns
                cols_to_keep = [c for c in df.columns if "_mean_intensity" not in c or c in valid_marker_cols]
                df = df[cols_to_keep]
                print(f"[SpatialPlot] Filtered columns using {len(valid_marker_cols)} selected markers")

            # Look for X, Y coordinate columns
            x_col = None
            y_col = None
            for col in df.columns:
                col_lower = col.lower()
                if "x" in col_lower and x_col is None:
                    x_col = col
                elif "y" in col_lower and y_col is None:
                    y_col = col

            if x_col is None or y_col is None:
                return []

            x = df[x_col].values
            y = df[y_col].values

            # Get first numeric column (intensity) for coloring
            numeric_cols = df.select_dtypes(include=["number"]).columns
            intensity_col = None
            for col in numeric_cols:
                if col not in [x_col, y_col]:
                    intensity_col = col
                    break

            # Create plot
            fig, ax = plt.subplots(figsize=(8, 6))
            if intensity_col is not None:
                c = df[intensity_col].values
                scatter = ax.scatter(x, y, c=c, cmap="viridis", alpha=0.6, s=20)
                plt.colorbar(scatter, ax=ax, label=intensity_col)
            else:
                ax.scatter(x, y, alpha=0.6, s=20)

            ax.set_xlabel(x_col)
            ax.set_ylabel(y_col)
            ax.set_title("Spatial Distribution")

            # Save plot
            output_file = temp_dir / f"spatial_plot.{export_format}"
            fig.savefig(str(output_file), dpi=150, bbox_inches="tight")
            plt.close(fig)

            return [output_file]

        except Exception as e:
            import traceback
            print(f"[SpatialPlot] ERROR generating spatial plot: {e}")
            print(traceback.format_exc())
            return []
