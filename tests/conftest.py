"""Test fixtures and dependency stubs.

Notes
-----
Provides lightweight stubs for optional GUI dependencies so modules can be
imported in headless environments.
"""

from __future__ import annotations

import sys
import types
from typing import Any

import numpy as np


class DummySignal:
    """Simple signal stub that records callbacks."""

    def __init__(self) -> None:
        self._callbacks: list[Any] = []

    def connect(self, callback) -> None:
        """Connect a callback to the signal.

        Returns
        -------
        None
        """
        self._callbacks.append(callback)

    def emit(self, *args, **kwargs) -> None:
        """Emit the signal to all callbacks.

        Returns
        -------
        None
        """
        for callback in list(self._callbacks):
            try:
                callback(*args, **kwargs)
            except TypeError:
                callback()


class Signal:
    """Descriptor-style signal for Qt stubs."""

    def __init__(self, *_args, **_kwargs) -> None:
        self._name: str | None = None

    def __set_name__(self, _owner, name: str) -> None:
        self._name = name

    def __get__(self, instance, _owner):
        if instance is None:
            return self
        signals = instance.__dict__.setdefault("_qt_signals", {})
        if self._name not in signals:
            signals[self._name] = DummySignal()
        return signals[self._name]


class QObject:
    """Minimal QObject stub."""

    def __init__(self, *_args, **_kwargs) -> None:
        super().__init__()

    def moveToThread(self, _thread) -> None:
        """No-op for thread move.

        Returns
        -------
        None
        """
        return None

    def deleteLater(self) -> None:
        """No-op delete later.

        Returns
        -------
        None
        """
        return None


class QThread(QObject):
    """Minimal QThread stub."""

    def __init__(self, *_args, **_kwargs) -> None:
        super().__init__()
        self.started = DummySignal()
        self.finished = DummySignal()

    def start(self) -> None:
        """Start the thread (immediately emits started).

        Returns
        -------
        None
        """
        self.started.emit()

    def quit(self) -> None:
        """Quit the thread (immediately emits finished).

        Returns
        -------
        None
        """
        self.finished.emit()


class Qt:
    """Qt constant namespace stub."""

    ScrollBarAlwaysOff = 0
    ScrollBarAsNeeded = 1
    AlignTop = 2
    AlignCenter = 3
    Vertical = 3
    Horizontal = 4
    KeepAspectRatio = 5
    SmoothTransformation = 6
    ItemIsUserCheckable = 1 << 0
    ItemIsEnabled = 1 << 1
    Checked = 2
    Unchecked = 0


class QTimer:
    """Minimal QTimer stub."""

    def __init__(self, *_args, **_kwargs) -> None:
        self.timeout = DummySignal()

    @staticmethod
    def singleShot(_ms: int, callback) -> None:
        """Invoke callback immediately.

        Returns
        -------
        None
        """
        callback()

    def setInterval(self, *_args, **_kwargs) -> None:
        return None

    def start(self) -> None:
        return None


class QSizePolicy:
    """Size policy stub."""

    Expanding = 0
    Fixed = 1
    Minimum = 2

    def __init__(self, *_args, **_kwargs) -> None:
        return None


class DummyLayout:
    """Layout stub with basic recording."""

    def __init__(self, *_args, **_kwargs) -> None:
        self.items: list[Any] = []

    def addWidget(self, widget, *_args, **_kwargs) -> None:
        """Record widget.

        Returns
        -------
        None
        """
        self.items.append(widget)

    def addLayout(self, layout) -> None:
        """Record layout.

        Returns
        -------
        None
        """
        self.items.append(layout)

    def addRow(self, *_args, **_kwargs) -> None:
        """Record row.

        Returns
        -------
        None
        """
        self.items.append((_args, _kwargs))

    def addStretch(self, *_args, **_kwargs) -> None:
        """No-op stretch.

        Returns
        -------
        None
        """
        return None

    def count(self) -> int:
        """Return the number of stored items."""
        return len(self.items)

    def takeAt(self, index: int):
        """Remove and return a layout item wrapper."""
        if index < 0 or index >= len(self.items):
            return DummyLayoutItem(None)
        item = self.items.pop(index)
        return DummyLayoutItem(item)

    def setContentsMargins(self, *_args, **_kwargs) -> None:
        if _args:
            self._margins = _args
        elif _kwargs:
            self._margins = (
                _kwargs.get("left", 0),
                _kwargs.get("top", 0),
                _kwargs.get("right", 0),
                _kwargs.get("bottom", 0),
            )
        return None

    def setSpacing(self, *_args, **_kwargs) -> None:
        if _args:
            self._spacing = _args[0]
        return None

    def setFieldGrowthPolicy(self, *_args, **_kwargs) -> None:
        return None

    def setSizeConstraint(self, *_args, **_kwargs) -> None:
        return None

    def setAlignment(self, *_args, **_kwargs) -> None:
        return None

    def activate(self) -> None:
        return None

    def contentsMargins(self):
        margins = getattr(self, "_margins", (0, 0, 0, 0))
        return DummyMargins(*margins)

    def spacing(self) -> int:
        return int(getattr(self, "_spacing", 0))

    def itemAt(self, index: int):
        if index < 0 or index >= len(self.items):
            return DummyLayoutItem(None)
        return DummyLayoutItem(self.items[index])


