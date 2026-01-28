"""Quantification feature UI components."""

from __future__ import annotations

import importlib
import pkgutil
from typing import Iterable

from .base import FeatureConfig, FeatureData, SenoQuantFeature
from .marker.config import MarkerFeatureData
from .spots.config import SpotsFeatureData


def _iter_subclasses(cls: type[SenoQuantFeature]) -> Iterable[type[SenoQuantFeature]]:
    """Yield all subclasses of a feature class recursively.

    Parameters
    ----------
    cls : type[SenoQuantFeature]
        Base class whose subclasses should be discovered.

    Yields
    ------
    type[SenoQuantFeature]
        Feature subclass types.
    """
    for subclass in cls.__subclasses__():
        yield subclass
        yield from _iter_subclasses(subclass)


def get_feature_registry() -> dict[str, type[SenoQuantFeature]]:
    """Discover feature classes and return a registry by name."""
    for module in pkgutil.walk_packages(__path__, f"{__name__}."):
        importlib.import_module(module.name)

    registry: dict[str, type[SenoQuantFeature]] = {}
    for feature_cls in _iter_subclasses(SenoQuantFeature):
        feature_type = getattr(feature_cls, "feature_type", "")
        if not feature_type:
            continue
        registry[feature_type] = feature_cls

    return dict(
        sorted(
            registry.items(),
            key=lambda item: getattr(item[1], "order", 0),
        )
    )

FEATURE_DATA_FACTORY: dict[str, type[FeatureData]] = {
    "Markers": MarkerFeatureData,
    "Spots": SpotsFeatureData,
}


def build_feature_data(feature_type: str) -> FeatureData:
    """Create a feature data instance for the specified feature type.

    Parameters
    ----------
    feature_type : str
        Feature type name.

    Returns
    -------
    FeatureData
        Feature-specific configuration instance.
    """
    data_cls = FEATURE_DATA_FACTORY.get(feature_type, FeatureData)
    return data_cls()


__all__ = [
    "FeatureConfig",
    "FeatureData",
    "SenoQuantFeature",
    "build_feature_data",
    "get_feature_registry",
]
