"""Visualization plot UI components."""

from __future__ import annotations

import importlib
import pkgutil
from typing import Iterable

from .base import PlotConfig, PlotData, SenoQuantPlot
from .spatialplot import SpatialPlotData
from .umap import UMAPData
from .double_expression import DoubleExpressionData


def _iter_subclasses(cls: type[SenoQuantPlot]) -> Iterable[type[SenoQuantPlot]]:
    """Yield all subclasses of a plot class recursively.

    Parameters
    ----------
    cls : type[SenoQuantPlot]
        Base class whose subclasses should be discovered.

    Yields
    ------
    type[SenoQuantPlot]
        Plot subclass types.
    """
    for subclass in cls.__subclasses__():
        yield subclass
        yield from _iter_subclasses(subclass)


def get_feature_registry() -> dict[str, type[SenoQuantPlot]]:
    """Discover plot classes and return a registry by name."""
    for module in pkgutil.walk_packages(__path__, f"{__name__}."):
        importlib.import_module(module.name)

    registry: dict[str, type[SenoQuantPlot]] = {}
    for plot_cls in _iter_subclasses(SenoQuantPlot):
        feature_type = getattr(plot_cls, "feature_type", "")
        if not feature_type:
            continue
        registry[feature_type] = plot_cls

    return dict(
        sorted(
            registry.items(),
            key=lambda item: getattr(item[1], "order", 0),
        )
    )

PLOT_DATA_FACTORY: dict[str, type[PlotData]] = {
    "UMAP": UMAPData,
    "Spatial Plot": SpatialPlotData,
    "Double Expression": DoubleExpressionData,
}


def build_plot_data(feature_type: str) -> PlotData:
    """Create a plot data instance for the specified plot type.

    Parameters
    ----------
    feature_type : str
        Plot type name.

    Returns
    -------
    PlotData
        Plot-specific configuration instance.
    """
    data_cls = PLOT_DATA_FACTORY.get(feature_type, PlotData)
    return data_cls()


__all__ = [
    "PlotConfig",
    "PlotData",
    "SenoQuantPlot",
    "build_plot_data",
    "get_feature_registry",
]