class DummyLayoutItem:
    """Layout item wrapper stub."""

    def __init__(self, item) -> None:
        self._item = item

    def widget(self):
        if isinstance(self._item, QWidget):
            return self._item
        return None

    def sizeHint(self):
        return DummySize(0, 0)

    def layout(self):
        if isinstance(self._item, DummyLayout):
            return self._item
        return None


class DummyMargins:
    """Margins stub."""

    def __init__(self, left: int, top: int, right: int, bottom: int) -> None:
        self._left = left
        self._top = top
        self._right = right
        self._bottom = bottom

    def left(self) -> int:
        return self._left

    def right(self) -> int:
        return self._right

    def top(self) -> int:
        return self._top

    def bottom(self) -> int:
        return self._bottom


class DummySize:
    """Size stub for size hints."""

    def __init__(self, width: int, height: int) -> None:
        self._width = width
        self._height = height

    def width(self) -> int:
        return self._width

    def height(self) -> int:
        return self._height

    def expandedTo(self, other: "DummySize") -> "DummySize":
        return DummySize(max(self._width, other._width), max(self._height, other._height))


class QFormLayout(DummyLayout):
    """Form layout stub."""

    AllNonFixedFieldsGrow = 0


class QVBoxLayout(DummyLayout):
    """Vertical layout stub."""

    SetMinAndMaxSize = 0


class QHBoxLayout(DummyLayout):
    """Horizontal layout stub."""


class QWidget:
    """Basic QWidget stub."""

    def __init__(self, *_args, **_kwargs) -> None:
        self._layout = None
        self._visible = True
        self._width = 640
        self._height = 480

    def setLayout(self, layout) -> None:
        self._layout = layout

    def setVisible(self, visible: bool) -> None:
        self._visible = bool(visible)

    def setMinimumWidth(self, *_args, **_kwargs) -> None:
        if _args:
            self._width = max(self._width, int(_args[0]))
        return None

    def setMinimumHeight(self, *_args, **_kwargs) -> None:
        if _args:
            self._height = max(self._height, int(_args[0]))
        return None

    def setMaximumHeight(self, *_args, **_kwargs) -> None:
        return None

    def setMinimumSize(self, *_args, **_kwargs) -> None:
        return None

    def setSizePolicy(self, *_args, **_kwargs) -> None:
        return None

    def setStyleSheet(self, *_args, **_kwargs) -> None:
        return None

    def setFlat(self, *_args, **_kwargs) -> None:
        return None

    def setObjectName(self, *_args, **_kwargs) -> None:
        return None

    def setAutoFillBackground(self, *_args, **_kwargs) -> None:
        return None

    def setBackgroundRole(self, *_args, **_kwargs) -> None:
        return None

    def setEnabled(self, *_args, **_kwargs) -> None:
        return None

    def blockSignals(self, *_args, **_kwargs) -> None:
        return None

    def adjustSize(self) -> None:
        return None

    def updateGeometry(self) -> None:
        return None

    def sizeHint(self) -> DummySize:
        return DummySize(0, 0)

    def minimumSizeHint(self) -> DummySize:
        return DummySize(0, 0)

    def setFixedHeight(self, *_args, **_kwargs) -> None:
        if _args:
            self._height = int(_args[0])
        return None

    def setUpdatesEnabled(self, *_args, **_kwargs) -> None:
        return None

    def deleteLater(self) -> None:
        return None

    def window(self):
        return None

    def minimumWidth(self) -> int:
        return 0

    def parentWidget(self):
        return None

    def width(self) -> int:
        return int(self._width)

    def height(self) -> int:
        return int(self._height)


class QFrame(QWidget):
    """Frame stub."""

    StyledPanel = 0
    Plain = 1

    def setFrameShape(self, *_args, **_kwargs) -> None:
        return None

    def setFrameShadow(self, *_args, **_kwargs) -> None:
        return None


class QGroupBox(QWidget):
    """Group box stub."""

    def __init__(self, *_args, **_kwargs) -> None:
        super().__init__()
        self._title = ""

    def setTitle(self, title: str) -> None:
        self._title = title


