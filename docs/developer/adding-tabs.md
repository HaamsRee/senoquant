# Adding tabs

This guide describes how to add a new tab to the main SenoQuant widget.

## Where tabs are wired

Three files are the core wiring points:

- `src/senoquant/tabs/<tab_name>/frontend.py`: tab UI (`QWidget`).
- `src/senoquant/tabs/<tab_name>/backend.py`: processing/discovery logic.
- `src/senoquant/_widget.py`: adds the tab to `SenoQuantWidget`.

You also export tab classes from `src/senoquant/tabs/__init__.py`.

## Step-by-step

### 1) Create the tab package

Create a folder:

`src/senoquant/tabs/<tab_name>/`

Add at least:

- `frontend.py`.
- `backend.py`.

Minimal scaffold:

```python
# src/senoquant/tabs/my_tab/backend.py
class MyTabBackend:
    def __init__(self) -> None:
        self.state = {}
```

```python
# src/senoquant/tabs/my_tab/frontend.py
from qtpy.QtWidgets import QVBoxLayout, QWidget
from .backend import MyTabBackend


class MyTab(QWidget):
    def __init__(self, backend: MyTabBackend | None = None, napari_viewer=None) -> None:
        super().__init__()
        self._backend = backend or MyTabBackend()
        self._viewer = napari_viewer
        layout = QVBoxLayout()
        layout.addStretch(1)
        self.setLayout(layout)
```

### 2) Export the tab class

Update `src/senoquant/tabs/__init__.py`:

- Import your tab class.
- Add it to `__all__`.

### 3) Add the tab to the main widget

Update `src/senoquant/_widget.py`:

- Import your tab class from `.tabs`.
- Add `tabs.addTab(MyTab(...), "My tab label")` in `SenoQuantWidget.__init__`.

If the tab uses shared settings, reuse the existing `SettingsBackend`
instance from `SenoQuantWidget` (same pattern as Segmentation/Settings tabs).

### 4) Add tests

At minimum:

- Add a smoke test in `tests/senoquant/tabs/test_ui_smoke.py` that
  instantiates your tab.
- If your tab has backend behavior, add backend unit tests in
  `tests/senoquant/tabs/<tab_name>/`.

### 5) Update docs navigation

Add the tab docs page to `mkdocs.yml` in the correct section (user or developer).

## Do you need to edit `napari.yaml`?

Usually no.

Current plugin wiring exposes a single widget command:

- `senoquant.make_widget -> senoquant._widget:SenoQuantWidget`.

If your new tab is part of `SenoQuantWidget`, no new napari command is needed.
Only update `napari.yaml` if you want to expose a separate plugin widget.

## Integration checklist

- New tab class exists and is importable.
- Exported from `src/senoquant/tabs/__init__.py`.
- Added to `SenoQuantWidget` in `src/senoquant/_widget.py`.
- Smoke tests added/updated.
- Docs and `mkdocs.yml` updated.
