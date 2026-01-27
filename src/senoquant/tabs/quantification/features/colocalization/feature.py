"""Colocalization feature UI."""

from qtpy.QtWidgets import QComboBox, QFormLayout

from ..base import SenoQuantFeature
from ..spots.config import SpotsFeatureData
from .config import ColocalizationFeatureData


class ColocalizationFeature(SenoQuantFeature):
    """Colocalization feature controls."""

    feature_type = "Colocalization"
    order = 30
    spot_feature_type = "Spots"

    def build(self) -> None:
        """Build the colocalization feature UI."""
        left_dynamic_layout = self._context.left_dynamic_layout
        form_layout = QFormLayout()
        form_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        spots_combo = QComboBox()
        self._tab._configure_combo(spots_combo)
        spots_combo.currentIndexChanged.connect(
            lambda _index: self._on_combo_changed(spots_combo)
        )
        form_layout.addRow("Spots feature", spots_combo)
        left_dynamic_layout.addLayout(form_layout)
        self._ui["spots_combo"] = spots_combo
        self.on_features_changed(self._tab._feature_configs)

    def on_features_changed(self, configs: list) -> None:
        """Refresh colocalization options when feature list changes.

        Parameters
        ----------
        configs : list of FeatureUIContext
            Current feature contexts.
        """
        choices = self._spot_feature_choices(configs)
        self._update_choices(choices)

    @classmethod
    def update_type_options(cls, tab, configs: list) -> None:
        """Enable/disable colocalization based on eligible spots features.

        Parameters
        ----------
        tab : QuantificationTab
            Parent quantification tab instance.
        configs : list of FeatureUIContext
            Current feature contexts.
        """
        choices = cls._spot_feature_choices(configs)
        allow_coloc = len(choices) >= 1
        for config in configs:
            combo = config.type_combo
            idx = combo.findText(cls.feature_type)
            if idx != -1:
                combo.model().item(idx).setEnabled(allow_coloc)
            if combo.currentText() == cls.feature_type and not allow_coloc:
                combo.setCurrentIndex(0)

    @classmethod
    def _spot_feature_choices(cls, configs: list) -> list[tuple[str, str]]:
        """Return labels for spot features available for colocalization.

        Parameters
        ----------
        configs : list of FeatureUIContext
            Current feature contexts.

        Returns
        -------
        list of tuple[str, str]
            Display labels and feature ids for spot features with >2 channels.
        """
        choices = []
        for index, config in enumerate(configs, start=0):
            if config.state.type_name != cls.spot_feature_type:
                continue
            data = config.state.data
            if not isinstance(data, SpotsFeatureData):
                continue
            if len(data.channels) < 2:
                continue
            name = config.state.name.strip()
            label = name if name else f"Feature {index}"
            choices.append((label, config.state.feature_id))
        return choices

    def _update_choices(self, choices: list[tuple[str, str]]) -> None:
        """Populate colocalization combo box with new choices.

        Parameters
        ----------
        choices : list of tuple[str, str]
            Spot feature labels and ids to present.
        """
        data = self._state.data
        if not isinstance(data, ColocalizationFeatureData):
            return
        combo = self._ui.get("spots_combo")
        if combo is None:
            return
        current_id = data.spots_feature_id
        combo.clear()
        if choices:
            for label, feature_id in choices:
                combo.addItem(label, feature_id)
        else:
            combo.addItem("No spots features with >2 channels")
        if current_id:
            index = combo.findData(current_id)
            if index != -1:
                combo.setCurrentIndex(index)
        data.spots_feature_id = combo.currentData()

    def _on_combo_changed(self, combo: QComboBox) -> None:
        """Store selected combo data."""
        data = self._state.data
        if not isinstance(data, ColocalizationFeatureData):
            return
        data.spots_feature_id = combo.currentData()
