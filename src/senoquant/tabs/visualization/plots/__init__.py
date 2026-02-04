"""Visualization plot UI components."""

from __future__ import annotations

import importlib
import pkgutil
from typing import Iterable

from .base import PlotConfig, FeatureData, SenoQuantPlot
from .spatialplot import SpatialPlotData
from .umap import UMAPData


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

FEATURE_DATA_FACTORY: dict[str, type[FeatureData]] = {
    "UMAP": UMAPData,
    "Spatial Plot": SpatialPlotData,
}


def build_feature_data(feature_type: str) -> FeatureData:
    """Create a plot data instance for the specified plot type.

    Parameters
    ----------
    feature_type : str
        Plot type name.

    Returns
    -------
    FeatureData
        Plot-specific configuration instance.
    """
    data_cls = FEATURE_DATA_FACTORY.get(feature_type, FeatureData)
    return data_cls()


__all__ = [
    "PlotConfig",
    "FeatureData",
    "SenoQuantPlot",
    "build_feature_data",
    "get_feature_registry",
]
