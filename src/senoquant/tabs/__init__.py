"""Tab widgets for SenoQuant."""

from .segmentation.frontend import SegmentationTab
from .spots.frontend import SpotsTab
from .prediction.frontend import PredictionTab
from .quantification.frontend import QuantificationTab
from .visualization.frontend import VisualizationTab
from .settings.frontend import SettingsTab
from .batch.frontend import BatchTab

__all__ = [
    "SegmentationTab",
    "SpotsTab",
    "PredictionTab",
    "QuantificationTab",
    "VisualizationTab",
    "SettingsTab",
    "BatchTab",
]
