"""Spots channels dialog rows."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qtpy.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..base import RefreshingComboBox
from .config import SpotsChannelConfig, SpotsSegmentationConfig

if TYPE_CHECKING:
    from .dialog import SpotsChannelsDialog


class SpotsSegmentationRow(QGroupBox):
    """Segmentation row widget for spots segmentation filters."""

    def __init__(
        self, dialog: SpotsChannelsDialog, data: SpotsSegmentationConfig
    ) -> None:
        """Initialize a segmentation row widget.

        Parameters
        ----------
        dialog : SpotsChannelsDialog
            Parent dialog instance.
        data : SpotsSegmentationConfig
            Segmentation configuration data.
        """
        super().__init__()
        self._dialog = dialog
        self._tab = dialog._tab
        self.data = data

        self.setFlat(True)
        self.setStyleSheet(
            "QGroupBox {"
            "  margin-top: 6px;"
            "}"
            "QGroupBox::title {"
            "  subcontrol-origin: margin;"
            "  subcontrol-position: top left;"
            "  padding: 0 6px;"
            "}"
        )

        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        form_layout = QFormLayout()
        form_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        labels_combo = RefreshingComboBox(
            refresh_callback=lambda combo_ref=None: self._dialog._refresh_labels_combo(
                labels_combo, filter_type="cellular"
            )
        )
        self._tab._configure_combo(labels_combo)
        labels_combo.currentTextChanged.connect(
            lambda text: self._set_data("label", text)
        )

        form_layout.addRow("Segmentation", labels_combo)
        layout.addLayout(form_layout)

        delete_button = QPushButton("Delete")
        delete_button.clicked.connect(
            lambda: self._dialog._remove_segmentation(self)
        )
        layout.addWidget(delete_button)

        self._labels_combo = labels_combo
        self.setLayout(layout)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._restore_state()

    def update_title(self, index: int) -> None:
        """Update the title label for the segmentation row.

        Parameters
        ----------
        index : int
            0-based index used in the title.
        """
        self.setTitle(f"Segmentation {index}")

    def _set_data(self, key: str, value) -> None:
        """Update the segmentation data model.

        Parameters
        ----------
        key : str
            Data field name to update.
        value : object
            Value to assign to the field.
        """
        setattr(self.data, key, value)

    def _restore_state(self) -> None:
        """Restore UI state from stored segmentation data.

        Notes
        -----
        This sets the labels combo to the stored label name when available.
        """
        label_name = self.data.label
        if label_name:
            self._labels_combo.setCurrentText(label_name)
        return


class SpotsChannelRow(QGroupBox):
    """Channel row widget for spots feature channels."""

    def __init__(
        self, dialog: SpotsChannelsDialog, data: SpotsChannelConfig
    ) -> None:
        """Initialize a channel row widget.

        Parameters
        ----------
        dialog : SpotsChannelsDialog
            Parent dialog instance.
        data : SpotsChannelConfig
            Channel configuration data.
        """
        super().__init__()
        self._dialog = dialog
        self._tab = dialog._tab
        self.data = data

        self.setFlat(True)
        self.setStyleSheet(
            "QGroupBox {"
            "  margin-top: 6px;"
            "}"
            "QGroupBox::title {"
            "  subcontrol-origin: margin;"
            "  subcontrol-position: top left;"
            "  padding: 0 6px;"
            "}"
        )

        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        channel_form = QFormLayout()
        channel_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        name_input = QLineEdit()
        name_input.setPlaceholderText("Channel name")
        name_input.setMinimumWidth(160)
        name_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        name_input.textChanged.connect(
            lambda text: self._set_data("name", text)
        )
        channel_combo = RefreshingComboBox(
            refresh_callback=lambda combo_ref=None: self._dialog._refresh_image_combo(
                channel_combo
            )
        )
        self._tab._configure_combo(channel_combo)
        channel_combo.currentTextChanged.connect(
            lambda text: self._set_data("channel", text)
        )
        segmentation_combo = RefreshingComboBox(
            refresh_callback=lambda combo_ref=None: self._dialog._refresh_labels_combo(
                segmentation_combo, filter_type="spots"
            )
        )
        self._tab._configure_combo(segmentation_combo)
        segmentation_combo.currentTextChanged.connect(
            lambda text: self._set_data("spots_segmentation", text)
        )

        channel_form.addRow("Name", name_input)
        channel_form.addRow("Channel", channel_combo)
        channel_form.addRow("Spots segmentation", segmentation_combo)
        layout.addLayout(channel_form)

        delete_button = QPushButton("Delete")
        delete_button.clicked.connect(lambda: self._dialog._remove_channel(self))
        layout.addWidget(delete_button)

        self.setLayout(layout)

        self._channel_combo = channel_combo
        self._name_input = name_input
        self._segmentation_combo = segmentation_combo

        self._restore_state()
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def update_title(self, index: int) -> None:
        """Update the title label for the channel row.

        Parameters
        ----------
        index : int
            0-based index used in the title.
        """
        self.setTitle(f"Channel {index}")

    def _set_data(self, key: str, value) -> None:
        """Update the channel data model.

        Parameters
        ----------
        key : str
            Data key to update.
        value : object
            New value to store.
        """
        setattr(self.data, key, value)

    def _restore_state(self) -> None:
        """Restore UI state from stored channel data.

        Notes
        -----
        Populates name, channel, and segmentation combos when values are
        present in the configuration.
        """
        channel_label = self.data.name
        if channel_label:
            self._name_input.setText(channel_label)
        channel_name = self.data.channel
        if channel_name:
            self._channel_combo.setCurrentText(channel_name)
        segmentation_name = self.data.spots_segmentation
        if segmentation_name:
            self._segmentation_combo.setCurrentText(segmentation_name)
