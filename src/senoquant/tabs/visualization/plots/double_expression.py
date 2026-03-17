"""Double expression plot handler for visualization."""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Iterable

from senoquant.utils.naming import sanitize_name_token

try:
    from napari.utils.notifications import show_error
except Exception:  # pragma: no cover - optional runtime dependency
    def show_error(message: str) -> None:
        pass

from .base import PlotData, SenoQuantPlot


def _notify_error(message: str) -> None:
    """Send an error notification and flush stdout for immediate visibility."""
    show_error(message)
    try:
        sys.stdout.flush()
    except Exception:  # pragma: no cover - best-effort flush
        pass


class DoubleExpressionData(PlotData):
    """Configuration data for double expression plot."""

    pass


class DoubleExpressionPlot(SenoQuantPlot):
    """Spatial scatter plot highlighting double positive cells."""

    plot_type = "Double Expression"
    order = 2

    def build(self) -> None:
        """Build the UI for double expression plot configuration."""
        pass

    def plot(
        self, 
        temp_dir: Path, 
        input_path: Path, 
        export_format: str,
        markers: list[str] | None = None,
        thresholds: dict[str, float] | None = None,
    ) -> Iterable[Path]:
        """Generate double expression plot from input CSV.

        Parameters
        ----------
        temp_dir : Path
            Temporary directory to write plot output.
        input_path : Path
            Path to input CSV file or folder containing CSV files.
        export_format : str
            Output format ("png", "svg", or "pdf").
        markers : list of str, optional
            List of selected markers. Must contain exactly 2 markers.
        thresholds : dict, optional
            Dictionary of {marker_name: threshold_value}.

        Returns
        -------
        iterable of Path
            Paths to generated plot files.
        """
        try:
            try:
                import pandas as pd
            except ImportError:
                msg = (
                    "[DoubleExpressionPlot] pandas is not installed; "
                    "skipping plot generation."
                )
                print(msg)
                _notify_error(msg)
                return []
            try:
                import matplotlib.pyplot as plt
            except ImportError:
                msg = (
                    "[DoubleExpressionPlot] matplotlib is not installed; "
                    "skipping plot generation."
                )
                print(msg)
                _notify_error(msg)
                return []

            print(f"[DoubleExpressionPlot] Starting with input_path={input_path}")
            
            if not markers or len(markers) != 2:
                msg = f"Double Expression Plot requires exactly 2 markers. Got {len(markers) if markers else 0}."
                print(f"[DoubleExpressionPlot] {msg}")
                _notify_error(msg)
                return []

            # Find data file
            data_files = list(input_path.glob("*.csv")) + list(input_path.glob("*.xlsx")) + list(input_path.glob("*.xls"))
            if not data_files:
                print(f"[DoubleExpressionPlot] No data files found")
                return []
            
            data_file = data_files[0]
            if data_file.suffix.lower() in ('.xlsx', '.xls'):
                df = pd.read_excel(data_file)
            else:
                df = pd.read_csv(data_file)
            
            if df.empty:
                return []

            # Identify columns (alphabetical order from frontend)
            m1, m2 = markers[0], markers[1]
            col1 = f"{m1}_mean_intensity"
            col2 = f"{m2}_mean_intensity"
            
            if col1 not in df.columns or col2 not in df.columns:
                msg = f"Missing columns for markers: {m1}, {m2}"
                print(f"[DoubleExpressionPlot] {msg}")
                _notify_error(msg)
                return []

            # Get thresholds
            t1 = thresholds.get(m1, 0.0) if thresholds else 0.0
            t2 = thresholds.get(m2, 0.0) if thresholds else 0.0
            
            print(f"[DoubleExpressionPlot] Using thresholds: {m1}>{t1}, {m2}>{t2}")

            # Find X, Y
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
                msg = "[DoubleExpressionPlot] Could not find X/Y columns in the data file."
                print(msg)
                _notify_error(msg)
                return []

            # Plotting in two columns: main plot + dedicated legend column.
            fig, (ax, legend_ax) = plt.subplots(
                ncols=2,
                figsize=(12, 10),
                gridspec_kw={"width_ratios": [1.0, 0.30], "wspace": 0.03},
            )
            
            # 1. Background (All cells - Negative appearance)
            ax.scatter(df[x_col], df[y_col], c="#f0f0f0", s=1, label="Negative")

            # 2. Layer 1: M1 ONLY (Red)
            # Logic: (M1 > T1) AND (M2 <= T2)
            m1_only = df[(df[col1] > t1) & (df[col2] <= t2)]
            ax.scatter(m1_only[x_col], m1_only[y_col], c="red", s=3, alpha=0.8, label=f"{m1}+ only")

            # 3. Layer 2: M2 ONLY (Blue)
            # Logic: (M2 > T2) AND (M1 <= T1)
            m2_only = df[(df[col2] > t2) & (df[col1] <= t1)]
            ax.scatter(m2_only[x_col], m2_only[y_col], c="blue", s=3, alpha=0.8, label=f"{m2}+ only")

            # 4. Layer 3: DOUBLE POSITIVE (Green)
            # Logic: (M1 > T1) AND (M2 > T2)
            both_pos = df[(df[col1] > t1) & (df[col2] > t2)]
            ax.scatter(both_pos[x_col], both_pos[y_col], c="green", s=4, alpha=1.0, label="Double Positive")

            ax.set_aspect('equal')
            ax.set_title(f"Spatial Distribution\n{m1} (Red) | {m2} (Blue) | Both (Green)", fontsize=15)
            ax.set_xlabel(x_col)
            ax.set_ylabel(y_col)
            ax.invert_yaxis()

            ax.invert_yaxis()

            handles, labels = ax.get_legend_handles_labels()
            legend_ax.axis("off")
            legend_ax.legend(
                handles,
                labels,
                loc="upper left",
                frameon=True,
                facecolor="white",
                edgecolor="0.7",
                markerscale=4,
            )

            # Print Counts
            print(f"[DoubleExpressionPlot] {m1}+ only: {len(m1_only)}")
            print(f"[DoubleExpressionPlot] {m2}+ only: {len(m2_only)}")
            print(f"[DoubleExpressionPlot] Double + : {len(both_pos)}")

            # Save
            safe_name = sanitize_name_token(
                f"{m1}_{m2}_double_expression",
                fallback="double_expression",
            )
            output_file = temp_dir / f"{safe_name}.{export_format}"
            fig.savefig(str(output_file), dpi=150, bbox_inches="tight")
            plt.close(fig)

            return [output_file]

        except Exception as e:
            import traceback
            print(f"[DoubleExpressionPlot] Error: {e}")
            print(traceback.format_exc())
            _notify_error(f"Error in Double Expression Plot: {e}")
            return []


