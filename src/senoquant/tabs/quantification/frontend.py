"""Frontend widget for the Quantification tab."""

from dataclasses import dataclass
from qtpy.QtCore import QObject, QThread, Qt, QTimer, Signal
from qtpy.QtGui import QGuiApplication
from qtpy.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

try:
    from napari.utils.notifications import (
        Notification,
        NotificationSeverity,
        show_console_notification,
    )
except Exception:  # pragma: no cover - optional import for runtime
    show_console_notification = None
    Notification = None
    NotificationSeverity = None

from .backend import QuantificationBackend
from .features import FeatureConfig, build_feature_data, get_feature_registry
from .features.base import RefreshingComboBox


@dataclass
class FeatureUIContext:
    """UI context for a single feature row."""

    state: FeatureConfig
    section: QGroupBox
    name_input: QLineEdit
    type_combo: QComboBox
    left_dynamic_layout: QVBoxLayout
    left_layout: QVBoxLayout
    right_layout: QVBoxLayout
    feature_handler: object | None = None


class QuantificationTab(QWidget):
    """Quantification tab UI for configuring feature extraction.

    Parameters
    ----------
    backend : QuantificationBackend or None
        Backend instance for quantification workflows.
    napari_viewer : object or None
        Napari viewer used to populate layer dropdowns.
    """
    def __init__(
        self,
        backend: QuantificationBackend | None = None,
        napari_viewer=None,
        *,
        show_output_section: bool = True,
        show_process_button: bool = True,
        enable_rois: bool = True,
        show_right_column: bool = True,
        enable_thresholds: bool = True,
    ) -> None:
        """Initialize the quantification tab UI.

        Parameters
        ----------
        backend : QuantificationBackend or None
            Backend instance for quantification workflows.
        napari_viewer : object or None
            Napari viewer used to populate layer dropdowns.
        show_output_section : bool, optional
            Whether to show the output configuration controls.
        show_process_button : bool, optional
            Whether to show the process button.
        enable_rois : bool, optional
            Whether to show ROI configuration controls within features.
        show_right_column : bool, optional
            Whether to show the right-hand feature column.
        enable_thresholds : bool, optional
            Whether to show threshold controls within features.
        """
        super().__init__()
        self._backend = backend or QuantificationBackend()
        self._viewer = napari_viewer
        self._enable_rois = enable_rois
        self._show_right_column = show_right_column
        self._enable_thresholds = enable_thresholds
        self._feature_configs: list[FeatureUIContext] = []
        self._feature_registry = get_feature_registry()
        self._features_watch_timer: QTimer | None = None
        self._features_last_size: tuple[int, int] | None = None
        self._active_workers: list[tuple[QThread, QObject]] = []

        layout = QVBoxLayout()
        layout.addWidget(self._make_features_section())
        if show_output_section:
            layout.addWidget(self._make_output_section())
        if show_process_button:
            process_button = QPushButton("Process")
            process_button.clicked.connect(self._process_features)
            layout.addWidget(process_button)
            self._process_button = process_button
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

        self._output_path_input = QLineEdit()
        self._output_path_input.setPlaceholderText("Output folder")
        browse_button = QPushButton("Browse")
        browse_button.clicked.connect(self._select_output_path)
        output_path_row = QHBoxLayout()
        output_path_row.setContentsMargins(0, 0, 0, 0)
        output_path_row.addWidget(self._output_path_input)
        output_path_row.addWidget(browse_button)
        output_path_widget = QWidget()
        output_path_widget.setLayout(output_path_row)

        self._save_name_input = QLineEdit()
        self._save_name_input.setPlaceholderText("Output name")
        self._save_name_input.setMinimumWidth(180)
        self._save_name_input.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Fixed
        )

        self._format_combo = QComboBox()
        self._format_combo.addItems(["xlsx", "csv"])
        self._configure_combo(self._format_combo)

        form_layout.addRow("Output folder", output_path_widget)
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

        self._add_feature_button = QPushButton("Add feature")
        self._add_feature_button.clicked.connect(self._add_feature_row)
        section_layout.addWidget(self._add_feature_button)
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

    def _add_feature_row(self, state: FeatureConfig | None = None) -> None:
        """Add a new feature input row."""
        if isinstance(state, bool):
            state = None
        index = len(self._feature_configs)
        feature_section = QGroupBox(f"Feature {index}")
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

        name_input = QLineEdit()
        name_input.setPlaceholderText("Feature name")
        name_input.setMinimumWidth(180)
        name_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        type_combo = RefreshingComboBox(
            refresh_callback=self._notify_features_changed
        )
        feature_types = self._feature_types()
        type_combo.addItems(feature_types)
        self._configure_combo(type_combo)

        form_layout.addRow("Name", name_input)
        form_layout.addRow("Type", type_combo)
        left_layout.addLayout(form_layout)

        delete_button = QPushButton("Delete")
        delete_button.clicked.connect(
            lambda _checked=False, section=feature_section: self._remove_feature(
                section
            )
        )

        left_dynamic_container = QWidget()
        left_dynamic_container.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Fixed
        )
        left_dynamic_layout = QVBoxLayout()
        left_dynamic_layout.setContentsMargins(0, 0, 0, 0)
        left_dynamic_layout.setSpacing(6)
        left_dynamic_container.setLayout(left_dynamic_layout)
        left_layout.addWidget(left_dynamic_container)
        left_layout.addWidget(delete_button)

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
        feature_section.setLayout(section_layout)
        feature_section.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Fixed
        )

        self._features_layout.addWidget(feature_section)
        feature_type = (
            state.type_name
            if state is not None and state.type_name
            else type_combo.currentText()
        )
        if state is None:
            state = FeatureConfig(
                name="",
                type_name=feature_type,
                data=build_feature_data(feature_type),
            )
        if feature_type in feature_types:
            type_combo.blockSignals(True)
            type_combo.setCurrentText(feature_type)
            type_combo.blockSignals(False)
        context = FeatureUIContext(
            state=state,
            section=feature_section,
            name_input=name_input,
            type_combo=type_combo,
            left_dynamic_layout=left_dynamic_layout,
            left_layout=left_layout,
            right_layout=right_layout,
        )
        self._feature_configs.append(context)
        name_input.setText(state.name)
        name_input.textChanged.connect(
            lambda text, ctx=context: self._on_feature_name_changed(ctx, text)
        )
        type_combo.currentTextChanged.connect(
            lambda _text, ctx=context: self._on_feature_type_changed(ctx)
        )
        self._build_feature_handler(context, preserve_data=True)
        self._notify_features_changed()
        self._features_layout.activate()
        QTimer.singleShot(0, self._apply_features_layout)

    def _on_feature_type_changed(self, context: FeatureUIContext) -> None:
        """Update a feature section when its type changes.

        Parameters
        ----------
        context : FeatureUIContext
            Feature UI context and data.
        """
        self._build_feature_handler(context, preserve_data=False)

    def _build_feature_handler(
        self,
        context: FeatureUIContext,
        *,
        preserve_data: bool,
    ) -> None:
        left_dynamic_layout = context.left_dynamic_layout
        self._clear_layout(left_dynamic_layout)
        self._clear_layout(context.right_layout)
        feature_type = context.type_combo.currentText()
        context.state.type_name = feature_type
        if not preserve_data:
            context.state.data = build_feature_data(feature_type)

        feature_handler = self._feature_handler_for_type(feature_type, context)
        context.feature_handler = feature_handler
        if feature_handler is not None:
            feature_handler.build()
        self._notify_features_changed()


    def _remove_feature(self, feature_section: QGroupBox) -> None:
        """Remove a feature section and renumber remaining entries.

        Parameters
        ----------
        feature_section : QGroupBox
            Feature section widget to remove.
        """
        context = next(
            (cfg for cfg in self._feature_configs if cfg.section is feature_section),
            None,
        )
        if context is None:
            return
        self._feature_configs.remove(context)
        self._features_layout.removeWidget(feature_section)
        feature_section.deleteLater()
        self._renumber_features()
        self._notify_features_changed()
        self._features_layout.activate()
        if hasattr(self, "_features_container"):
            self._features_container.adjustSize()
        QTimer.singleShot(0, self._apply_features_layout)

    def _renumber_features(self) -> None:
        """Renumber feature sections after insertions/removals."""
        for index, context in enumerate(self._feature_configs, start=0):
            context.section.setTitle(f"Feature {index}")

    def _notify_features_changed(self) -> None:
        """Notify feature handlers that the feature list has changed."""
        for feature_cls in self._feature_registry.values():
            feature_cls.update_type_options(self, self._feature_configs)
        for context in self._feature_configs:
            handler = context.feature_handler
            if handler is not None:
                handler.on_features_changed(self._feature_configs)


    def _feature_types(self) -> list[str]:
        """Return the available feature type names."""
        return list(self._feature_registry.keys())

    def load_feature_configs(self, configs: list[FeatureConfig]) -> None:
        """Replace the current feature list with provided configs."""
        for context in list(self._feature_configs):
            self._remove_feature(context.section)
        if not configs:
            self._add_feature_row()
            return
        for config in configs:
            self._add_feature_row(config)

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
        """Trigger quantification processing for configured features."""
        process = getattr(self._backend, "process", None)
        if not callable(process):
            return
        features = list(self._feature_configs)
        output_path = self._output_path_input.text()
        output_name = self._save_name_input.text()
        export_format = self._format_combo.currentText()
        if hasattr(self, "_process_button"):
            self._start_background_run(
                run_button=self._process_button,
                run_text="Process",
                run_callable=lambda: process(
                    features,
                    output_path,
                    output_name,
                    export_format,
                ),
                on_success=self._handle_process_complete,
            )
        else:
            process(features, output_path, output_name, export_format)

    def _feature_handler_for_type(
        self, feature_type: str, context: FeatureUIContext
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

    def _start_background_run(
        self,
        *,
        run_button: QPushButton,
        run_text: str,
        run_callable,
        on_success,
    ) -> None:
        """Run quantification in a background thread and manage UI state."""
        run_button.setEnabled(False)
        run_button.setText("Running...")

        thread = QThread(self)
        worker = _RunWorker(run_callable)
        worker.moveToThread(thread)

        def handle_success(result) -> None:
            on_success(result)
            self._finish_background_run(run_button, run_text, thread, worker)

        def handle_error(message: str) -> None:
            self._notify(f"Quantification failed: {message}")
            self._finish_background_run(run_button, run_text, thread, worker)

        thread.started.connect(worker.run)
        worker.finished.connect(handle_success)
        worker.error.connect(handle_error)
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(worker.deleteLater)

        self._active_workers.append((thread, worker))
        thread.start()

    def _finish_background_run(
        self,
        run_button: QPushButton,
        run_text: str,
        thread: QThread,
        worker: QObject,
    ) -> None:
        """Restore UI state after a background run completes."""
        run_button.setEnabled(True)
        run_button.setText(run_text)
        try:
            self._active_workers.remove((thread, worker))
        except ValueError:
            pass

    def _handle_process_complete(self, result) -> None:
        """Notify the user when quantification completes."""
        output_root = getattr(result, "output_root", None)
        if output_root:
            self._notify(f"Quantification complete: {output_root}")
        else:
            self._notify("Quantification complete.")

    def _notify(self, message: str) -> None:
        """Send a user-visible notification."""
        if (
            show_console_notification is not None
            and Notification is not None
            and NotificationSeverity is not None
        ):
            show_console_notification(
                Notification(message, severity=NotificationSeverity.WARNING)
            )

    def _feature_index(self, context: FeatureUIContext) -> int:
        """Return the 0-based index for a feature config.

        Parameters
        ----------
        context : FeatureUIContext
            Feature UI context.

        Returns
        -------
        int
            0-based index of the feature.
        """
        return self._feature_configs.index(context)

    def _on_feature_name_changed(
        self, context: FeatureUIContext, text: str
    ) -> None:
        """Store feature name updates and refresh dependent combos.

        Parameters
        ----------
        context : FeatureUIContext
            Feature UI context.
        text : str
            Updated name string.
        """
        context.state.name = text
        self._notify_features_changed()

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


class _RunWorker(QObject):
    """Worker that executes a callable in a background thread."""

    finished = Signal(object)
    error = Signal(str)

    def __init__(self, run_callable) -> None:
        """Initialize the worker with a callable."""
        super().__init__()
        self._run_callable = run_callable

    def run(self) -> None:
        """Execute the callable and emit results."""
        try:
            result = self._run_callable()
        except Exception as exc:  # pragma: no cover - runtime error path
            self.error.emit(str(exc))
            return
        self.finished.emit(result)
