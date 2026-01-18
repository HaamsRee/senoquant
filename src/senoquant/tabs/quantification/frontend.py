"""Frontend widget for the Quantification tab."""

from qtpy.QtCore import Qt, QTimer
from qtpy.QtGui import QGuiApplication
from qtpy.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QFrame,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .backend import QuantificationBackend


class QuantificationTab(QWidget):
    def __init__(self, backend: QuantificationBackend | None = None) -> None:
        super().__init__()
        self._backend = backend or QuantificationBackend()
        self._feature_inputs: list[QLineEdit] = []

        layout = QVBoxLayout()
        layout.addWidget(self._make_output_section())
        layout.addWidget(self._make_features_section())
        layout.addStretch(1)
        self.setLayout(layout)

    def _make_output_section(self) -> QGroupBox:
        """Build the output configuration section.

        Returns
        -------
        QGroupBox
            Group box containing output settings.
        """
        section = QGroupBox("Output")
        section_layout = QVBoxLayout()

        form_layout = QFormLayout()
        form_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self._save_name_input = QLineEdit()
        self._save_name_input.setPlaceholderText("Output name")
        self._save_name_input.setMinimumWidth(180)
        self._save_name_input.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Fixed
        )

        self._format_combo = QComboBox()
        self._format_combo.addItems(["csv", "xlsx"])
        self._configure_combo(self._format_combo)

        form_layout.addRow("Save name", self._save_name_input)
        form_layout.addRow("Format", self._format_combo)

        section_layout.addLayout(form_layout)
        section.setLayout(section_layout)
        return section

    def _make_features_section(self) -> QGroupBox:
        """Build the features configuration section.

        Returns
        -------
        QGroupBox
            Group box containing feature inputs.
        """
        section = QGroupBox("Features")
        section.setFlat(True)
        section.setStyleSheet(
            "QGroupBox {"
            "  margin-top: 8px;"
            "}"
            "QGroupBox::title {"
            "  subcontrol-origin: margin;"
            "  subcontrol-position: top left;"
            "  padding: 0 6px;"
            "}"
        )

        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)
        frame.setFrameShadow(QFrame.Plain)
        frame.setObjectName("features-section-frame")
        frame.setStyleSheet(
            "QFrame#features-section-frame {"
            "  border: 1px solid palette(mid);"
            "  border-radius: 4px;"
            "}"
        )

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._features_scroll_area = scroll_area

        features_container = QWidget()
        self._features_container = features_container
        features_container.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Fixed
        )
        self._features_layout = QVBoxLayout()
        self._features_layout.setContentsMargins(0, 0, 0, 0)
        self._features_layout.setSizeConstraint(QVBoxLayout.SetMinAndMaxSize)
        features_container.setLayout(self._features_layout)
        scroll_area.setWidget(features_container)

        frame_layout = QVBoxLayout()
        frame_layout.setContentsMargins(10, 12, 10, 10)
        frame_layout.addWidget(scroll_area)
        frame.setLayout(frame_layout)

        section_layout = QVBoxLayout()
        section_layout.setContentsMargins(8, 12, 8, 4)
        section_layout.addWidget(frame)

        self._add_feature_button = QPushButton("Add feature")
        self._add_feature_button.clicked.connect(self._add_feature_row)
        section_layout.addWidget(self._add_feature_button)
        section.setLayout(section_layout)

        self._add_feature_row()
        self._update_features_scroll_height()
        return section

    def showEvent(self, event) -> None:
        """Ensure the features list resizes on initial show."""
        super().showEvent(event)
        self._update_features_scroll_height()

    def resizeEvent(self, event) -> None:
        """Resize handler to keep the features list at half the window height."""
        super().resizeEvent(event)
        self._update_features_scroll_height()

    def _update_features_scroll_height(self) -> None:
        """Update the features scroll area height based on the window size."""
        if not hasattr(self, "_features_scroll_area"):
            return
        screen = self.window().screen() if self.window() is not None else None
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        screen_height = screen.availableGeometry().height() if screen else 720
        target_height = max(180, int(screen_height * 0.25))
        content_height = 0
        if hasattr(self, "_features_container"):
            self._features_container.adjustSize()
            content_height = self._features_container.sizeHint().height()
        frame = self._features_scroll_area.frameWidth() * 2
        height = max(0, min(target_height, content_height + frame))
        self._features_scroll_area.setUpdatesEnabled(False)
        if content_height + frame <= target_height:
            self._features_scroll_area.setVerticalScrollBarPolicy(
                Qt.ScrollBarAlwaysOff
            )
        else:
            self._features_scroll_area.setVerticalScrollBarPolicy(
                Qt.ScrollBarAsNeeded
            )
        self._features_scroll_area.setFixedHeight(height)
        self._features_scroll_area.setUpdatesEnabled(True)

    def _add_feature_row(self) -> None:
        """Add a new feature input row."""
        index = len(self._feature_inputs) + 1
        feature_section = QGroupBox(str(index))
        feature_section.setFlat(True)
        feature_section.setStyleSheet(
            "QGroupBox {"
            "  margin-top: 6px;"
            "}"
            "QGroupBox::title {"
            "  subcontrol-origin: margin;"
            "  subcontrol-position: top left;"
            "  padding: 0 6px;"
            "}"
        )

        section_layout = QVBoxLayout()
        input_field = QLineEdit()
        input_field.setPlaceholderText("Feature name")
        input_field.setMinimumWidth(180)
        input_field.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        section_layout.addWidget(input_field)
        feature_section.setLayout(section_layout)
        feature_section.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Fixed
        )

        self._features_layout.addWidget(feature_section)
        self._feature_inputs.append(input_field)
        self._features_layout.activate()
        QTimer.singleShot(0, self._update_features_scroll_height)

    def _configure_combo(self, combo: QComboBox) -> None:
        """Apply sizing defaults to combo boxes."""
        combo.setSizeAdjustPolicy(
            QComboBox.AdjustToMinimumContentsLengthWithIcon
        )
        combo.setMinimumContentsLength(8)
        combo.setMinimumWidth(140)
        combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
