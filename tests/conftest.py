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
    Vertical = 3
    Horizontal = 4


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

    def setLayout(self, layout) -> None:
        self._layout = layout

    def setVisible(self, visible: bool) -> None:
        self._visible = bool(visible)

    def setMinimumWidth(self, *_args, **_kwargs) -> None:
        return None

    def setMinimumHeight(self, *_args, **_kwargs) -> None:
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

    def setText(self, text: str) -> None:
        self._text = text


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


class QFileDialog:
    """File dialog stub."""

    @staticmethod
    def getExistingDirectory(*_args, **_kwargs) -> str:
        return ""


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
    qtwidgets.QSizePolicy = QSizePolicy

    qtgui.QGuiApplication = QGuiApplication
    qtgui.QPalette = QPalette

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
