# AGENTS.md

## Purpose
This file gives coding agents a repo-specific operating guide for SenoQuant.

## Required environment
- Use the conda environment named `senoquant-dev`.
- Python version: `3.11`.

```bash
conda create -n senoquant-dev python=3.11
conda activate senoquant-dev
pip install uv
uv pip install "napari[all]"
uv pip install -e .
```

## Core commands
- Run tests (preferred CI-equivalent command):

```bash
conda activate senoquant-dev
python -m pytest -q
```

- Run full pytest (uses `pytest.ini` coverage settings, 80% minimum):

```bash
conda activate senoquant-dev
pytest
```

- Run docs locally:

```bash
conda activate senoquant-dev
pip install mkdocs mkdocs-material "mkdocstrings[python]"
mkdocs serve
```

## Repository map
- `src/senoquant/`: main plugin package.
- `src/senoquant/_widget.py`: top-level napari widget wiring.
- `src/senoquant/tabs/`: feature tabs (`segmentation`, `spots`, `quantification`, `visualization`, `batch`, `settings`).
- `src/senoquant/utils/settings_bundle.py`: shared `senoquant.settings` bundle schema helpers used by Settings, Batch, and quantification exports.
- `tests/`: pytest suite (UI smoke tests, backends, readers, exports, models).
- `docs/`: user + developer docs and API reference scaffolding.
- `stardist_ext/`: compiled extension source/package.
- `_vendor/ufish/`: vendored dependency code.

## Implementation conventions
- Keep files under 500 lines; split large files into multiple modules.
- Preserve the frontend/backend split in tabs:
  - `frontend.py`: Qt widgets and signal wiring.
  - `backend.py`: business logic and processing.
- Keep Settings/Batch behavior aligned:
  - Batch tab does not own profile load/save buttons.
  - Settings tab is the UI entry point for saving/loading unified settings bundles.
  - Batch runs persist `senoquant_settings.json` in the output root.
- Keep imports absolute from `senoquant`.
- Prefer `pathlib.Path` for filesystem code.
- Use Python 3.11+ type hints.
- For segmentation/spot model discovery, keep `models/<name>/details.json` present.
- For quantification features, maintain registration in `src/senoquant/tabs/quantification/features/__init__.py` and batch config compatibility in `src/senoquant/tabs/batch/config.py`.

## Testing expectations
- Add or update tests with any behavior change.
- Keep tests in the matching subtree under `tests/senoquant/...`.
- Avoid top-level GUI-heavy imports in tests; rely on stubs/fixtures in `tests/conftest.py`.
- For settings-related changes, include coverage for Settings-tab save/load and Batch config application.

## Safe edit boundaries
- Avoid changing vendored/third-party code unless the task explicitly requires it:
  - `_vendor/ufish/`
  - `src/senoquant/tabs/segmentation/stardist_onnx_utils/_csbdeep/`
  - large third-party code under `stardist_onnx_utils/_stardist/lib/external/`
- Do not commit generated artifacts (`build/`, `dist/`, `coverage.xml`, `.coverage`) unless requested.

## Pre-handoff checklist
1. `conda activate senoquant-dev`
2. `python -m pytest -q`
3. Update relevant docs in `docs/user/` or `docs/developer/` when behavior changes.
