"""Feature UI base classes for quantification."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING
import uuid

from qtpy.QtWidgets import QComboBox

if TYPE_CHECKING:
    from ..frontend import QuantificationTab
    from ..frontend import FeatureUIContext


class FeatureData:
    """Base class for feature-specific configuration data.

    Notes
    -----
    Concrete feature data classes should inherit from this class so they can
    be stored on :class:`FeatureConfig`.
    """


@dataclass
class FeatureConfig:
    """Configuration for a single quantification feature.

    Attributes
    ----------
    feature_id : str
        Unique identifier for the feature instance.
    name : str
        User-facing name for the feature.
    type_name : str
        Feature type name (e.g., ``"Marker"``).
    data : FeatureData
        Feature-specific configuration payload.
    """

    feature_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    name: str = ""
    type_name: str = ""
    data: FeatureData = field(default_factory=FeatureData)


class SenoQuantFeature:
    """Base class for quantification feature UI."""

    feature_type: str = ""
    order: int = 0

    def __init__(self, tab: "QuantificationTab", context: "FeatureUIContext") -> None:
        """Initialize a feature with shared tab context.

        Parameters
        ----------
        tab : QuantificationTab
            Parent quantification tab instance.
        context : FeatureUIContext
            Feature UI context with configuration state.
        """
        self._tab = tab
        self._context = context
        self._state = context.state
        self._ui: dict[str, object] = {}

    def build(self) -> None:
        """Build the UI for this feature."""
        raise NotImplementedError

    def on_features_changed(self, configs: list["FeatureUIContext"]) -> None:
        """Handle updates when the feature list changes.

        Parameters
        ----------
        configs : list of FeatureUIContext
            Current feature contexts.
        """
        return

    @classmethod
    def update_type_options(
        cls, tab: "QuantificationTab", configs: list["FeatureUIContext"]
    ) -> None:
        """Update type availability in feature selectors.

        Parameters
        ----------
        tab : QuantificationTab
            Parent quantification tab instance.
        configs : list of FeatureUIContext
            Current feature contexts.
        """
        return


class RefreshingComboBox(QComboBox):
    """Combo box that refreshes its items when opened."""

    def __init__(self, refresh_callback=None, parent=None) -> None:
        """Create a combo box that refreshes before showing its popup.

        Parameters
        ----------
        refresh_callback : callable or None
            Callback invoked before showing the popup.
        parent : QWidget or None
            Optional parent widget.
        """
        super().__init__(parent)
        self._refresh_callback = refresh_callback

    def showPopup(self) -> None:
        """Refresh items before showing the popup."""
        if self._refresh_callback is not None:
            self._refresh_callback()
        super().showPopup()