class QScrollArea(QWidget):
    """Scroll area stub."""

    def setWidgetResizable(self, *_args, **_kwargs) -> None:
        return None

    def setHorizontalScrollBarPolicy(self, *_args, **_kwargs) -> None:
        return None

    def setVerticalScrollBarPolicy(self, *_args, **_kwargs) -> None:
        return None

    def setWidget(self, *_args, **_kwargs) -> None:
        if _args:
            self._widget = _args[0]
        return None

    def viewport(self):
        return DummyViewport()

    def widget(self):
        return getattr(self, "_widget", None)

    def verticalScrollBar(self):
        return QScrollBar()

    def frameWidth(self) -> int:
        return 0


class QTabWidget(QWidget):
    """Tab widget stub."""

    def addTab(self, _widget, _label: str) -> None:
        return None


class QSplitter(QWidget):
    """Splitter stub."""

    def addWidget(self, widget) -> None:
        return None

    def setChildrenCollapsible(self, *_args, **_kwargs) -> None:
        return None

    def setStretchFactor(self, *_args, **_kwargs) -> None:
        return None


class QComboBox(QWidget):
    """Combo box stub."""

    AdjustToMinimumContentsLengthWithIcon = 0

    def __init__(self, *_args, **_kwargs) -> None:
        super().__init__()
        self._items: list[str] = []
        self._current_text = ""
        self.currentTextChanged = DummySignal()
        self.activated = DummySignal()

    def addItems(self, items) -> None:
        self._items.extend(list(items))
        if not self._current_text and self._items:
            self.setCurrentText(self._items[0])

    def addItem(self, item: str) -> None:
        self._items.append(item)
        if not self._current_text:
            self.setCurrentText(item)

    def insertItem(self, index: int, item: str) -> None:
        self._items.insert(index, item)
        if index == 0 and not self._current_text:
            self.setCurrentText(item)

    def clear(self) -> None:
        self._items = []
        self._current_text = ""

    def currentText(self) -> str:
        return self._current_text

    def setCurrentText(self, text: str) -> None:
        self._current_text = text
        self.currentTextChanged.emit(text)

    def setEditable(self, *_args, **_kwargs) -> None:
        return None

    def setSizeAdjustPolicy(self, *_args, **_kwargs) -> None:
        return None

    def setMinimumContentsLength(self, *_args, **_kwargs) -> None:
        return None

    def findText(self, text: str) -> int:
        try:
            return self._items.index(text)
        except ValueError:
            return -1

    def setCurrentIndex(self, index: int) -> None:
        if 0 <= index < len(self._items):
            self.setCurrentText(self._items[index])


class QCheckBox(QWidget):
    """Checkbox stub."""

    def __init__(self, *_args, **_kwargs) -> None:
        super().__init__()
        self._checked = False
        self.toggled = DummySignal()

    def setChecked(self, checked: bool) -> None:
        self._checked = bool(checked)
        self.toggled.emit(self._checked)

    def isChecked(self) -> bool:
        return self._checked


class QPushButton(QWidget):
    """Button stub."""

    def __init__(self, *_args, **_kwargs) -> None:
        super().__init__()
        self.clicked = DummySignal()
        self._text = ""
        self._enabled = True

    def setText(self, text: str) -> None:
        self._text = text

    def text(self) -> str:
        return self._text

    def setEnabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)

    def isEnabled(self) -> bool:
        return self._enabled


class QLineEdit(QWidget):
    """Line edit stub."""

    def __init__(self, *_args, **_kwargs) -> None:
        super().__init__()
        self._text = ""
        self.textChanged = DummySignal()

    def setText(self, text: str) -> None:
        self._text = text
        self.textChanged.emit(text)

    def text(self) -> str:
        return self._text

    def setPlaceholderText(self, *_args, **_kwargs) -> None:
        return None


class QSpinBox(QWidget):
    """Spin box stub."""

    def __init__(self, *_args, **_kwargs) -> None:
        super().__init__()
        self._value = 0
        self.valueChanged = DummySignal()

    def setValue(self, value: int) -> None:
        self._value = int(value)
        self.valueChanged.emit(self._value)

    def value(self) -> int:
        return self._value

    def setRange(self, *_args, **_kwargs) -> None:
        return None

    def setMinimum(self, *_args, **_kwargs) -> None:
        return None

    def setMaximum(self, *_args, **_kwargs) -> None:
        return None

    def setSingleStep(self, *_args, **_kwargs) -> None:
        return None


class QScrollBar:
    """Scrollbar stub."""

    def maximum(self) -> int:
        return 0

    def setRange(self, *_args, **_kwargs) -> None:
        return None

    def setValue(self, *_args, **_kwargs) -> None:
        return None


class DummyViewport:
    """Viewport stub."""

    def width(self) -> int:
        return 0

    def updateGeometry(self) -> None:
        return None


