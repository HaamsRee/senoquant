"""Spatial plot handler for visualization."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import numpy as np

from .base import PlotData, SenoQuantPlot


class SpatialPlotData(PlotData):
    """Configuration data for spatial plot."""

    pass


class SpatialPlot(SenoQuantPlot):
    """Spatial scatter plot handler for coordinate and intensity data."""

    plot_type = "Spatial Plot"
    order = 0

    @staticmethod
    def _threshold_for_marker(
        thresholds: dict[str, float] | None,
        marker: str,
    ) -> float:
        """Resolve threshold with tolerant key matching."""
        if not thresholds:
            return 0.0
        candidates = (
            marker,
            marker.lower(),
            marker.upper(),
            f"{marker}_mean_intensity",
            f"{marker.lower()}_mean_intensity",
            f"{marker.upper()}_mean_intensity",
        )
        for key in candidates:
            if key in thresholds:
                try:
                    return float(thresholds[key])
                except Exception:
                    return 0.0
        return 0.0

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
            
            # Look for X, Y coordinate columns
            x_col = "centroid_x_pixels" if "centroid_x_pixels" in df.columns else None
            y_col = "centroid_y_pixels" if "centroid_y_pixels" in df.columns else None

            if x_col is None or y_col is None:
                x_col = None
                y_col = None
                x_candidates = [c for c in df.columns if "x" in c.lower()]
                for xc in x_candidates:
                    patterns = [
                        ("_x_", "_y_"), ("_X_", "_Y_"),
                        ("_x", "_y"), ("_X", "_Y"),
                        ("x_", "y_"), ("X_", "Y_"),
                        ("x", "y"), ("X", "Y")
                    ]
                    for pat_x, pat_y in patterns:
                        if pat_x in xc:
                            yc = xc.replace(pat_x, pat_y)
                            if yc in df.columns and yc != xc:
                                x_col = xc
                                y_col = yc
                                break
                    if x_col:
                        break

            if x_col is None or y_col is None:
                return []

            x = df[x_col].values
            y = df[y_col].values

            # Create a two-column layout: main plot + dedicated legend column.
            fig, (ax, legend_ax) = plt.subplots(
                ncols=2,
                figsize=(10, 6),
                gridspec_kw={"width_ratios": [1.0, 0.30], "wspace": 0.03},
            )

            # Fallback mode: if no markers selected, draw all points with one color.
            if not markers:
                ax.scatter(x, y, alpha=0.7, s=20, color="tab:blue", label="Cells")
                legend_title: str | None = None
            else:
                # Resolve selected marker columns in order, preserving the UI order.
                marker_names: list[str] = []
                marker_cols: list[str] = []
                for marker in markers:
                    candidate = f"{marker}_mean_intensity"
                    if candidate in df.columns:
                        marker_names.append(marker)
                        marker_cols.append(candidate)
                    elif marker in df.columns:
                        marker_names.append(marker)
                        marker_cols.append(marker)
                    else:
                        print(f"[SpatialPlot] Missing marker column for '{marker}', skipping.")

                if not marker_cols:
                    print("[SpatialPlot] No valid selected marker columns found.")
                    return []

                values = df[marker_cols].apply(pd.to_numeric, errors="coerce").to_numpy()
                labels = ["Other"] * len(df)
                assigned = np.zeros(len(df), dtype=bool)
                # First-match precedence: top marker in list wins overlaps.
                for idx, marker in enumerate(marker_names):
                    threshold = self._threshold_for_marker(thresholds, marker)
                    is_pos = values[:, idx] > threshold
                    take = is_pos & (~assigned)
                    if np.any(take):
                        labels_arr = np.asarray(labels, dtype=object)
                        labels_arr[take] = marker
                        labels = labels_arr.tolist()
                        assigned[take] = True

                label_series = pd.Series(labels, index=df.index, dtype="object")
                category_order = ["Other"] + marker_names
                colors = plt.cm.get_cmap("tab20", len(category_order))

                for color_idx, category in enumerate(category_order):
                    mask = label_series == category
                    if not mask.any():
                        continue
                    point_color = "lightgray" if category == "Other" else colors(color_idx)
                    ax.scatter(
                        x[mask.to_numpy()],
                        y[mask.to_numpy()],
                        alpha=0.75,
                        s=20,
                        color=point_color,
                        label=category,
                    )
                legend_title = "Assigned marker"

            handles, labels = ax.get_legend_handles_labels()
            legend_ax.axis("off")
            legend_ax.legend(
                handles,
                labels,
                loc="upper left",
                frameon=True,
                facecolor="white",
                edgecolor="0.7",
                title=legend_title,
            )

            ax.set_xlabel(x_col)
            ax.set_ylabel(y_col)
            ax.set_title("Spatial Distribution by Marker")
            ax.set_aspect("equal", adjustable="box")
            # Use image-style coordinates: y=0 at top, increasing downward.
            ax.invert_yaxis()

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
