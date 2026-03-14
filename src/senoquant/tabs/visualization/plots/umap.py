"""UMAP plot handler for visualization."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt
import pandas as pd
from umap import UMAP as UMAPReducer

import numpy as np
from sklearn.neighbors import NearestNeighbors
import igraph as ig
import leidenalg

from sklearn.preprocessing import StandardScaler

from .base import PlotData, SenoQuantPlot


class UMAPData(PlotData):
    """Configuration data for UMAP plot."""

    pass


class UMAPPlot(SenoQuantPlot):
    """UMAP dimensionality reduction plot handler."""

    plot_type = "UMAP"
    order = 1

    def build(self) -> None:
        """Build the UI for UMAP plot configuration."""
        # Minimal UI for now; can add controls for n_components, metric, etc. later
        pass

    def plot(
        self, 
        temp_dir: Path, 
        input_path: str, 
        export_format: str,
        markers: list[str] | None = None,
        thresholds: dict[str, float] | None = None,
        resolution: float = 0.1
    ) -> Iterable[Path]:
        """Generate UMAP plot from input CSV.

        Parameters
        ----------
        temp_dir : Path
            Temporary directory to write plot output.
        input_path : str
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
            print(f"[UMAPPlot] Starting with input_path={input_path}")
            # Find the first data file (CSV or Excel) in the input folder
            data_files = list(Path(input_path).glob("*.csv")) + list(Path(input_path).glob("*.xlsx")) + list(Path(input_path).glob("*.xls"))
            print(f"[UMAPPlot] Found {len(data_files)} data files")
            if not data_files:
                print(f"[UMAPPlot] No CSV/Excel files found in {input_path}")
                return []
            
            data_file = data_files[0]
            print(f"[UMAPPlot] Reading {data_file}")
            if data_file.suffix.lower() in ('.xlsx', '.xls'):
                df = pd.read_excel(data_file)
            else:
                df = pd.read_csv(data_file)
            print(f"[UMAPPlot] Loaded dataframe with shape {df.shape}")
            if df.empty:
                print(f"[UMAPPlot] DataFrame is empty")
                return []

            # Apply thresholds if provided
            if thresholds:
                for marker, thresh in thresholds.items():
                    col_name = f"{marker}_mean_intensity"
                    if col_name in df.columns:
                        # Clip values below threshold to 0
                        df.loc[df[col_name] < thresh, col_name] = 0

            # Select numeric columns for UMAP
            if markers:
                numeric_cols = [f"{m}_mean_intensity" for m in markers if f"{m}_mean_intensity" in df.columns]
                print(f"[UMAPPlot] Using {len(numeric_cols)} selected markers for UMAP")
            else:
                numeric_cols = df.select_dtypes(include=["number"]).columns
                print(f"[UMAPPlot] Found {len(numeric_cols)} numeric columns (default)")
            
            if len(numeric_cols) < 2:
                print(f"[UMAPPlot] Need at least 2 numeric columns for UMAP, found {len(numeric_cols)}")
                return []
            
            X_raw = df[numeric_cols].values
            n_samples = len(X_raw)

            # 1. Scale the data (Mandatory for diverse datasets)
            X = StandardScaler().fit_transform(X_raw)

            # 2. Fit UMAP 
            # UMAP can handle lower n_neighbors for visual local structure
            umap_neighbors = 15 if n_samples >= 15 else max(2, n_samples - 1)
            reducer = UMAPReducer(
                n_components=2,
                random_state=42,
                n_neighbors=umap_neighbors,
            )
            embedding = reducer.fit_transform(X)

            # 3. Build K-Nearest Neighbors Graph for Clustering
            # Use a higher k for the clustering graph to prevent micro-clusters
            # A good generic baseline for cellular data is 30, scaling up if data is huge
            cluster_neighbors = 30 if n_samples >= 30 else max(2, n_samples - 1)
            
            knn = NearestNeighbors(n_neighbors=cluster_neighbors).fit(X)
            distances, indices = knn.kneighbors(X)

            edges = []
            for i in range(n_samples):
                # Start at 1 to skip the self-loop (a point is always its own nearest neighbor)
                for j in indices[i][1:]:
                    edges.append((i, j))

            # 4. Run Leiden Clustering
            g = ig.Graph(n=n_samples, edges=edges, directed=False)
            g.simplify()

            # Resolution must remain a parameter. Default to 0.5 in your function signature.
            partition = leidenalg.find_partition(
                g, 
                leidenalg.RBConfigurationVertexPartition,
                resolution_parameter=resolution 
            )
            cluster_labels = np.array(partition.membership)
            
            # Assign clusters back to the dataframe (optional, but good for export later)
            df['Leiden_Cluster'] = cluster_labels
            unique_clusters = np.unique(cluster_labels)

            # 4. Create Plot
            fig, ax = plt.subplots(figsize=(10, 8))
            
            # Define a color map (tab20 can handle up to 20 distinct clusters)
            cmap = plt.cm.get_cmap('tab20', len(unique_clusters))

            # Scatter plot each cluster
            for cluster in unique_clusters:
                mask = cluster_labels == cluster
                ax.scatter(
                    embedding[mask, 0], 
                    embedding[mask, 1], 
                    color=cmap(cluster % 20), 
                    label=f"Cluster {cluster}", 
                    alpha=0.6, 
                    s=20
                )

                # Calculate the centroid of this cluster to place the label
                cx = np.median(embedding[mask, 0])
                cy = np.median(embedding[mask, 1])
                
                # Draw the cluster number on the map
                ax.text(
                    cx, cy, str(cluster), 
                    fontsize=12, weight='bold', ha='center', va='center',
                    bbox=dict(facecolor='white', alpha=0.7, edgecolor='black', boxstyle='round,pad=0.2')
                )

            # Finalize plot formatting
            ax.set_title("UMAP Plot with Leiden Clustering")
            ax.set_xlabel("UMAP 1")
            ax.set_ylabel("UMAP 2")
            
            # Add a legend outside the plot
            ax.legend(title="Leiden Clusters", bbox_to_anchor=(1.05, 1), loc='upper left')
            fig.tight_layout()

            # Save plot
            output_file = temp_dir / f"umap_leiden_plot.{export_format}"
            fig.savefig(str(output_file), dpi=150, bbox_inches="tight")
            plt.close(fig)

            return [output_file]

            # X = df[numeric_cols].values

            # # Fit UMAP
            # n_samples = len(X)
            # print(f"[UMAPPlot] Fitting UMAP with {n_samples} samples")

            # # Adjust settings for small datasets to prevent solver errors
            # n_neighbors = 15
            # init_method = "spectral"
            # if n_samples < 15:
            #     n_neighbors = max(2, n_samples - 1)
            #     init_method = "random"

            # reducer = UMAPReducer(
            #     n_components=2,
            #     random_state=42,
            #     n_neighbors=n_neighbors,
            #     init=init_method,
            # )
            # embedding = reducer.fit_transform(X)
            # print(f"[UMAPPlot] UMAP embedding created with shape {embedding.shape}")

            # # Create plot
            # fig, ax = plt.subplots(figsize=(8, 6))
            # ax.scatter(embedding[:, 0], embedding[:, 1], alpha=0.6, s=20)
            # ax.set_xlabel("UMAP 1")
            # ax.set_ylabel("UMAP 2")
            # ax.set_title("UMAP Plot")

            # # Save plot
            # output_file = temp_dir / f"umap_plot.{export_format}"
            # print(f"[UMAPPlot] Saving to {output_file}")
            # fig.savefig(str(output_file), dpi=150, bbox_inches="tight")
            # plt.close(fig)
            # print(f"[UMAPPlot] Plot saved successfully")

            # return [output_file]

        except Exception as e:
            import traceback
            print(f"[UMAPPlot] ERROR generating UMAP plot: {e}")
            print(traceback.format_exc())
            return []
