"""Model-choice and settings behavior mixin for segmentation frontend."""

from __future__ import annotations

from qtpy.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
)


class SegmentationSettingsMixin:
    """Model selection and settings form behavior for segmentation tab."""

    def export_settings_state(self) -> dict[str, object]:
        """Return serializable segmentation settings state for persistence."""
        return {
            "nuclear": {
                "model": self._nuclear_model_combo.currentText(),
                "settings": self._collect_settings(self._nuclear_settings_widgets),
            },
            "cytoplasmic": {
                "model": self._cyto_model_combo.currentText(),
                "settings": self._collect_settings(self._cyto_settings_widgets),
            },
        }

    def apply_settings_state(self, payload: dict | None) -> None:
        """Apply serialized segmentation settings to the UI."""
        if not isinstance(payload, dict):
            return

        nuclear = payload.get("nuclear")
        if isinstance(nuclear, dict):
            model_name = str(nuclear.get("model", "")).strip()
            if model_name:
                self._set_combo_value(self._nuclear_model_combo, model_name)
            self._update_nuclear_model_settings(self._nuclear_model_combo.currentText())
            self._apply_settings_values(
                self._nuclear_settings_widgets,
                nuclear.get("settings"),
            )

        cytoplasmic = payload.get("cytoplasmic")
        if isinstance(cytoplasmic, dict):
            model_name = str(cytoplasmic.get("model", "")).strip()
            if model_name:
                self._set_combo_value(self._cyto_model_combo, model_name)
            self._update_cytoplasmic_model_settings(self._cyto_model_combo.currentText())
            self._apply_settings_values(
                self._cyto_settings_widgets,
                cytoplasmic.get("settings"),
            )

    def _refresh_model_choices(self) -> None:
        """Populate the model dropdowns from available model folders."""
        self._nuclear_model_combo.clear()
        self._cyto_model_combo.clear()

        nuclear_names = self._backend.list_model_names(task="nuclear")
        if not nuclear_names:
            self._nuclear_model_combo.addItem("No models found")
        else:
            self._nuclear_model_combo.addItems(nuclear_names)

        cyto_names = self._backend.list_model_names(task="cytoplasmic")
        if not cyto_names:
            self._cyto_model_combo.addItem("No models found")
        else:
            self._cyto_model_combo.addItems(cyto_names)

        if cyto_names:
            self._update_cytoplasmic_model_settings(self._cyto_model_combo.currentText())

    def _update_nuclear_model_settings(self, model_name: str) -> None:
        """Rebuild the nuclear model settings area for the selected model."""
        self._refresh_model_settings_layout(
            self._nuclear_model_settings_layout,
            model_name,
        )

    def _update_cytoplasmic_model_settings(self, model_name: str) -> None:
        """Rebuild the cytoplasmic model settings area for the selected model."""
        self._refresh_model_settings_layout(
            self._cyto_model_settings_layout,
            model_name,
        )

        if not model_name or model_name == "No models found":
            self._cyto_layer_combo.setVisible(True)
            self._cyto_layer_combo.setEnabled(False)
            self._cyto_nuclear_layer_combo.setEnabled(False)
            self._cyto_nuclear_label.setText("Nuclear layer")
            return

        model = self._backend.get_model(model_name)
        modes = model.cytoplasmic_input_modes()

        if modes == ["nuclear"]:
            self._cyto_layer_combo.setVisible(False)
            self._cyto_layer_label.setVisible(False)
            self._cyto_nuclear_layer_combo.setEnabled(True)
            self._cyto_nuclear_label.setText("Nuclear layer")
            self._refresh_nuclear_labels_for_cyto()
        elif "nuclear+cytoplasmic" in modes:
            self._cyto_layer_combo.setVisible(True)
            self._cyto_layer_label.setVisible(True)
            self._cyto_layer_combo.setEnabled(True)
            optional = model.cytoplasmic_nuclear_optional()
            suffix = "optional" if optional else "mandatory"
            self._cyto_nuclear_label.setText(f"Nuclear layer ({suffix})")
            self._cyto_nuclear_layer_combo.setEnabled(True)
            self._refresh_nuclear_images_for_cyto()
        else:
            self._cyto_layer_combo.setVisible(True)
            self._cyto_layer_label.setVisible(True)
            self._cyto_layer_combo.setEnabled(True)
            self._cyto_nuclear_label.setText("Nuclear layer")
            self._cyto_nuclear_layer_combo.setEnabled(False)
            self._refresh_nuclear_images_for_cyto()

        self._update_cytoplasmic_run_state(model)

    def _refresh_model_settings_layout(
        self,
        settings_layout: QVBoxLayout,
        model_name: str,
    ) -> None:
        """Rebuild the provided model settings area for the selected model."""
        self._clear_layout(settings_layout)

        if not model_name or model_name == "No models found":
            settings_layout.addWidget(
                QLabel("Select a model to configure its settings.")
            )
            return

        model = self._backend.get_model(model_name)
        settings_map = (
            self._nuclear_settings_widgets
            if settings_layout is self._nuclear_model_settings_layout
            else self._cyto_settings_widgets
        )
        settings_meta = (
            self._nuclear_settings_meta
            if settings_layout is self._nuclear_model_settings_layout
            else self._cyto_settings_meta
        )
        settings_map.clear()
        settings_meta.clear()
        form_layout = self._build_model_settings(
            model,
            settings_map,
            settings_meta,
        )
        if form_layout is None:
            settings_layout.addWidget(
                QLabel(f"No settings defined for '{model_name}'.")
            )
        else:
            settings_layout.addLayout(form_layout)

    def _update_cytoplasmic_run_state(self, model) -> None:
        """Enable/disable cytoplasmic run button based on required inputs."""
        modes = model.cytoplasmic_input_modes()

        if modes == ["nuclear"]:
            nuclear_layer = self._get_layer_by_name(
                self._cyto_nuclear_layer_combo.currentText()
            )
            self._cyto_run_button.setEnabled(nuclear_layer is not None)
            return

        if self._cyto_requires_nuclear(model):
            nuclear_layer = self._get_layer_by_name(
                self._cyto_nuclear_layer_combo.currentText()
            )
            self._cyto_run_button.setEnabled(nuclear_layer is not None)
        else:
            self._cyto_run_button.setEnabled(True)

    def _clear_layout(self, layout: QVBoxLayout) -> None:
        """Remove widgets and nested layouts from the provided layout."""
        while layout.count():
            item = layout.takeAt(0)
            child_layout = item.layout()
            if child_layout is not None:
                self._clear_layout(child_layout)
                continue
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _build_model_settings(
        self,
        model,
        settings_map: dict,
        settings_meta: dict,
    ) -> QFormLayout | None:
        """Build model settings controls from model metadata."""
        settings = model.list_settings()
        if not settings:
            return None

        form_layout = QFormLayout()
        for setting in settings:
            setting_type = setting.get("type")
            label = setting.get("label", setting.get("key", "Setting"))
            key = setting.get("key", label)
            settings_meta[key] = setting

            if setting_type == "float":
                widget = QDoubleSpinBox()
                decimals = int(setting.get("decimals", 1))
                widget.setDecimals(decimals)
                widget.setRange(
                    float(setting.get("min", 0.0)),
                    float(setting.get("max", 1.0)),
                )
                widget.setSingleStep(0.1)
                widget.setValue(float(setting.get("default", 0.0)))
                settings_map[key] = widget
                form_layout.addRow(label, widget)
            elif setting_type == "int":
                widget = QSpinBox()
                widget.setRange(
                    int(setting.get("min", 0)),
                    int(setting.get("max", 100)),
                )
                widget.setSingleStep(1)
                widget.setValue(int(setting.get("default", 0)))
                settings_map[key] = widget
                form_layout.addRow(label, widget)
            elif setting_type == "bool":
                widget = QCheckBox()
                widget.setChecked(bool(setting.get("default", False)))
                widget.toggled.connect(
                    lambda _checked, m=settings_map, meta=settings_meta: self._apply_setting_dependencies(  # noqa: E501
                        m,
                        meta,
                    )
                )
                settings_map[key] = widget
                form_layout.addRow(label, widget)
            else:
                form_layout.addRow(label, QLabel("Unsupported setting type"))

        self._apply_setting_dependencies(settings_map, settings_meta)
        return form_layout

    def _apply_setting_dependencies(
        self,
        settings_map: dict,
        settings_meta: dict,
    ) -> None:
        """Apply enabled/disabled relationships between settings."""
        for key, setting in settings_meta.items():
            widget = settings_map.get(key)
            if widget is None:
                continue

            enabled_by = setting.get("enabled_by")
            disabled_by = setting.get("disabled_by")

            if enabled_by:
                controller = settings_map.get(enabled_by)
                if isinstance(controller, QCheckBox):
                    widget.setEnabled(controller.isChecked())
            if disabled_by:
                controller = settings_map.get(disabled_by)
                if isinstance(controller, QCheckBox):
                    widget.setEnabled(not controller.isChecked())

    def _collect_settings(self, settings_map: dict) -> dict:
        """Collect current values from the settings widgets."""
        values = {}
        for key, widget in settings_map.items():
            if hasattr(widget, "value"):
                values[key] = widget.value()
            elif isinstance(widget, QCheckBox):
                values[key] = widget.isChecked()
        return values

    @staticmethod
    def _apply_settings_values(settings_map: dict, values: object) -> None:
        """Apply persisted values onto matching settings widgets."""
        if not isinstance(values, dict):
            return
        for key, value in values.items():
            widget = settings_map.get(key)
            if widget is None:
                continue
            if isinstance(widget, QCheckBox):
                widget.setChecked(bool(value))
                continue
            if hasattr(widget, "setValue"):
                try:
                    widget.setValue(value)
                except (TypeError, ValueError):
                    continue

    def _configure_combo(self, combo: QComboBox) -> None:
        """Apply sizing defaults to combo boxes."""
        combo.setSizeAdjustPolicy(
            QComboBox.AdjustToMinimumContentsLengthWithIcon
        )
        combo.setMinimumContentsLength(20)
        combo.setMinimumWidth(180)
        combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def _cyto_requires_nuclear(self, model) -> bool:
        """Return True when cytoplasmic mode requires a nuclear channel."""
        modes = model.cytoplasmic_input_modes()
        if modes == ["nuclear"]:
            return True
        if "nuclear+cytoplasmic" not in modes:
            return False
        return not model.cytoplasmic_nuclear_optional()

    def _on_cyto_nuclear_layer_changed(self) -> None:
        """React to cytoplasmic nuclear-layer combo changes."""
        model_name = self._cyto_model_combo.currentText()
        if not model_name or model_name == "No models found":
            self._cyto_run_button.setEnabled(False)
            return
        model = self._backend.get_model(model_name)
        self._update_cytoplasmic_run_state(model)

    @staticmethod
    def _set_combo_value(combo: QComboBox, value: str) -> None:
        """Select a combo value when present."""
        index = combo.findText(value)
        if index != -1:
            combo.setCurrentIndex(index)
