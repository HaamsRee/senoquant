"""Colocalization feature UI."""

from qtpy.QtWidgets import QComboBox, QFormLayout

from ..base import SenoQuantFeature


class ColocalizationFeature(SenoQuantFeature):
    """Colocalization feature controls."""

    feature_type = "Colocalization"
    order = 30
    spot_feature_type = "Spots"

    def build(self) -> None:
        """Build the colocalization feature UI."""
        left_dynamic_layout = self._config.get("left_dynamic_layout")
        if left_dynamic_layout is None:
            return
        form_layout = QFormLayout()
        form_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        coloc_a = QComboBox()
        coloc_b = QComboBox()
        self._tab._configure_combo(coloc_a)
        self._tab._configure_combo(coloc_b)
        coloc_a.currentTextChanged.connect(
            lambda _text: self._sync_choices()
        )
        coloc_b.currentTextChanged.connect(
            lambda _text: self._sync_choices()
        )
        form_layout.addRow("Labels A", coloc_a)
        form_layout.addRow("Labels B", coloc_b)
        left_dynamic_layout.addLayout(form_layout)
        self._config["coloc_a_combo"] = coloc_a
        self._config["coloc_b_combo"] = coloc_b
        self.on_features_changed(self._tab._feature_configs)

    def on_features_changed(self, configs: list[dict]) -> None:
        """Refresh colocalization options when feature list changes."""
        choices = self._spot_feature_choices(configs)
        self._update_choices(choices)

    @classmethod
    def update_type_options(cls, tab, configs: list[dict]) -> None:
        """Enable/disable colocalization based on spot feature count."""
        choices = cls._spot_feature_choices(configs)
        allow_coloc = len(choices) >= 2
        for config in configs:
            combo = config["type_combo"]
            idx = combo.findText(cls.feature_type)
            if idx != -1:
                combo.model().item(idx).setEnabled(allow_coloc)
            if combo.currentText() == cls.feature_type and not allow_coloc:
                combo.setCurrentIndex(0)

    @classmethod
    def _spot_feature_choices(cls, configs: list[dict]) -> list[str]:
        choices = []
        for index, config in enumerate(configs, start=1):
            if config["type_combo"].currentText() == cls.spot_feature_type:
                name = config["name_input"].text().strip()
                label = name if name else f"Feature {index}"
                choices.append(f"{index}: {label}")
        return choices

    def _update_choices(self, choices: list[str]) -> None:
        combos = []
        for key in ("coloc_a_combo", "coloc_b_combo"):
            combo = self._config.get(key)
            if combo is None:
                continue
            combos.append(combo)
            current = combo.currentText()
            combo.clear()
            if choices:
                combo.addItems(choices)
            else:
                combo.addItem("No spots features")
            if current:
                index = combo.findText(current)
                if index != -1:
                    combo.setCurrentIndex(index)
        if len(choices) >= 2 and len(combos) == 2:
            a_combo, b_combo = combos
            if a_combo.currentText() == b_combo.currentText():
                a_combo.setCurrentIndex(0)
                b_combo.setCurrentIndex(1)
        self._sync_choices()

    def _sync_choices(self) -> None:
        coloc_a = self._config.get("coloc_a_combo")
        coloc_b = self._config.get("coloc_b_combo")
        if coloc_a is None or coloc_b is None:
            return
        self._disable_combo_choice(coloc_a, coloc_b.currentText())
        self._disable_combo_choice(coloc_b, coloc_a.currentText())

    def _disable_combo_choice(self, combo: QComboBox, value: str) -> None:
        model = combo.model()
        for index in range(combo.count()):
            item = model.item(index)
            if item is None:
                continue
            item.setEnabled(combo.itemText(index) != value)
