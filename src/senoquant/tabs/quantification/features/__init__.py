"""Quantification feature UI components."""

from __future__ import annotations

import importlib
import pkgutil
from typing import Iterable

from .base import SenoQuantFeature


def _iter_subclasses(cls: type[SenoQuantFeature]) -> Iterable[type[SenoQuantFeature]]:
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


__all__ = ["SenoQuantFeature", "get_feature_registry"]
