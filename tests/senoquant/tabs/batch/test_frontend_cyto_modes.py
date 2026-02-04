"""Tests for batch cytoplasmic input-mode handling."""

from __future__ import annotations

from qtpy.QtWidgets import QComboBox

from senoquant.tabs.batch.config import BatchChannelConfig
from senoquant.tabs.batch.frontend import BatchTab


class _Toggle:
    def __init__(self, checked: bool) -> None:
        self._checked = checked

    def isChecked(self) -> bool:
        return self._checked


class _ModelCombo:
    def __init__(self, text: str) -> None:
        self._text = text

    def currentText(self) -> str:
        return self._text


class _CytoModel:
    def __init__(self, modes: list[str], optional: bool) -> None:
        self._modes = modes
        self._optional = optional

    def cytoplasmic_input_modes(self) -> list[str]:
        return list(self._modes)

    def cytoplasmic_nuclear_optional(self) -> bool:
        return self._optional


def test_refresh_channel_choices_uses_nuclear_labels_for_nuclear_only_mode() -> None:
    """Populate cytoplasmic nuclear selector from generated nuclear labels."""
    tab = BatchTab.__new__(BatchTab)
    tab._refreshing_channel_choices = False
    tab._channel_configs = [BatchChannelConfig(name="Ch0", index=0)]
    tab._cyto_nuclear_optional = False
    tab._cyto_nuclear_from_labels = True
    tab._nuclear_enabled = _Toggle(True)
    tab._nuclear_model_combo = _ModelCombo("nuc_model")

    tab._nuclear_channel_combo = QComboBox()
    tab._nuclear_channel_combo.addItems(["old", "Ch0"])
    tab._nuclear_channel_combo.setCurrentText("Ch0")
    tab._cyto_channel_combo = QComboBox()
    tab._cyto_nuclear_combo = QComboBox()

    tab._refresh_channel_choices()

    assert tab._cyto_nuclear_combo.currentText() == "Ch0_nuc_model_nuc_labels"
    assert tab._cyto_nuclear_combo.findText("(no nuclear labels)") == -1


def test_refresh_channel_choices_uses_placeholder_when_no_nuclear_labels() -> None:
    """Show explicit placeholder when nuclear-only model has no label source."""
    tab = BatchTab.__new__(BatchTab)
    tab._refreshing_channel_choices = False
    tab._channel_configs = [BatchChannelConfig(name="Ch0", index=0)]
    tab._cyto_nuclear_optional = False
    tab._cyto_nuclear_from_labels = True
    tab._nuclear_enabled = _Toggle(False)
    tab._nuclear_model_combo = _ModelCombo("nuc_model")

    tab._nuclear_channel_combo = QComboBox()
    tab._nuclear_channel_combo.addItems(["Ch0"])
    tab._nuclear_channel_combo.setCurrentText("Ch0")
    tab._cyto_channel_combo = QComboBox()
    tab._cyto_nuclear_combo = QComboBox()

    tab._refresh_channel_choices()

    assert tab._cyto_nuclear_combo.currentText() == "(no nuclear labels)"
    assert tab._cyto_nuclear_combo.findText("(no nuclear labels)") != -1


def test_cyto_requires_nuclear_matches_mode_contract() -> None:
    """Require nuclear input for nuclear-only and required dual-input modes."""
    nuclear_only = _CytoModel(["nuclear"], optional=False)
    required_dual = _CytoModel(["nuclear+cytoplasmic"], optional=False)
    optional_dual = _CytoModel(["nuclear+cytoplasmic"], optional=True)
    cyto_only = _CytoModel(["cytoplasmic"], optional=True)

    assert BatchTab._cyto_requires_nuclear(nuclear_only) is True
    assert BatchTab._cyto_requires_nuclear(required_dual) is True
    assert BatchTab._cyto_requires_nuclear(optional_dual) is False
    assert BatchTab._cyto_requires_nuclear(cyto_only) is False