class QDoubleSpinBox(QWidget):
    """Double spin box stub."""

    def __init__(self, *_args, **_kwargs) -> None:
        super().__init__()
        self._value = 0.0
        self.valueChanged = DummySignal()

    def setValue(self, value: float) -> None:
        self._value = float(value)
        self.valueChanged.emit(self._value)

    def value(self) -> float:
        return self._value

    def setRange(self, *_args, **_kwargs) -> None:
        return None

    def setDecimals(self, *_args, **_kwargs) -> None:
        return None

    def setSingleStep(self, *_args, **_kwargs) -> None:
        return None

    def setSuffix(self, *_args, **_kwargs) -> None:
        return None


class QLabel(QWidget):
    """Label stub."""

    def __init__(self, *_args, **_kwargs) -> None:
        super().__init__()
        self._text = ""
        self._pixmap = None
        self._alignment = None

    def setText(self, text: str) -> None:
        self._text = text

    def text(self) -> str:
        return self._text

    def setAlignment(self, alignment) -> None:
        self._alignment = alignment

    def setOpenExternalLinks(self, *_args, **_kwargs) -> None:
        return None

    def setPixmap(self, pixmap) -> None:
        self._pixmap = pixmap


class QProgressBar(QWidget):
    """Progress bar stub."""

    def __init__(self, *_args, **_kwargs) -> None:
        super().__init__()
        self._value = 0
        self._visible = True

    def setValue(self, value: int) -> None:
        """Set progress value.

        Parameters
        ----------
        value : int
            Progress value (0-100).
        """
        self._value = value

    def setVisible(self, visible: bool) -> None:
        """Set visibility.

        Parameters
        ----------
        visible : bool
            Whether the progress bar is visible.
        """
        self._visible = visible


class QDialog(QWidget):
    """Dialog stub."""

    def __init__(self, *_args, **_kwargs) -> None:
        super().__init__()
        self.accepted = DummySignal()
        self._title = ""

    def show(self) -> None:
        return None

    def raise_(self) -> None:
        return None

    def activateWindow(self) -> None:
        return None

    def close(self) -> None:
        return None

    def setWindowTitle(self, title: str) -> None:
        self._title = title

    def accept(self) -> None:
        self.accepted.emit()

    def exec(self) -> int:
        return 0


class QFileDialog:
    """File dialog stub."""

    @staticmethod
    def getExistingDirectory(*_args, **_kwargs) -> str:
        return ""

    @staticmethod
    def getOpenFileName(*_args, **_kwargs):
        return "", ""

    @staticmethod
    def getSaveFileName(*_args, **_kwargs):
        return "", ""


class QPixmap:
    """Pixmap stub."""

    def __init__(self, path: str = "") -> None:
        self._path = path
        self._null = not bool(path)

    def isNull(self) -> bool:
        return self._null

    def scaled(self, *_args, **_kwargs):
        return self


class QHeaderView(QWidget):
    """Header view stub."""

    ResizeToContents = 0
    Stretch = 1

    def setSectionResizeMode(self, *_args, **_kwargs) -> None:
        return None

    def setVisible(self, *_args, **_kwargs) -> None:
        return None


class QTableWidgetItem:
    """Table widget item stub."""

    def __init__(self, text: str = "") -> None:
        self._text = text
        self._check_state = Qt.Unchecked
        self._flags = Qt.ItemIsEnabled

    def setCheckState(self, state: int) -> None:
        self._check_state = state

    def checkState(self) -> int:
        return self._check_state

    def setFlags(self, flags: int) -> None:
        self._flags = flags

    def text(self) -> str:
        return self._text


class QTableWidget(QWidget):
    """Table widget stub."""

    def __init__(self, *_args, **_kwargs) -> None:
        super().__init__()
        self._rows = 0
        self._cols = 0
        self._items: dict[tuple[int, int], QTableWidgetItem] = {}
        self._cell_widgets: dict[tuple[int, int], QWidget] = {}
        self._h_header = QHeaderView()
        self._v_header = QHeaderView()

    def setColumnCount(self, count: int) -> None:
        self._cols = int(count)

    def setHorizontalHeaderLabels(self, _labels) -> None:
        return None

    def horizontalHeader(self) -> QHeaderView:
        return self._h_header

    def verticalHeader(self) -> QHeaderView:
        return self._v_header

    def setRowCount(self, count: int) -> None:
        self._rows = int(count)
        self._items = {
            key: value
            for key, value in self._items.items()
            if key[0] < self._rows and key[1] < self._cols
        }
        self._cell_widgets = {
            key: value
            for key, value in self._cell_widgets.items()
            if key[0] < self._rows and key[1] < self._cols
        }

    def insertRow(self, row: int) -> None:
        self._rows = max(self._rows, int(row) + 1)

    def setItem(self, row: int, col: int, item: QTableWidgetItem) -> None:
        self._items[(int(row), int(col))] = item

    def item(self, row: int, col: int):
        return self._items.get((int(row), int(col)))

    def setCellWidget(self, row: int, col: int, widget: QWidget) -> None:
        self._cell_widgets[(int(row), int(col))] = widget

    def cellWidget(self, row: int, col: int):
        return self._cell_widgets.get((int(row), int(col)))

    def rowCount(self) -> int:
        return self._rows


