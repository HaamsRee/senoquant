"""Tab widgets for SenoQuant."""

from .segmentation.frontend import SegmentationTab
from .spots.frontend import SpotsTab
from .quantification.frontend import QuantificationTab
from .settings.frontend import SettingsTab

__all__ = ["SegmentationTab", "SpotsTab", "QuantificationTab", "SettingsTab"]
