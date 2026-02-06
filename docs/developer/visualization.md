# Visualization tab

This guide covers architecture and extension points for the Visualization tab.

## Module layout

Visualization code lives in:

- `src/senoquant/tabs/visualization/frontend.py`
- `src/senoquant/tabs/visualization/backend.py`
- `src/senoquant/tabs/visualization/plots/`

Key responsibilities:

- `frontend.py`:
  - Builds the Qt UI (`VisualizationTab`).
  - Collects marker selections and thresholds.
  - Runs preview generation and save actions.
- `backend.py`:
  - Orchestrates plot handler execution.
  - Routes temporary outputs into final files.
- `plots/`:
  - Contains plot handler implementations.
  - Handles dynamic plot discovery and registration.

## Plot discovery and state

Plot classes are discovered dynamically by `get_feature_registry()` in
`src/senoquant/tabs/visualization/plots/__init__.py`.

Discovery behavior:

- Imports all modules under `plots/`.
- Collects subclasses of `SenoQuantPlot`.
- Uses each class `feature_type` as the dropdown key.
- Sorts by class attribute `order`.

Plot runtime state is stored in `PlotConfig`:

- `plot_id`: stable identifier for the configured row.
- `type_name`: selected plot type.
- `data`: plot-specific payload (`PlotData` subclass).

`FEATURE_DATA_FACTORY` maps plot type names to typed `PlotData` classes.

## Runtime flow

Single run flow:

1. `VisualizationTab._process_features()` gathers selected markers and thresholds.
2. It calls `VisualizationBackend.process(..., save=False, cleanup=False)`.
3. Backend calls each handler's `plot(temp_dir, input_path, export_format, markers, thresholds)`.
4. Returned paths are stored in `VisualizationResult.plot_outputs`.
5. Frontend renders preview files from those output paths.

Save flow:

1. `VisualizationTab._save_plots()` calls `VisualizationBackend.save_result(...)`.
2. Backend routes/copies files to the chosen output directory.
3. Output paths in `PlotExportResult.outputs` are updated to final destinations.

## Plot handler contract

Plot handlers subclass `SenoQuantPlot` from
`src/senoquant/tabs/visualization/plots/base.py`.

Required class attributes:

- `feature_type`: user-facing plot name in the dropdown.
- `order`: integer sort key in the registry.

Required methods:

- `build(self)`: build plot-specific controls (optional if no custom UI).
- `plot(self, temp_dir, input_path, export_format, markers=None, thresholds=None)`:
  generate outputs and return an iterable of `Path`.

Behavior notes:

- Handlers may return explicit output paths, or return `[]` and write files into `temp_dir`.
- Backend will fallback to routing all files in `temp_dir` when explicit paths are not returned.

## Adding a new visualization plot

1. Add a module under `src/senoquant/tabs/visualization/plots/`.
2. Define a `PlotData` subclass if typed state is needed.
3. Implement a `SenoQuantPlot` subclass with `feature_type` and `order`.
4. Implement `plot(...)` to produce outputs in the provided `temp_dir`.
5. Register typed data in `FEATURE_DATA_FACTORY` when applicable.
6. Add tests under `tests/senoquant/tabs/visualization/`.

Minimal skeleton:

```python
from pathlib import Path
from typing import Iterable

from senoquant.tabs.visualization.plots.base import PlotData, SenoQuantPlot


class MyPlotData(PlotData):
    pass


class MyPlot(SenoQuantPlot):
    feature_type = "My Plot"
    order = 30

    def build(self) -> None:
        pass

    def plot(
        self,
        temp_dir: Path,
        input_path: Path,
        export_format: str,
        markers: list[str] | None = None,
        thresholds: dict[str, float] | None = None,
    ) -> Iterable[Path]:
        output_file = temp_dir / f"my_plot.{export_format}"
        # write output_file
        return [output_file]
```

## Dependency notes

Dependency loading is currently mixed:

- `SpatialPlot` and `DoubleExpressionPlot` import `pandas`/`matplotlib`
  inside `plot()`.
- `UMAPPlot` imports `pandas`, `matplotlib`, and `umap-learn` at module load
  time (`src/senoquant/tabs/visualization/plots/umap.py`).

When adding new dependencies:

- Prefer local imports inside handler methods.
- Gracefully return `[]` with a clear message when dependency import fails.
