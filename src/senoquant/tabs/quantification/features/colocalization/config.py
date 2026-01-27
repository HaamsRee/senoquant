"""Colocalization feature configuration models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..base import FeatureData


@dataclass
class ColocalizationFeatureData(FeatureData):
    """Configuration for colocalization feature inputs.

    Attributes
    ----------
    spots_feature_id : str or None
        Feature id for the spots feature used for colocalization.
    """

    spots_feature_id: Optional[str] = None
