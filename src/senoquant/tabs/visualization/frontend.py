"""Frontend widget for the Visualization tab."""

from dataclasses import dataclass
import json
from pathlib import Path
import pandas as pd
import shutil
from qtpy.QtCore import Qt, QTimer
from qtpy.QtGui import QGuiApplication, QPixmap
from qtpy.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .backend import VisualizationBackend
from .plots import PlotConfig, build_plot_data, get_feature_registry
from .plots.base import RefreshingComboBox


@dataclass
class PlotUIContext:
    """UI context for a single plot row."""

    state: PlotConfig
    section: QGroupBox
    type_combo: QComboBox
    left_dynamic_layout: QVBoxLayout
    left_layout: QVBoxLayout
    right_layout: QVBoxLayout
    plot_handler: object | None = None


class VisualizationTab(QWidget):
    """Visualization tab UI for configuring plot generation.

    Parameters
    ----------
    backend : VisualizationBackend or None
        Backend instance for visualization workflows.
    napari_viewer : object or None
        Napari viewer used to populate layer dropdowns.
    """
    def __init__(
        self,
        backend: VisualizationBackend | None = None,
        napari_viewer=None,
        *,
        show_output_section: bool = True,
        show_process_button: bool = True,
        # enable_rois: bool = True,
        show_right_column: bool = True,
        enable_thresholds: bool = True,
    ) -> None:
        """Initialize the visualization tab UI.

        Parameters
        ----------
        backend : VisualizationBackend or None
            Backend instance for visualization workflows.
        napari_viewer : object or None
            Napari viewer used to populate layer dropdowns.
        show_output_section : bool, optional
            Whether to show the output configuration controls.
        show_process_button : bool, optional
            Whether to show the process button.
        # enable_rois : bool, optional
        #     Whether to show ROI configuration controls within features.
        show_right_column : bool, optional
            Whether to show the right-hand feature column.
        enable_thresholds : bool, optional
            Whether to show threshold controls within features.
        """
        super().__init__()
        self._backend = backend or VisualizationBackend()
        self._viewer = napari_viewer
        # self._enable_rois = enable_rois
        self._show_right_column = show_right_column
        self._enable_thresholds = enable_thresholds
        self._feature_configs: list[PlotUIContext] = []
        self._feature_registry = get_feature_registry()
        self._features_watch_timer: QTimer | None = None
        self._features_last_size: tuple[int, int] | None = None

        layout = QVBoxLayout()
        
        layout.addWidget(self._make_input_section())
        layout.addWidget(self._make_marker_section())
        layout.addWidget(self._make_plots_section())
        
        # Add plot display area
        layout.addWidget(self._make_plot_display_section(show_process_button))
        
        if show_output_section:
            layout.addWidget(self._make_output_section())
        
        layout.addStretch(1)
        self.setLayout(layout)

    def _make_input_section(self) -> QGroupBox:
        """Build the input configuration section."""
        section = QGroupBox("Input")
        section_layout = QVBoxLayout()
        form_layout = QFormLayout()
        form_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self._input_path = QLineEdit()
        self._input_path.setPlaceholderText("Folder with quantification files")
        browse_button = QPushButton("Browse")
        browse_button.clicked.connect(self._select_input_path)
        input_row = QHBoxLayout()
        input_row.setContentsMargins(0, 0, 0, 0)
        input_row.addWidget(self._input_path)
        input_row.addWidget(browse_button)
        input_widget = QWidget()
        input_widget.setLayout(input_row)
        self._input_path.textChanged.connect(self._on_input_path_changed)

        self._extensions = QLineEdit()
        self._extensions.setText(".csv, .xlsx, .xls")

        form_layout.addRow("Input folder", input_widget)
        form_layout.addRow("Extensions", self._extensions)

        section_layout.addLayout(form_layout)
        section.setLayout(section_layout)
        return section

    def _make_marker_section(self) -> QGroupBox:
        """Build the marker selection and thresholding section."""
        section = QGroupBox("Marker selection && thresholding")
        layout = QVBoxLayout()

        # Add Select/Deselect buttons
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 8, 0, 5)
        sel_all = QPushButton("Select All")
        sel_all.clicked.connect(self._select_all_markers)
        desel_all = QPushButton("Deselect All")
        desel_all.clicked.connect(self._deselect_all_markers)
        btn_layout.addWidget(sel_all)
        btn_layout.addWidget(desel_all)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self._marker_table = QTableWidget()
        self._marker_table.setColumnCount(3)
        self._marker_table.setHorizontalHeaderLabels(["Include", "Marker", "Threshold"])
        
        header = self._marker_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        
        # Hide vertical header
        self._marker_table.verticalHeader().setVisible(False)
        
        layout.addWidget(self._marker_table)
        section.setLayout(layout)
        return section

    def _on_input_path_changed(self, path_text: str) -> None:
        """Handle input path changes to populate markers."""
        path = Path(path_text)
        if not path.exists() or not path.is_dir():
            return

        # Find first CSV or Excel file
        data_file = None
        for ext in [".csv", ".xlsx", ".xls"]:
            found = list(path.glob(f"*{ext}"))
            if found:
                data_file = found[0]
                break
        
        if data_file:
            self._populate_markers_from_file(data_file)
            
            # Look for JSON thresholds
            json_files = list(path.glob("*.json"))
            target_json = None
            if json_files:
                # Prioritize files with 'threshold' in the name
                for jf in json_files:
                    if "threshold" in jf.name.lower():
                        target_json = jf
                        break
                if not target_json:
                    target_json = json_files[0]
                self._load_thresholds_from_json(target_json)

    def _populate_markers_from_file(self, file_path: Path) -> None:
        """Read header from file and populate marker table."""
        try:
            if file_path.suffix == ".csv":
                df = pd.read_csv(file_path, nrows=0)
            else:
                df = pd.read_excel(file_path, nrows=0)
            
            markers = set()
            for col in df.columns:
                if "_mean_intensity" in col:
                    # Extract marker name (first part)
                    marker = col.split("_mean_intensity")[0]
                    markers.add(marker)
            
            self._marker_table.setRowCount(0)
            for i, marker in enumerate(sorted(markers)):
                self._marker_table.insertRow(i)
                
                # Checkbox
                chk_item = QTableWidgetItem()
                chk_item.setCheckState(Qt.Checked)
                chk_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
                self._marker_table.setItem(i, 0, chk_item)
                
                # Marker Name
                name_item = QTableWidgetItem(marker)
                name_item.setFlags(Qt.ItemIsEnabled)
                self._marker_table.setItem(i, 1, name_item)
                
                # Threshold Input
                thresh_input = QLineEdit()
                thresh_input.setPlaceholderText("Auto")
                self._marker_table.setCellWidget(i, 2, thresh_input)
                
        except Exception as e:
            print(f"Error populating markers: {e}")

    def _load_thresholds_from_json(self, json_path: Path) -> None:
        """Load thresholds from a JSON file."""
        try:
            print(f"[Frontend] Loading thresholds from {json_path}")
            with open(json_path, "r") as f:
                data = json.load(f)
            
            thresholds_map = {}
            
            # Handle SenoQuant export format (dict with "channels" list)
            if isinstance(data, dict) and "channels" in data and isinstance(data["channels"], list):
                for ch in data["channels"]:
                    name = ch.get("name") or ch.get("channel")
                    if not name:
                        continue
                    
                    # Replicate sanitization to match CSV headers
                    safe_name = "".join(
                        c if c.isalnum() or c in "-_ " else "_" for c in name
                    ).strip().replace(" ", "_").lower()
                    
                    # Prefer threshold_min
                    val = ch.get("threshold_min")
                    if val is None:
                        val = ch.get("threshold")
                    
                    if val is not None:
                        thresholds_map[safe_name] = val
                        thresholds_map[name] = val
            
            # Handle simple key-value format
            elif isinstance(data, dict):
                thresholds_map = data
            
            # Iterate over table rows and set thresholds if found
            for row in range(self._marker_table.rowCount()):
                marker_item = self._marker_table.item(row, 1)
                if not marker_item:
                    continue
                marker = marker_item.text()
                
                val = None
                if marker in thresholds_map:
                    val = thresholds_map[marker]
                elif f"{marker}_mean_intensity" in thresholds_map:
                    val = thresholds_map[f"{marker}_mean_intensity"]
                
                if val is not None:
                    widget = self._marker_table.cellWidget(row, 2)
                    if isinstance(widget, QLineEdit):
                        widget.setText(str(val))
        except Exception as e:
            print(f"Error loading thresholds from JSON: {e}")

    def _select_all_markers(self) -> None:
        """Select all markers in the table."""
        for row in range(self._marker_table.rowCount()):
            item = self._marker_table.item(row, 0)
            if item:
                item.setCheckState(Qt.Checked)

    def _deselect_all_markers(self) -> None:
        """Deselect all markers in the table."""
        for row in range(self._marker_table.rowCount()):
            item = self._marker_table.item(row, 0)
            if item:
                item.setCheckState(Qt.Unchecked)

    def _get_marker_settings(self) -> tuple[list[str], dict[str, float]]:
        """Retrieve selected markers and their thresholds from the table."""
        selected_markers = []
        thresholds = {}
        
        for row in range(self._marker_table.rowCount()):
            # Check if selected
            chk_item = self._marker_table.item(row, 0)
            if not chk_item or chk_item.checkState() != Qt.Checked:
                continue
            
            # Get marker name
            name_item = self._marker_table.item(row, 1)
            if not name_item:
                continue
            marker = name_item.text()
            selected_markers.append(marker)
            
            # Get threshold
            thresh_widget = self._marker_table.cellWidget(row, 2)
            if isinstance(thresh_widget, QLineEdit):
                text = thresh_widget.text().strip()
                if text:
                    try:
                        val = float(text)
                        thresholds[marker] = val
                    except ValueError:
                        pass # Ignore invalid numbers
                        
        return selected_markers, thresholds

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

        self._output_path_input = QLineEdit()
        default_output = str(Path.cwd())
        self._output_path_input.setText(default_output)
        self._output_path_input.setPlaceholderText("Output folder path")
        browse_button = QPushButton("Browse")
        browse_button.clicked.connect(self._select_output_path)
        output_path_row = QHBoxLayout()
        output_path_row.setContentsMargins(0, 0, 0, 0)
        output_path_row.addWidget(self._output_path_input)
        output_path_row.addWidget(browse_button)
        output_path_widget = QWidget()
        output_path_widget.setLayout(output_path_row)

        self._save_name_input = QLineEdit()
        self._save_name_input.setPlaceholderText("Plot name")
        self._save_name_input.setMinimumWidth(180)
        self._save_name_input.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Fixed
        )

        self._format_combo = QComboBox()
        self._format_combo.addItems(["png", "svg", "pdf"])
        self._configure_combo(self._format_combo)

        form_layout.addRow("Output path", output_path_widget)
        form_layout.addRow("Plot name", self._save_name_input)
        form_layout.addRow("Format", self._format_combo)

        section_layout.addLayout(form_layout)
        
        # Add Save button
        save_button = QPushButton("Save Plot")
        save_button.clicked.connect(self._save_plots)
        section_layout.addWidget(save_button)
        self._save_button = save_button
        
        section.setLayout(section_layout)
        return section
    
    def _make_plot_display_section(self, show_process_button: bool = True) -> QGroupBox:
        """Build the plot display section.

        Parameters
        ----------
        show_process_button : bool, optional
            Whether to show the Process button.

        Returns
        -------
        QGroupBox
            Group box containing generated plot images and process button.
        """
        section = QGroupBox("Plot Preview")
        section_layout = QVBoxLayout()
        
        # Create a resizable widget for displaying plots (no scrolling)
        self._plot_display_widget = QWidget()
        self._plot_display_widget.setMinimumHeight(200)
        self._plot_display_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._plot_display_layout = QVBoxLayout()
        self._plot_display_layout.setContentsMargins(0, 0, 0, 0)
        self._plot_display_layout.setSpacing(6)
        self._plot_display_widget.setLayout(self._plot_display_layout)
        section_layout.addWidget(self._plot_display_widget)
        
        # Add Process button
        if show_process_button:
            process_button = QPushButton("Process")
            process_button.clicked.connect(self._process_features)
            section_layout.addWidget(process_button)
            self._process_button = process_button
        
        section.setLayout(section_layout)
        return section
    

    def _make_plots_section(self) -> QGroupBox:
        """Build the plots configuration section.

        Returns
        -------
        QGroupBox
            Group box containing plot inputs.
        """
        section = QGroupBox("Plots")
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
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._features_scroll_area = scroll_area

        features_container = QWidget()
        self._features_container = features_container
        features_container.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Minimum
        )
        features_container.setMinimumWidth(200)
        self._features_min_width = 200
        self._features_layout = QVBoxLayout()
        self._features_layout.setContentsMargins(0, 0, 0, 0)
        self._features_layout.setSpacing(8)
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

        section.setLayout(section_layout)

        self._add_feature_row()
        self._apply_features_layout()
        self._start_features_watch()
        return section

    def showEvent(self, event) -> None:
        """Ensure layout sizing is applied on initial show.

        Parameters
        ----------
        event : QShowEvent
            Qt show event passed by the widget.
        """
        super().showEvent(event)
        self._apply_features_layout()

    def resizeEvent(self, event) -> None:
        """Resize handler to keep the features list at a capped height.

        Parameters
        ----------
        event : QResizeEvent
            Qt resize event passed by the widget.
        """
        super().resizeEvent(event)
        self._apply_features_layout()
        # Rescale any preview images to fit the new size
        try:
            self._rescale_all_plot_labels()
        except Exception:
            pass

    def _add_feature_row(self, state: PlotConfig | None = None) -> None:
        """Add a new feature input row."""
        if isinstance(state, bool):
            state = None
        
        section_layout = QVBoxLayout()

        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)
        content_layout.setAlignment(Qt.AlignTop)
        left_layout = QVBoxLayout()
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)
        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        form_layout = QFormLayout()
        form_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        type_combo = RefreshingComboBox(
            refresh_callback=self._notify_features_changed
        )
        feature_types = self._feature_types()
        type_combo.addItems(feature_types)
        self._configure_combo(type_combo)

        form_layout.addRow("Plot Type", type_combo)
        left_layout.addLayout(form_layout)

        left_dynamic_container = QWidget()
        left_dynamic_container.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Fixed
        )
        left_dynamic_layout = QVBoxLayout()
        left_dynamic_layout.setContentsMargins(0, 0, 0, 0)
        left_dynamic_layout.setSpacing(6)
        left_dynamic_container.setLayout(left_dynamic_layout)
        left_layout.addWidget(left_dynamic_container)

        left_container = QWidget()
        left_container.setLayout(left_layout)
        left_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        right_container = QWidget()
        right_container.setLayout(right_layout)
        right_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self._left_container = left_container
        self._right_container = right_container

        content_layout.addWidget(left_container, 3)
        if self._show_right_column:
            content_layout.addWidget(right_container, 2)
        section_layout.addLayout(content_layout)
        self._apply_features_layout()

        # Determine feature type first
        feature_type = (
            state.type_name
            if state is not None and state.type_name
            else type_combo.currentText()
        )
        if state is None:
            state = PlotConfig(
                type_name=feature_type,
                data=build_plot_data(feature_type),
            )
        if feature_type in feature_types:
            type_combo.blockSignals(True)
            type_combo.setCurrentText(feature_type)
            type_combo.blockSignals(False)

        # Create feature section with feature type as title
        feature_section = QGroupBox()
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
        feature_section.setLayout(section_layout)
        feature_section.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Fixed
        )

        self._features_layout.addWidget(feature_section)
        context = PlotUIContext(
            state=state,
            section=feature_section,
            type_combo=type_combo,
            left_dynamic_layout=left_dynamic_layout,
            left_layout=left_layout,
            right_layout=right_layout,
        )
        self._feature_configs.append(context)
        type_combo.currentTextChanged.connect(
            lambda _text, ctx=context: self._on_feature_type_changed(ctx)
        )
        self._build_feature_handler(context, preserve_data=True)
        self._notify_features_changed()
        self._features_layout.activate()
        QTimer.singleShot(0, self._apply_features_layout)

    def _on_feature_type_changed(self, context: PlotUIContext) -> None:
        """Update a plot section when its type changes.

        Parameters
        ----------
        context : PlotUIContext
            Plot UI context and data.
        """
        self._build_feature_handler(context, preserve_data=False)

    def _build_feature_handler(
        self,
        context: PlotUIContext,
        *,
        preserve_data: bool,
    ) -> None:
        left_dynamic_layout = context.left_dynamic_layout
        self._clear_layout(left_dynamic_layout)
        self._clear_layout(context.right_layout)
        feature_type = context.type_combo.currentText()
        context.state.type_name = feature_type
        if not preserve_data:
            context.state.data = build_plot_data(feature_type)

        feature_handler = self._feature_handler_for_type(feature_type, context)
        print(f"[Frontend] Built handler for {feature_type}: {feature_handler}")
        context.plot_handler = feature_handler
        if feature_handler is not None:
            feature_handler.build()
            print(f"[Frontend] Handler build() called")
        else:
            print(f"[Frontend] Handler is None!")
        self._notify_features_changed()


    def _notify_features_changed(self) -> None:
        """Notify plot handlers that the plot list has changed."""
        for feature_cls in self._feature_registry.values():
            feature_cls.update_type_options(self, self._feature_configs)
        for context in self._feature_configs:
            handler = context.plot_handler
            if handler is not None:
                handler.on_features_changed(self._feature_configs)
        # Update default plot name shown in the output section
        self._update_default_plot_name()

    def _update_default_plot_name(self) -> None:
        """Compute and set a sensible default for the Plot name field.

        Uses the joined feature type names separated by hyphens. Only sets
        the field when the user has not provided a custom name (empty) or
        when the current value matches the previous auto-generated value.
        """
        try:
            names = [ctx.state.type_name for ctx in self._feature_configs if getattr(ctx, 'state', None)]
            if not names:
                auto = "visualization"
            else:
                auto = "-".join(names)
            current = self._save_name_input.text().strip() if hasattr(self, '_save_name_input') else ''
            prev_auto = getattr(self, '_plot_name_auto', '')
            if not current or current == prev_auto:
                self._save_name_input.setText(auto)
                self._plot_name_auto = auto
        except Exception:
            # Fail silently; this is only a nicety
            pass

    def _feature_types(self) -> list[str]:
        """Return the available feature type names."""
        return list(self._feature_registry.keys())

    def load_feature_configs(self, configs: list[PlotConfig]) -> None:
        """Replace the current plot list with provided configs."""
        for context in list(self._feature_configs):
            self._remove_feature(context.section)
        if not configs:
            self._add_feature_row()
            return
        for config in configs:
            self._add_feature_row(config)

    def _select_input_path(self) -> None:
        """Open a folder picker for the input path."""
        path = QFileDialog.getExistingDirectory(self, "Select input folder")
        if path:
            self._input_path.setText(path)

    def _select_output_path(self) -> None:
        """Open a folder selection dialog for the output path."""
        path = QFileDialog.getExistingDirectory(
            self,
            "Select output folder",
            self._output_path_input.text(),
        )
        if path:
            self._output_path_input.setText(path)

    def _process_features(self) -> None:
        """Trigger visualization processing for configured plots."""
        # Clear previous plots
        while self._plot_display_layout.count():
            child = self._plot_display_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        
        print(f"[Frontend] Processing {len(self._feature_configs)} plot configs")
        for i, cfg in enumerate(self._feature_configs):
            print(f"[Frontend]   Config {i}: type={cfg.state.type_name}, handler={cfg.plot_handler}")
        
        # Clean up previous result temp files if they exist
        if hasattr(self, "_last_visualization_result") and self._last_visualization_result:
            try:
                shutil.rmtree(self._last_visualization_result.temp_root, ignore_errors=True)
            except Exception as e:
                print(f"[Frontend] Warning: Failed to cleanup previous temp dir: {e}")

        markers, thresholds = self._get_marker_settings()

        process = getattr(self._backend, "process", None)
        if callable(process):
            input_path = Path(self._input_path.text())
            result = process(
                self._feature_configs,
                input_path,
                self._output_path_input.text(),
                self._save_name_input.text(),
                self._format_combo.currentText(),
                markers=markers,
                thresholds=thresholds,
                save=False,
                cleanup=False,
            )
            
            # Store result for later saving
            self._last_visualization_result = result
            
            print(f"[Frontend] Process returned result: {result}")
            print(f"[Frontend] Output root: {result.output_root if result else 'None'}")
            
            # Display generated plots using the backend-returned final paths
            if result and hasattr(result, "plot_outputs"):
                print(f"[Frontend] Found {len(result.plot_outputs)} plot outputs")
                for plot_output in result.plot_outputs:
                    for output_file in getattr(plot_output, "outputs", []):
                        try:
                            output_file = Path(output_file)
                        except Exception:
                            output_file = None
                        if output_file and output_file.exists() and output_file.suffix.lower() in [".png", ".svg", ".pdf"]:
                            print(f"[Frontend] Displaying: {output_file}")
                            self._display_plot_file(output_file)
                        else:
                            print(f"[Frontend] Skipping non-existent or unsupported file: {output_file}")

    def _plot_dir_name(self, plot_output: object) -> str:
        """Build filesystem-friendly folder name for a plot (matches backend)."""
        plot_type = getattr(plot_output, "plot_type", "unknown")
        name = plot_type.strip()
        safe = "".join(
            c if c.isalnum() or c in " -_" else "_" for c in name
        )
        return safe

    def _save_plots(self) -> None:
        """Save the current plot results to the output directory."""
        if not hasattr(self, "_last_visualization_result") or self._last_visualization_result is None:
            print("No plots to save. Run Process first.")
            return
        
        result = self._last_visualization_result
        output_root = result.output_root
        
        # Perform the save using the backend
        if hasattr(self._backend, "save_result"):
            self._backend.save_result(
                result,
                self._output_path_input.text(),
                self._save_name_input.text()
            )
            
        saved_files: list[str] = []
        for plot_output in getattr(result, "plot_outputs", []):
            for p in getattr(plot_output, "outputs", []):
                try:
                    path = Path(p)
                except Exception:
                    continue
                if path.exists():
                    saved_files.append(str(path))

        if saved_files:
            print(f"Plots saved to: {output_root}")
            for f in saved_files:
                print(f" - {f}")
        else:
            # No files present: re-run process to force saving 
            markers, thresholds = self._get_marker_settings()
            process = getattr(self._backend, "process", None)
            if callable(process):
                result = process(
                    self._feature_configs,
                    Path(self._input_path.text()),
                    self._output_path_input.text(),
                    self._save_name_input.text(),
                    self._format_combo.currentText(),
                    markers=markers,
                    thresholds=thresholds,
                    save=True,
                    cleanup=True,
                )
                self._last_visualization_result = result
                print(f"Re-run complete. Check folder: {self._output_path_input.text() or Path.cwd()}")

    def _feature_handler_for_type(
        self, feature_type: str, context: PlotUIContext
    ):
        """Return the feature handler for a given feature type.

        Parameters
        ----------
        feature_type : str
            Selected feature type.
        config : dict
            Feature configuration dictionary.

        Returns
        -------
        SenoQuantFeature or None
            Feature handler instance for the selected type.
        """
        feature_cls = self._feature_registry.get(feature_type)
        if feature_cls is None:
            return None
        return feature_cls(self, context)

    def _display_plot_file(self, file_path) -> None:
        """Display a plot image file in the preview area.

        Parameters
        ----------
        file_path : Path or str
            Path to the plot image file (PNG or SVG).
        """
        from pathlib import Path
        file_path = Path(file_path)
        
        if file_path.suffix.lower() == ".png":
            # Display PNG directly and scale to fit preview widget
            pixmap = QPixmap(str(file_path))
            if not pixmap.isNull():
                label = QLabel()
                label.setAlignment(Qt.AlignCenter)
                label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                # store original pixmap for later rescaling
                label._orig_pixmap = pixmap
                # scale now to current widget size
                self._rescale_plot_label(label)
                self._plot_display_layout.addWidget(label)
        elif file_path.suffix.lower() == ".svg":
            # For SVG, display filename with link
            link_label = QLabel(f'<a href="file:///{file_path}">View {file_path.name}</a>')
            link_label.setOpenExternalLinks(True)
            self._plot_display_layout.addWidget(link_label)
        elif file_path.suffix.lower() == ".pdf":
            # For PDF, display filename with link
            link_label = QLabel(f'<a href="file:///{file_path}">View {file_path.name}</a>')
            link_label.setOpenExternalLinks(True)
            self._plot_display_layout.addWidget(link_label)

    def _rescale_plot_label(self, label: QLabel) -> None:
        """Rescale a QLabel containing an original QPixmap to fit preview area."""
        try:
            orig = getattr(label, "_orig_pixmap", None)
            if orig is None:
                return
            max_w = max(10, self._plot_display_widget.width() - 20)
            max_h = max(10, self._plot_display_widget.height() - 20)
            scaled = orig.scaled(max_w, max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            label.setPixmap(scaled)
        except Exception:
            pass

    def _rescale_all_plot_labels(self) -> None:
        """Rescale all displayed plot labels to fit the preview area."""
        for i in range(self._plot_display_layout.count()):
            item = self._plot_display_layout.itemAt(i)
            widget = item.widget() if item is not None else None
            if isinstance(widget, QLabel) and hasattr(widget, "_orig_pixmap"):
                self._rescale_plot_label(widget)

    def _configure_combo(self, combo: QComboBox) -> None:
        """Apply sizing defaults to combo boxes.

        Parameters
        ----------
        combo : QComboBox
            Combo box to configure.
        """
        combo.setSizeAdjustPolicy(
            QComboBox.AdjustToMinimumContentsLengthWithIcon
        )
        combo.setMinimumContentsLength(8)
        combo.setMinimumWidth(140)
        combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def _clear_layout(self, layout: QVBoxLayout) -> None:
        """Remove all widgets and layouts from a layout.

        Parameters
        ----------
        layout : QVBoxLayout
            Layout to clear.
        """
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            child_layout = item.layout()
            if child_layout is not None:
                self._clear_layout(child_layout)

    def _feature_index(self, context: PlotUIContext) -> int:
        """Return the 0-based index for a plot config.

        Parameters
        ----------
        context : PlotUIContext
            Plot UI context.

        Returns
        -------
        int
            0-based index of the plot.
        """
        return self._feature_configs.index(context)
    def _start_features_watch(self) -> None:
        """Start a timer to monitor feature sizing changes.

        The watcher polls for content size changes and reapplies layout
        constraints without blocking the UI thread.
        """
        if self._features_watch_timer is not None:
            return
        self._features_watch_timer = QTimer(self)
        self._features_watch_timer.setInterval(150)
        self._features_watch_timer.timeout.connect(self._poll_features_geometry)
        self._features_watch_timer.start()

    def _poll_features_geometry(self) -> None:
        """Recompute layout sizing when content size changes."""
        if not hasattr(self, "_features_scroll_area"):
            return
        size = self._features_content_size()
        if size == self._features_last_size:
            return
        self._features_last_size = size
        self._apply_features_layout(size)

    def _apply_features_layout(
        self, content_size: tuple[int, int] | None = None
    ) -> None:
        """Apply sizing rules for the features container and scroll area.

        Parameters
        ----------
        content_size : tuple of int or None
            Optional (width, height) of the features content. If None, the
            size is computed from the current layout.
        """
        if not hasattr(self, "_features_scroll_area"):
            return
        if content_size is None:
            content_size = self._features_content_size()
        content_width, content_height = content_size

        total_min = getattr(self, "_features_min_width", 0)
        if total_min <= 0 and hasattr(self, "_features_container"):
            total_min = self._features_container.minimumWidth()
        left_hint = 0
        right_hint = 0
        if hasattr(self, "_left_container") and self._left_container is not None:
            try:
                left_hint = self._left_container.sizeHint().width()
            except RuntimeError:
                self._left_container = None
        if hasattr(self, "_right_container") and self._right_container is not None:
            try:
                right_hint = self._right_container.sizeHint().width()
            except RuntimeError:
                self._right_container = None
        left_min = max(int(total_min * 0.6), left_hint)
        right_min = max(int(total_min * 0.4), right_hint)
        if self._left_container is not None:
            try:
                self._left_container.setMinimumWidth(left_min)
            except RuntimeError:
                self._left_container = None
        if self._right_container is not None:
            try:
                self._right_container.setMinimumWidth(right_min)
            except RuntimeError:
                self._right_container = None

        if hasattr(self, "_features_container"):
            self._features_container.setMinimumHeight(0)
            self._features_container.setMinimumWidth(
                max(total_min, content_width)
            )
            self._features_container.updateGeometry()

        screen = self.window().screen() if self.window() is not None else None
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        screen_height = screen.availableGeometry().height() if screen else 720
        target_height = max(180, int(screen_height * 0.5))
        frame = self._features_scroll_area.frameWidth() * 2
        scroll_slack = 2
        effective_height = content_height + scroll_slack
        height = max(0, min(target_height, effective_height + frame))
        self._features_scroll_area.setUpdatesEnabled(False)
        self._features_scroll_area.setFixedHeight(height)
        self._features_scroll_area.setUpdatesEnabled(True)
        self._features_scroll_area.updateGeometry()
        widget = self._features_scroll_area.widget()
        if widget is not None:
            widget.adjustSize()
            widget.updateGeometry()
        self._features_scroll_area.viewport().updateGeometry()
        bar = self._features_scroll_area.verticalScrollBar()
        if bar.maximum() > 0:
            self._features_scroll_area.setVerticalScrollBarPolicy(
                Qt.ScrollBarAsNeeded
            )
        else:
            self._features_scroll_area.setVerticalScrollBarPolicy(
                Qt.ScrollBarAlwaysOff
            )
            bar.setRange(0, 0)
            bar.setValue(0)

    def _features_content_size(self) -> tuple[int, int]:
        """Compute the content size for the features layout.

        Returns
        -------
        tuple of int
            (width, height) of the content.
        """
        if not hasattr(self, "_features_layout"):
            return (0, 0)
        layout = self._features_layout
        layout.activate()
        margins = layout.contentsMargins()
        spacing = layout.spacing()
        count = layout.count()
        total_height = margins.top() + margins.bottom()
        max_width = 0
        for index in range(count):
            item = layout.itemAt(index)
            widget = item.widget()
            if widget is None:
                item_size = item.sizeHint()
            else:
                widget.adjustSize()
                item_size = widget.sizeHint().expandedTo(
                    widget.minimumSizeHint()
                )
            max_width = max(max_width, item_size.width())
            total_height += item_size.height()
        if count > 1:
            total_height += spacing * (count - 1)
        total_width = margins.left() + margins.right() + max_width
        if hasattr(self, "_features_container"):
            self._features_container.adjustSize()
            container_size = self._features_container.sizeHint().expandedTo(
                self._features_container.minimumSizeHint()
            )
            total_width = max(total_width, container_size.width())
            total_height = max(total_height, container_size.height())
        return (total_width, total_height)
