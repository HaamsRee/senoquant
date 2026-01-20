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
    labels_a_id : str or None
        Feature id for the first spots feature.
    labels_b_id : str or None
        Feature id for the second spots feature.
    """

    labels_a_id: Optional[str] = None
    labels_b_id: Optional[str] = None