class QPalette:
    """Palette stub."""

    Window = 0

    def __init__(self, *_args, **_kwargs) -> None:
        return None


class QGuiApplication:
    """Gui application stub."""

    @staticmethod
    def clipboard():
        return types.SimpleNamespace(setText=lambda *_args, **_kwargs: None)

    @staticmethod
    def primaryScreen():
        return DummyScreen()


class DummyScreen:
    """Screen stub."""

    def availableGeometry(self):
        return DummyRect()


class DummyRect:
    """Rectangle stub."""

    def height(self) -> int:
        return 720


def _ensure_qtpy(force: bool = True) -> None:
    """Ensure qtpy is importable by installing stubs.

    Parameters
    ----------
    force : bool, optional
        When True, always install stubs to avoid loading real Qt bindings.
    """
    if not force:
        try:
            import qtpy  # noqa: F401
            return
        except Exception:
            pass

    qtpy = types.ModuleType("qtpy")
    qtcore = types.ModuleType("qtpy.QtCore")
    qtwidgets = types.ModuleType("qtpy.QtWidgets")
    qtgui = types.ModuleType("qtpy.QtGui")

    qtcore.Signal = Signal
    qtcore.QObject = QObject
    qtcore.QThread = QThread
    qtcore.Qt = Qt
    qtcore.QTimer = QTimer

    qtwidgets.QWidget = QWidget
    qtwidgets.QFrame = QFrame
    qtwidgets.QGroupBox = QGroupBox
    qtwidgets.QScrollArea = QScrollArea
    qtwidgets.QTabWidget = QTabWidget
    qtwidgets.QSplitter = QSplitter
    qtwidgets.QFormLayout = QFormLayout
    qtwidgets.QVBoxLayout = QVBoxLayout
    qtwidgets.QHBoxLayout = QHBoxLayout
    qtwidgets.QComboBox = QComboBox
    qtwidgets.QCheckBox = QCheckBox
    qtwidgets.QPushButton = QPushButton
    qtwidgets.QLineEdit = QLineEdit
    qtwidgets.QSpinBox = QSpinBox
    qtwidgets.QDoubleSpinBox = QDoubleSpinBox
    qtwidgets.QLabel = QLabel
    qtwidgets.QProgressBar = QProgressBar
    qtwidgets.QDialog = QDialog
    qtwidgets.QFileDialog = QFileDialog
    qtwidgets.QHeaderView = QHeaderView
    qtwidgets.QTableWidget = QTableWidget
    qtwidgets.QTableWidgetItem = QTableWidgetItem
    qtwidgets.QSizePolicy = QSizePolicy

    qtgui.QGuiApplication = QGuiApplication
    qtgui.QPalette = QPalette
    qtgui.QPixmap = QPixmap

    sys.modules["qtpy"] = qtpy
    sys.modules["qtpy.QtCore"] = qtcore
    sys.modules["qtpy.QtWidgets"] = qtwidgets
    sys.modules["qtpy.QtGui"] = qtgui


def _ensure_superqt(force: bool = True) -> None:
    """Provide a superqt RangeSlider stub.

    Parameters
    ----------
    force : bool, optional
        When True, always install stubs to avoid importing Qt widgets.
    """
    if not force:
        try:
            import superqt  # noqa: F401
            return
        except Exception:
            pass

    superqt = types.ModuleType("superqt")

    class QRangeSlider(QWidget):
        """Range slider stub."""

        def __init__(self, *_args, **_kwargs) -> None:
            super().__init__()
            self._value = (0, 0)

        def setValue(self, value) -> None:
            self._value = tuple(value)

        def value(self):
            return self._value

        def setOrientation(self, *_args, **_kwargs) -> None:
            return None

    superqt.QRangeSlider = QRangeSlider
    superqt.QDoubleRangeSlider = QRangeSlider
    sys.modules["superqt"] = superqt


def _ensure_onnxruntime(force: bool = True) -> None:
    """Provide a lightweight onnxruntime stub."""
    if not force:
        try:
            import onnxruntime  # noqa: F401
            return
        except Exception:
            pass
    ort = types.ModuleType("onnxruntime")

    def get_available_providers():
        return ["CPUExecutionProvider"]

    class InferenceSession:
        """Inference session stub."""

        def __init__(self, _path: str, providers=None) -> None:
            self._providers = providers or ["CPUExecutionProvider"]

        def run(self, _output_names, _feeds):
            raise RuntimeError("onnxruntime stub cannot run inference.")

        def get_providers(self):
            return list(self._providers)

    ort.get_available_providers = get_available_providers
    ort.InferenceSession = InferenceSession
    sys.modules["onnxruntime"] = ort


