"""Colocalization feature UI."""

from qtpy.QtWidgets import QComboBox, QFormLayout

from ..base import SenoQuantFeature
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
        coloc_a = QComboBox()
        coloc_b = QComboBox()
        self._tab._configure_combo(coloc_a)
        self._tab._configure_combo(coloc_b)
        coloc_a.currentIndexChanged.connect(
            lambda _index: self._on_combo_changed("labels_a_id", coloc_a)
        )
        coloc_b.currentIndexChanged.connect(
            lambda _index: self._on_combo_changed("labels_b_id", coloc_b)
        )
        form_layout.addRow("Labels A", coloc_a)
        form_layout.addRow("Labels B", coloc_b)
        left_dynamic_layout.addLayout(form_layout)
        self._ui["coloc_a_combo"] = coloc_a
        self._ui["coloc_b_combo"] = coloc_b
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
        """Enable/disable colocalization based on spot feature count.

        Parameters
        ----------
        tab : QuantificationTab
            Parent quantification tab instance.
        configs : list of FeatureUIContext
            Current feature contexts.
        """
        choices = cls._spot_feature_choices(configs)
        allow_coloc = len(choices) >= 2
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
            Display labels and feature ids for spot features.
        """
        choices = []
        for index, config in enumerate(configs, start=1):
            if config.state.type_name == cls.spot_feature_type:
                name = config.state.name.strip()
                label = name if name else f"Feature {index}"
                choices.append((f"{index}: {label}", config.state.feature_id))
        return choices

    def _update_choices(self, choices: list[tuple[str, str]]) -> None:
        """Populate colocalization combo boxes with new choices.

        Parameters
        ----------
        choices : list of tuple[str, str]
            Spot feature labels and ids to present.
        """
        data = self._state.data
        if not isinstance(data, ColocalizationFeatureData):
            return
        combos = []
        for key in ("coloc_a_combo", "coloc_b_combo"):
            combo = self._ui.get(key)
            if combo is None:
                continue
            combos.append(combo)
            current_id = (
                data.labels_a_id if key == "coloc_a_combo" else data.labels_b_id
            )
            combo.clear()
            if choices:
                for label, feature_id in choices:
                    combo.addItem(label, feature_id)
            else:
                combo.addItem("No spots features")
            if current_id:
                index = combo.findData(current_id)
                if index != -1:
                    combo.setCurrentIndex(index)
        if len(choices) >= 2 and len(combos) == 2:
            a_combo, b_combo = combos
            if a_combo.currentData() == b_combo.currentData():
                a_combo.setCurrentIndex(0)
                b_combo.setCurrentIndex(1)
        if len(combos) == 2:
            a_combo, b_combo = combos
            data.labels_a_id = a_combo.currentData()
            data.labels_b_id = b_combo.currentData()
        self._sync_choices()

    def _sync_choices(self) -> None:
        """Ensure colocalization combos cannot select the same feature."""
        coloc_a = self._ui.get("coloc_a_combo")
        coloc_b = self._ui.get("coloc_b_combo")
        if coloc_a is None or coloc_b is None:
            return
        self._disable_combo_choice(coloc_a, coloc_b.currentData())
        self._disable_combo_choice(coloc_b, coloc_a.currentData())

    def _on_combo_changed(self, key: str, combo: QComboBox) -> None:
        """Store selected combo data and resync unique choices."""
        data = self._state.data
        if not isinstance(data, ColocalizationFeatureData):
            return
        value = combo.currentData()
        if key == "labels_a_id":
            data.labels_a_id = value
        else:
            data.labels_b_id = value
        self._sync_choices()

    def _disable_combo_choice(self, combo: QComboBox, value) -> None:
        """Disable a combo-box option that matches the provided value.

        Parameters
        ----------
        combo : QComboBox
            Combo box to update.
        value : object
            Option value to disable.
        """
        model = combo.model()
        for index in range(combo.count()):
            item = model.item(index)
            if item is None:
                continue
            item.setEnabled(combo.itemData(index) != value)
