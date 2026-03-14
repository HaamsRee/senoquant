"""Neighborhood enrichment plot handler."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree


if TYPE_CHECKING:
    from ..frontend import VisualizationTab, PlotUIContext

from .base import PlotData, SenoQuantPlot


class NeighborhoodEnrichmentData(PlotData):
    """Configuration data for neighborhood enrichment plot."""

    pass


def _find_xy_columns(df: pd.DataFrame) -> tuple[str | None, str | None]:
    """Infer X/Y coordinate columns from common naming patterns."""
    x_col = "centroid_x_pixels" if "centroid_x_pixels" in df.columns else None
    y_col = "centroid_y_pixels" if "centroid_y_pixels" in df.columns else None

    if x_col is not None and y_col is not None:
        return x_col, y_col

    x_candidates = [column for column in df.columns if "x" in column.lower()]
    patterns = [
        ("_x_", "_y_"),
        ("_X_", "_Y_"),
        ("_x", "_y"),
        ("_X", "_Y"),
        ("x_", "y_"),
        ("X_", "Y_"),
        ("x", "y"),
        ("X", "Y"),
    ]
    for x_candidate in x_candidates:
        for x_pattern, y_pattern in patterns:
            if x_pattern not in x_candidate:
                continue
            y_candidate = x_candidate.replace(x_pattern, y_pattern)
            if y_candidate in df.columns and y_candidate != x_candidate:
                return x_candidate, y_candidate
    return None, None


def _build_knn_edges(coords: np.ndarray, k: int) -> np.ndarray:
    """Return unique undirected edges from a k-NN graph."""
    n_points = coords.shape[0]
    if n_points < 2:
        return np.empty((0, 2), dtype=int)

    neighbor_count = min(k + 1, n_points)
    tree = cKDTree(coords)
    _, indices = tree.query(coords, k=neighbor_count)
    
    if indices.ndim == 1:
        indices = indices[:, None]

    if indices.shape[1] < 2:
        return np.empty((0, 2), dtype=int)

    # Vectorized edge construction: exclude self (col 0), flatten, and sort
    neighbors = indices[:, 1:]
    sources = np.repeat(np.arange(n_points), neighbors.shape[1])
    targets = neighbors.flatten()
    
    edges = np.column_stack((sources, targets))
    edges.sort(axis=1)
    
    return np.unique(edges, axis=0)


def _edge_count_matrix(edge_classes: np.ndarray, class_count: int) -> np.ndarray:
    """Build a symmetric class-by-class interaction count matrix."""
    if edge_classes.size == 0:
        return np.zeros((class_count, class_count), dtype=float)

    # Vectorized counting using bincount
    u = edge_classes[:, 0]
    v = edge_classes[:, 1]
    
    # Interleave (u, v) and (v, u) to fill symmetric matrix
    flat_indices = np.concatenate([
        u * class_count + v,
        v * class_count + u
    ])
    
    counts = np.bincount(flat_indices, minlength=class_count * class_count)
    return counts.reshape((class_count, class_count)).astype(float)


def _compute_enrichment_zscores(
    class_codes: np.ndarray,
    edges: np.ndarray,
    n_classes: int,
    n_permutations: int = 200,
    seed: int = 0,
) -> np.ndarray:
    """Compute neighborhood enrichment z-scores via label permutations."""
    if edges.size == 0 or n_classes == 0:
        return np.zeros((n_classes, n_classes), dtype=float)

    observed_edge_classes = class_codes[edges]
    observed = _edge_count_matrix(observed_edge_classes, n_classes)

    rng = np.random.default_rng(seed)
    permutation_totals = np.zeros((n_permutations, n_classes, n_classes), dtype=float)
    for index in range(n_permutations):
        shuffled = rng.permutation(class_codes)
        permutation_totals[index] = _edge_count_matrix(shuffled[edges], n_classes)

    perm_mean = permutation_totals.mean(axis=0)
    perm_std = permutation_totals.std(axis=0)
    zscores = np.divide(
        observed - perm_mean,
        perm_std,
        out=np.zeros_like(observed),
        where=perm_std > 0,
    )
    return zscores


def _resolve_marker_columns(
    df: pd.DataFrame,
    markers: list[str],
) -> tuple[list[str], list[str]]:
    """Resolve selected markers to available dataframe columns."""
    marker_names: list[str] = []
    marker_columns: list[str] = []
    for marker in markers:
        candidate = f"{marker}_mean_intensity"
        if candidate in df.columns:
            marker_names.append(marker)
            marker_columns.append(candidate)
        elif marker in df.columns:
            marker_names.append(marker)
            marker_columns.append(marker)
        else:
            print(f"[NeighborhoodPlot] Missing marker column for '{marker}', skipping.")
    return marker_names, marker_columns


class NeighborhoodEnrichmentPlot(SenoQuantPlot):
    """Neighborhood enrichment analysis from point coordinates and thresholds.

    Assigns cells to classes based on marker thresholds and computes
    neighborhood enrichment z-scores.
    """

    plot_type = "Neighborhood Enrichment"
    order = 3

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

    def __init__(self, frontend: VisualizationTab, context: PlotUIContext) -> None:
        super().__init__(frontend, context)
        self.frontend = frontend
        self.context = context

    def build(self) -> None:
        """Build the configuration UI for this plot."""
        pass


    def on_plots_changed(self, plots: list[PlotUIContext]) -> None:
        """Handle updates when the plot list changes."""
        pass

    @classmethod
    def update_type_options(cls, frontend: VisualizationTab, plots: list[PlotUIContext]) -> None:
        """Update available options based on other plots (unused)."""
        pass

    def plot(
        self,
        temp_dir: Path,
        input_path: Path,
        export_format: str,
        markers: list[str] | None = None,
        thresholds: dict[str, float] | None = None,
    ) -> list[Path]:
        """Generate the neighborhood enrichment plot."""
        if not markers:
            print("[NeighborhoodPlot] No markers selected.")
            return []

        # Resolve input file (prefer CSV, then Excel)
        input_path = Path(input_path)
        data_file = None
        if input_path.is_file():
            data_file = input_path
        elif input_path.is_dir():
            for ext in [".csv", ".xlsx", ".xls"]:
                found = list(input_path.glob(f"*{ext}"))
                if found:
                    data_file = found[0]
                    break
        
        if not data_file:
            print("[NeighborhoodPlot] No data file found.")
            return []

        # Load data
        try:
            if data_file.suffix == ".csv":
                df = pd.read_csv(data_file)
            else:
                df = pd.read_excel(data_file)
        except Exception as e:
            print(f"[NeighborhoodPlot] Error reading data: {e}")
            return []

        # Identify coordinate columns
        x_col, y_col = _find_xy_columns(df)
        if not x_col or not y_col:
            print("[NeighborhoodPlot] Centroid columns not found.")
            return []

        marker_names, marker_columns = _resolve_marker_columns(df, markers)
        if len(marker_columns) < 2:
            print("[NeighborhoodPlot] Need at least two selected markers with valid columns.")
            return []

        try:
            coords = df[[x_col, y_col]].to_numpy(dtype=float, copy=False)
            marker_values = df[marker_columns].apply(
                pd.to_numeric,
                errors="coerce",
            ).to_numpy(dtype=float, copy=False)

            valid = np.isfinite(coords).all(axis=1) & np.isfinite(marker_values).all(axis=1)
            coords = coords[valid]
            marker_values = marker_values[valid]
            if coords.shape[0] < 3:
                print("[NeighborhoodPlot] Not enough valid points for neighborhood graph.")
                return []

            class_codes = np.full(coords.shape[0], fill_value=-1, dtype=int)
            for idx, marker in enumerate(marker_names):
                threshold = self._threshold_for_marker(thresholds, marker)
                is_pos = marker_values[:, idx] > threshold
                take = is_pos & (class_codes < 0)
                class_codes[take] = idx

            other_code = len(marker_names)
            class_codes[class_codes < 0] = other_code
            class_names = marker_names + ["Other"]

            edges = _build_knn_edges(coords, k=6)
            if edges.size == 0:
                print("[NeighborhoodPlot] Could not build neighborhood graph.")
                return []

            zscores = _compute_enrichment_zscores(
                class_codes=class_codes,
                edges=edges,
                n_classes=len(class_names),
            )
        except Exception as e:
            print(f"[NeighborhoodPlot] Error in neighborhood computation: {e}")
            return []

        # Generate Plot
        output_filename = f"neighborhood_enrichment.{export_format}"
        output_path = temp_dir / output_filename

        fig, ax = plt.subplots(figsize=(6, 6))

        try:
            image = ax.imshow(zscores, cmap="bwr", aspect="equal")
            ax.set_xticks(range(len(class_names)))
            ax.set_xticklabels(class_names, rotation=45, ha="right")
            ax.set_yticks(range(len(class_names)))
            ax.set_yticklabels(class_names)
            ax.set_title("Neighborhood Enrichment (z-score)")
            fig.colorbar(image, ax=ax, label="z-score")
            for row in range(zscores.shape[0]):
                for col in range(zscores.shape[1]):
                    ax.text(
                        col,
                        row,
                        f"{zscores[row, col]:.1f}",
                        ha="center",
                        va="center",
                        fontsize=8,
                    )
            fig.tight_layout()
            fig.savefig(output_path, bbox_inches="tight")
            plt.close(fig)
        except Exception as e:
            print(f"[NeighborhoodPlot] Error plotting: {e}")
            # Close figure still
            plt.close(fig)
            return []

        return [output_path]