def _ensure_cellpose(force: bool = True) -> None:
    """Provide a lightweight cellpose stub."""
    if not force:
        try:
            import cellpose  # noqa: F401
            return
        except Exception:
            pass

    cellpose = types.ModuleType("cellpose")
    models = types.ModuleType("cellpose.models")

    class CellposeModel:
        """Cellpose model stub that returns empty outputs."""

        def __init__(self, *args, **kwargs) -> None:
            return None

        def eval(self, *args, **kwargs):
            return np.zeros((1, 1), dtype=np.uint16), None, None

    models.CellposeModel = CellposeModel
    cellpose.models = models
    sys.modules["cellpose"] = cellpose
    sys.modules["cellpose.models"] = models


def _ensure_torch(force: bool = True) -> None:
    """Provide a lightweight torch stub."""
    if not force:
        try:
            import torch  # noqa: F401
            return
        except Exception:
            pass

    torch = types.ModuleType("torch")
    nn = types.ModuleType("torch.nn")
    functional = types.ModuleType("torch.nn.functional")
    onnx = types.ModuleType("torch.onnx")
    optim = types.ModuleType("torch.optim")
    utils = types.ModuleType("torch.utils")
    tensorboard = types.ModuleType("torch.utils.tensorboard")
    data = types.ModuleType("torch.utils.data")

    def _shape_args(*shape):
        if len(shape) == 1 and isinstance(shape[0], tuple):
            return shape[0]
        return shape

    class _NoGrad:
        def __enter__(self):
            return None

        def __exit__(self, *_args) -> bool:
            return False

    class _Module:
        def __init__(self, *_args, **_kwargs) -> None:
            self.training = True

        def __call__(self, *args, **kwargs):
            return self.forward(*args, **kwargs)

        def forward(self, *args, **_kwargs):
            return args[0] if args else None

        def parameters(self) -> list:
            return []

        def cuda(self, *_args, **_kwargs):
            return self

        def to(self, *_args, **_kwargs):
            return self

        def eval(self):
            self.training = False
            return self

        def train(self, mode: bool = True):
            self.training = bool(mode)
            return self

        def load_state_dict(self, *_args, **_kwargs) -> None:
            return None

        def state_dict(self) -> dict:
            return {}

    class _Identity(_Module):
        pass

    class _Sequential(_Module):
        def __init__(self, *modules) -> None:
            super().__init__()
            self._modules = modules

        def forward(self, x, *_args, **_kwargs):
            out = x
            for module in self._modules:
                out = module(out)
            return out

    class _ModuleList(list):
        pass

    class _Optimizer:
        def __init__(self, *_args, **_kwargs) -> None:
            return None

        def zero_grad(self) -> None:
            return None

        def step(self) -> None:
            return None

    class _DataLoader(list):
        pass

    class _SummaryWriter:
        def __init__(self, *_args, **_kwargs) -> None:
            return None

        def add_scalar(self, *_args, **_kwargs) -> None:
            return None

        def close(self) -> None:
            return None

    class _Tensor(np.ndarray):
        """NumPy-backed tensor stub with minimal torch-like API."""

        def __new__(cls, value, dtype=None, device: str | None = None):
            arr = np.asarray(value, dtype=dtype).view(cls)
            arr.device = device or "cpu"
            return arr

        def __array_finalize__(self, obj):
            self.device = getattr(obj, "device", "cpu")

        def to(self, device=None, dtype=None, **_kwargs):
            target_device = self.device if device is None else device
            target_dtype = self.dtype if dtype is None else dtype
            return _to_tensor(self, dtype=target_dtype, device=target_device)

        def cuda(self, *_args, **_kwargs):
            return self.to(device="cuda")

        def cpu(self):
            return self.to(device="cpu")

        def detach(self):
            return self

        def numpy(self):
            return np.asarray(self)

        def unsqueeze(self, dim: int):
            return _to_tensor(np.expand_dims(np.asarray(self), axis=dim), device=self.device)

        def squeeze(self, axis=None):
            return _to_tensor(np.squeeze(np.asarray(self), axis=axis), device=self.device)

        def clamp(self, min=None, max=None):
            low = -np.inf if min is None else min
            high = np.inf if max is None else max
            return _to_tensor(np.clip(np.asarray(self), low, high), device=self.device)

        def amin(self, *args, **kwargs):
            return float(np.amin(np.asarray(self), *args, **kwargs))

        def amax(self, *args, **kwargs):
            return float(np.amax(np.asarray(self), *args, **kwargs))

        def max(self, dim=None, keepdim=False):
            arr = np.asarray(self)
            if dim is None:
                return float(np.max(arr))
            values = np.max(arr, axis=dim, keepdims=keepdim)
            indices = np.argmax(arr, axis=dim)
            return types.SimpleNamespace(
                values=_to_tensor(values, device=self.device),
                indices=_to_tensor(indices, device=self.device),
            )

    def _to_tensor(value, dtype=None, device=None):
        base = np.asarray(value, dtype=dtype)
        target_device = device
        if target_device is None:
            target_device = getattr(value, "device", "cpu")
        return _Tensor(base, device=str(target_device))

    def _asarray(value, dtype=None, device=None, **_kwargs):
        return _to_tensor(value, dtype=dtype, device=device)

    def _cat(values, dim=0):
        device = getattr(values[0], "device", "cpu") if values else "cpu"
        return _to_tensor(
            np.concatenate([np.asarray(v) for v in values], axis=dim),
            device=device,
        )

    def _stack(values, dim=0):
        device = getattr(values[0], "device", "cpu") if values else "cpu"
        return _to_tensor(
            np.stack([np.asarray(v) for v in values], axis=dim),
            device=device,
        )

    def _max(values, dim=None, keepdim=False):
        arr = np.asarray(values)
        if dim is None:
            return np.max(arr)
        max_vals = np.max(arr, axis=dim, keepdims=keepdim)
        max_idx = np.argmax(arr, axis=dim)
        device = getattr(values, "device", "cpu")
        return _to_tensor(max_vals, device=device), _to_tensor(max_idx, device=device)

    def _identity_op(value, *_args, **_kwargs):
        return _to_tensor(value, device=getattr(value, "device", "cpu"))

    def _pad(value, pad, mode="constant", **_kwargs):
        arr = np.asarray(value)
        if len(pad) == 4:
            left, right, top, bottom = pad
            pad_width = [(0, 0)] * (arr.ndim - 2) + [(top, bottom), (left, right)]
        elif len(pad) == 2:
            left, right = pad
            pad_width = [(0, 0)] * (arr.ndim - 1) + [(left, right)]
        else:
            return _to_tensor(arr, device=getattr(value, "device", "cpu"))
        np_mode = "reflect" if mode == "reflect" else "constant"
        padded = np.pad(arr, pad_width, mode=np_mode)
        return _to_tensor(padded, device=getattr(value, "device", "cpu"))

    torch.Tensor = _Tensor
    torch.float = np.float32
    torch.float32 = np.float32
    torch.device = lambda value: value
    torch.as_tensor = _asarray
    torch.tensor = _asarray
    torch.from_numpy = lambda value: _to_tensor(value)
    torch.rand = lambda *shape, **_kwargs: _to_tensor(
        np.random.rand(*_shape_args(*shape)).astype(np.float32),
        device=_kwargs.get("device"),
    )
    torch.zeros = lambda *shape, **_kwargs: _to_tensor(
        np.zeros(
            _shape_args(*shape),
            dtype=_kwargs.get("dtype", np.float32),
        ),
        device=_kwargs.get("device"),
    )
    torch.ones = lambda *shape, **_kwargs: _to_tensor(
        np.ones(
            _shape_args(*shape),
            dtype=_kwargs.get("dtype", np.float32),
        ),
        device=_kwargs.get("device"),
    )
    torch.zeros_like = lambda value, **_kwargs: _to_tensor(
        np.zeros_like(np.asarray(value)),
        device=_kwargs.get("device", getattr(value, "device", "cpu")),
    )
    torch.ones_like = lambda value, **_kwargs: _to_tensor(
        np.ones_like(np.asarray(value)),
        device=_kwargs.get("device", getattr(value, "device", "cpu")),
    )
    torch.cat = _cat
    torch.stack = _stack
    torch.mean = lambda value, dim=None, keepdim=False: np.mean(
        np.asarray(value),
        axis=dim,
        keepdims=keepdim,
    )
    torch.max = _max
    torch.sum = lambda value, *args, **kwargs: np.sum(
        np.asarray(value),
        *args,
        **kwargs,
    )
    torch.sqrt = lambda value: _to_tensor(
        np.sqrt(np.asarray(value)),
        device=getattr(value, "device", "cpu"),
    )
    torch.flatten = lambda value: _to_tensor(
        np.ravel(np.asarray(value)),
        device=getattr(value, "device", "cpu"),
    )
    torch.no_grad = lambda: _NoGrad()
    torch.load = lambda *_args, **_kwargs: {}
    torch.save = lambda *_args, **_kwargs: None
    torch.set_grad_enabled = lambda *_args, **_kwargs: None
    torch.cuda = types.SimpleNamespace(is_available=lambda: False)
    torch.backends = types.SimpleNamespace(
        mps=types.SimpleNamespace(is_available=lambda: False)
    )
    torch.hub = types.SimpleNamespace(download_url_to_file=lambda *_a, **_k: None)
    torch.jit = types.SimpleNamespace(trace=lambda model, *_a, **_k: model)

    onnx.export = lambda *_args, **_kwargs: None
    torch.onnx = onnx

    nn.Module = _Module
    nn.Sequential = _Sequential
    nn.ModuleList = _ModuleList
    nn.Identity = _Identity
    nn.Conv2d = _Identity
    nn.BatchNorm2d = _Identity
    nn.ReLU = _Identity
    nn.MaxPool2d = _Identity
    nn.Upsample = _Identity
    nn.Sigmoid = _Identity
    nn.AdaptiveAvgPool2d = _Identity
    nn.AdaptiveMaxPool2d = _Identity
    nn.Linear = _Identity

    def _nn_getattr(_name: str):
        return _Identity

    nn.__getattr__ = _nn_getattr
    nn.functional = functional

    functional.pad = _pad
    functional.interpolate = _identity_op
    functional.max_pool2d = _identity_op
    functional.grid_sample = _identity_op
    functional.relu = lambda value, *_a, **_k: np.maximum(np.asarray(value), 0)
    functional.sigmoid = lambda value: 1.0 / (1.0 + np.exp(-np.asarray(value)))
    functional.softmax = lambda value, *_a, **_k: np.asarray(value)
    functional.__getattr__ = lambda _name: _identity_op

    optim.Optimizer = _Optimizer
    optim.Adam = _Optimizer

    tensorboard.SummaryWriter = _SummaryWriter
    data.DataLoader = _DataLoader
    utils.tensorboard = tensorboard
    utils.data = data

    torch.nn = nn
    torch.optim = optim
    torch.utils = utils

    sys.modules["torch"] = torch
    sys.modules["torch.nn"] = nn
    sys.modules["torch.nn.functional"] = functional
    sys.modules["torch.onnx"] = onnx
    sys.modules["torch.optim"] = optim
    sys.modules["torch.utils"] = utils
    sys.modules["torch.utils.tensorboard"] = tensorboard
    sys.modules["torch.utils.data"] = data


