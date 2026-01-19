"""Feature UI base classes for quantification."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Optional

from qtpy.QtWidgets import QComboBox, QFormLayout, QWidget

if TYPE_CHECKING:
    from ..frontend import QuantificationTab
    from ..frontend import FeatureUIContext


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

    def build_labels_widget(
        self,
        label_text: str,
        get_value: Optional[Callable[[], str]] = None,
        set_value: Optional[Callable[[str], None]] = None,
    ) -> None:
        """Build and attach a labels selection widget.

        Parameters
        ----------
        label_text : str
            Label shown for the combo box.
        get_value : callable, optional
            Getter returning the currently selected label name.
        set_value : callable, optional
            Setter called when the selection changes.
        """
        labels_form = QFormLayout()
        labels_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        labels_combo = RefreshingComboBox(
            refresh_callback=lambda combo_ref=None: self._refresh_labels_combo(
                labels_combo
            )
        )
        self._tab._configure_combo(labels_combo)
        if set_value is not None:
            labels_combo.currentTextChanged.connect(set_value)
        labels_form.addRow(label_text, labels_combo)
        labels_widget = QWidget()
        labels_widget.setLayout(labels_form)
        self._context.left_layout.insertWidget(1, labels_widget)
        self._ui["labels_widget"] = labels_widget
        if get_value is not None:
            current = get_value()
            if current:
                labels_combo.setCurrentText(current)

    def teardown(self) -> None:
        """Remove feature-specific widgets before rebuilding."""
        widget = self._ui.get("labels_widget")
        if widget is not None:
            self._context.left_layout.removeWidget(widget)
            widget.deleteLater()
        self._ui.clear()

    def _refresh_labels_combo(self, combo: QComboBox) -> None:
        """Refresh the labels combo with available layers.

        Parameters
        ----------
        combo : QComboBox
            Combo box to populate.
        """
        current = combo.currentText()
        combo.clear()
        viewer = self._tab._viewer
        if viewer is None:
            combo.addItem("Select labels")
            return
        for layer in viewer.layers:
            if layer.__class__.__name__ == "Labels":
                combo.addItem(layer.name)
        if current:
            index = combo.findText(current)
            if index != -1:
                combo.setCurrentIndex(index)


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
