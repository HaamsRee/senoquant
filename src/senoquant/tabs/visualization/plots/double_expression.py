"""Double expression plot handler for visualization."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

try:
    from napari.utils.notifications import show_error
except ImportError:
    def show_error(message: str) -> None:
        pass

from .base import PlotData, SenoQuantPlot


class DoubleExpressionData(PlotData):
    """Configuration data for double expression plot."""

    pass


class DoubleExpressionPlot(SenoQuantPlot):
    """Spatial scatter plot highlighting double positive cells."""

    feature_type = "Double Expression"
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
                show_error(msg)
                return []
            try:
                import matplotlib.pyplot as plt
            except ImportError:
                msg = (
                    "[DoubleExpressionPlot] matplotlib is not installed; "
                    "skipping plot generation."
                )
                print(msg)
                show_error(msg)
                return []

            print(f"[DoubleExpressionPlot] Starting with input_path={input_path}")
            
            if not markers or len(markers) != 2:
                msg = f"Double Expression Plot requires exactly 2 markers. Got {len(markers) if markers else 0}."
                print(f"[DoubleExpressionPlot] {msg}")
                show_error(msg)
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
                show_error(msg)
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
                show_error(msg)
                return []

            # Plotting
            fig, ax = plt.subplots(figsize=(10, 10))
            
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

            # Custom Legend
            ax.legend(markerscale=4, loc='upper right', frameon=False)

            # Print Counts
            print(f"[DoubleExpressionPlot] {m1}+ only: {len(m1_only)}")
            print(f"[DoubleExpressionPlot] {m2}+ only: {len(m2_only)}")
            print(f"[DoubleExpressionPlot] Double + : {len(both_pos)}")

            # Save
            safe_name = f"{m1}_{m2}_double_expression"
            safe_name = "".join(c if c.isalnum() else "_" for c in safe_name)
            output_file = temp_dir / f"{safe_name}.{export_format}"
            fig.savefig(str(output_file), dpi=150, bbox_inches="tight")
            plt.close(fig)

            return [output_file]

        except Exception as e:
            import traceback
            print(f"[DoubleExpressionPlot] Error: {e}")
            print(traceback.format_exc())
            show_error(f"Error in Double Expression Plot: {e}")
            return []