class DummyLayerList:
    """List-like container emulating napari layer list."""

    def __init__(self, layers: list[Any] | None = None) -> None:
        self._layers = list(layers) if layers is not None else []

    def __iter__(self):
        return iter(self._layers)

    def __getitem__(self, key):
        if isinstance(key, str):
            for layer in self._layers:
                if layer.name == key:
                    return layer
            raise KeyError(key)
        return self._layers[key]

    def append(self, layer) -> None:
        self._layers.append(layer)


class DummyLayer:
    """Simple layer stub with data/metadata."""

    def __init__(self, data, name: str, metadata: dict | None = None, rgb: bool = False):
        self.data = np.asarray(data) if data is not None else data
        self.name = name
        self.metadata = metadata or {}
        self.rgb = rgb
        self.contour = None


class Image(DummyLayer):
    """Image layer stub with napari-like class name."""


class Labels(DummyLayer):
    """Labels layer stub with napari-like class name."""


class DummyViewer:
    """Viewer stub with add_labels and layer list."""

    def __init__(self, layers: list[DummyLayer] | None = None) -> None:
        self.layers = DummyLayerList(layers)

    def add_labels(self, data, name: str):
        layer = DummyLayer(np.asarray(data), name)
        self.layers.append(layer)
        return layer


_ensure_qtpy(force=True)
_ensure_superqt(force=True)
_ensure_onnxruntime(force=True)
_ensure_cellpose(force=True)
_ensure_torch(force=True)


def _ensure_cupy_stub() -> None:
    """Provide minimal cupy/cucim stubs to avoid heavy imports."""
    cupy = types.ModuleType("cupy")
    cupy.asarray = np.asarray
    cupy.array = np.array
    cupy.ndarray = np.ndarray
    sys.modules["cupy"] = cupy

    cucim = types.ModuleType("cucim")
    skimage = types.ModuleType("cucim.skimage")
    filters = types.ModuleType("cucim.skimage.filters")
    morphology = types.ModuleType("cucim.skimage.morphology")
    transform = types.ModuleType("cucim.skimage.transform")

    filters.threshold_otsu = lambda data: float(np.mean(data))
    morphology.opening = lambda image, footprint=None, mode=None: np.asarray(image)
    morphology.rectangle = lambda *_args, **_kwargs: np.ones((1, 1), dtype=np.uint8)
    transform.rotate = lambda image, _angle, mode=None: np.asarray(image)

    cucim.skimage = skimage
    sys.modules["cucim"] = cucim
    sys.modules["cucim.skimage"] = skimage
    sys.modules["cucim.skimage.filters"] = filters
    sys.modules["cucim.skimage.morphology"] = morphology
    sys.modules["cucim.skimage.transform"] = transform


_ensure_cupy_stub()
