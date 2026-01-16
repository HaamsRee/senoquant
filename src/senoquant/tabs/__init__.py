"""Tab widgets for SenoQuant."""

from .segmentation.frontend import SegmentationTab
from .spots.frontend import SpotsTab
from .quantify.frontend import QuantifyTab
from .settings.frontend import SettingsTab

__all__ = ["SegmentationTab", "SpotsTab", "QuantifyTab", "SettingsTab"]
