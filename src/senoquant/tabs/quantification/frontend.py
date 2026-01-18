"""Frontend widget for the Quantification tab."""

from qtpy.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QFrame,
    QLineEdit,
    QPushButton,
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

        self._features_layout = QVBoxLayout()
        self._features_layout.setContentsMargins(10, 12, 10, 10)
        frame.setLayout(self._features_layout)

        section_layout = QVBoxLayout()
        section_layout.setContentsMargins(8, 12, 8, 4)
        section_layout.addWidget(frame)

        self._add_feature_button = QPushButton("Add feature")
        self._add_feature_button.clicked.connect(self._add_feature_row)
        section_layout.addWidget(self._add_feature_button)
        section.setLayout(section_layout)

        self._add_feature_row()
        return section

    def _add_feature_row(self) -> None:
        """Add a new feature input row."""
        input_field = QLineEdit()
        input_field.setPlaceholderText("Feature name")
        input_field.setMinimumWidth(180)
        input_field.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._features_layout.addWidget(input_field)
        self._feature_inputs.append(input_field)

    def _configure_combo(self, combo: QComboBox) -> None:
        """Apply sizing defaults to combo boxes."""
        combo.setSizeAdjustPolicy(
            QComboBox.AdjustToMinimumContentsLengthWithIcon
        )
        combo.setMinimumContentsLength(8)
        combo.setMinimumWidth(140)
        combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
