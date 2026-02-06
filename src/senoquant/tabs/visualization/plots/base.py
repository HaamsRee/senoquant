"""Feature UI base classes for visualization."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Iterable
import uuid

from qtpy.QtWidgets import QComboBox

if TYPE_CHECKING:
    from ..frontend import VisualizationTab
    from ..frontend import PlotUIContext


class PlotData:
    """Base class for plot-specific configuration data.

    Notes
    -----
    Concrete plot data classes should inherit from this class so they can
    be stored on :class:`PlotConfig`.
    """


@dataclass
class PlotConfig:
    """Configuration for a single visualization plot.

    Attributes
    ----------
    plot_id : str
        Unique identifier for the plot instance.
    type_name : str
        Plot type name (e.g., ``"UMAP"``).
    data : PlotData
        Plot-specific configuration payload.
    """

    plot_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    type_name: str = ""
    data: PlotData = field(default_factory=PlotData)


class SenoQuantPlot:
    """Base class for visualization plot UI."""

    feature_type: str = ""
    order: int = 0

    def __init__(self, tab: "VisualizationTab", context: "PlotUIContext") -> None:
        """Initialize a plot with shared tab context.

        Parameters
        ----------
        tab : VisualizationTab
            Parent visualization tab instance.
        context : PlotUIContext
            Plot UI context with configuration state.
        """
        self._tab = tab
        self._context = context
        self._state = context.state
        self._ui: dict[str, object] = {}

    def build(self) -> None:
        """Build the UI for this plot."""
        raise NotImplementedError

    def plot(
        self, 
        temp_dir: Path, 
        input_path: str, 
        export_format: str,
        markers: list[str] | None = None,
        thresholds: dict[str, float] | None = None,
    ) -> Iterable[Path]:
        """Generate plot outputs into a temporary directory.

        Parameters
        ----------
        temp_dir : Path
            Temporary directory where outputs should be written.
        input_path : str
            Path to the input CSV file for plotting.
        export_format : str
            File format requested by the user (``"png"`` or ``"svg"``).
        markers : list of str, optional
            List of selected markers to include.
        thresholds : dict, optional
            Dictionary of {marker_name: threshold_value} for filtering.

        Returns
        -------
        iterable of Path
            Paths to files produced by the plot routine.

        Notes
        -----
        Implementations may either return explicit file paths or simply
        write outputs into ``temp_dir`` and return an empty iterable.
        """
        return []

    def on_features_changed(self, configs: list["PlotUIContext"]) -> None:
        """Handle updates when the plot list changes.

        Parameters
        ----------
        configs : list of PlotUIContext
            Current plot contexts.
        """
        return

    @classmethod
    def update_type_options(
        cls, tab: "VisualizationTab", configs: list["PlotUIContext"]
    ) -> None:
        """Update type availability in plot selectors.

        Parameters
        ----------
        tab : VisualizationTab
            Parent visualization tab instance.
        configs : list of PlotUIContext
            Current plot contexts.
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
