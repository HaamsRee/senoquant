# SenoQuant Developer Guide for AI Agents

## Project Overview

SenoQuant is a napari plugin for spatial quantification of senescence markers in tissue imaging. It's a Qt-based tabbed UI with segmentation (StarDist/Cellpose ONNX models), spot detection, and quantification features.

**Key stack:** Python 3.11, napari, QtPy, BioIO readers, ONNX Runtime, `scikit-image`, `scipy`

## Architecture

### Tab-Based UI Structure

The main widget (`src/senoquant/_widget.py`) composes 5 tabs:
- **Segmentation** → nuclear/cytoplasmic segmentation
- **Spots** → spot detection (udwt, rmp models)
- **Quantification** → feature extraction (markers, spots, ROI)
- **Batch** → automated processing pipeline
- **Settings** → model preloading preferences

Each tab follows **frontend/backend split**:
- `frontend.py` → Qt UI (QWidget construction, signals)
- `backend.py` → pure Python logic (model discovery, processing)

### Plugin-Based Model Discovery

**Segmentation models:** `src/senoquant/tabs/segmentation/models/<model_name>/`
- `details.json` → metadata (name, version, tasks, UI settings schema)
- `model.py` (optional) → subclass of `SenoQuantSegmentationModel`
- Discovered at runtime by scanning folders; first subclass is instantiated

**Spot detectors:** `src/senoquant/tabs/spots/models/<detector_name>/`
- Same pattern: `details.json` + optional `model.py` (subclass `SenoQuantSpotDetector`)

**Quantification features:** `src/senoquant/tabs/quantification/features/<feature>/`
- Subclass `SenoQuantFeature`, define `feature_type` and `order`
- Registry built via dynamic import scanning (`get_feature_registry()`)

### Batch Processing Pipeline

[`BatchBackend.run_job()`](../src/senoquant/tabs/batch/backend.py) orchestrates:
1. Enumerate input files + resolve channel names to indices
2. Run segmentation tasks (nuclear/cytoplasmic) if enabled
3. Run spot detection for selected channels
4. Build lightweight `BatchViewer` shim → run quantification
5. Write masks and quantification outputs to disk

Batch config is serialized/deserialized via `BatchJobConfig` dataclasses in [config.py](../src/senoquant/tabs/batch/config.py).

### BioIO Reader Integration

Reader in [`src/senoquant/reader/core.py`](../src/senoquant/reader/core.py):
- Uses `BioImage.determine_plugin()` to validate files
- Iterates scenes + channels → creates napari layers with fixed colormap cycle
- Supports multi-scene files when BioIO detects multiple scenes

## Development Workflows

### Environment Setup
```bash
conda create -n senoquant python=3.11
conda activate senoquant
pip install uv
uv pip install "napari[all]"
uv pip install -e .
napari  # Opens napari; load plugin from Plugins menu
```

### Testing
```bash
pytest  # Runs tests from tests/ with 80% coverage requirement
```
- Pytest config: `pytest.ini` (coverage settings, pythonpath=src)
- Test fixtures: `tests/conftest.py` provides stubs for headless GUI dependencies (DummySignal, mock napari layers)
- Tests use `tmp_path` fixtures extensively for isolated file operations

### StarDist ONNX Conversion (Separate Environment)
```bash
conda create -n stardist-convert python=3.11
conda activate stardist-convert
pip install uv
uv pip install tensorflow tf2onnx
uv pip install --upgrade "protobuf>=6.33.4"  # Force after TF install
uv pip install -e .
python -m senoquant.tabs.segmentation.stardist_onnx_utils.onnx_framework.convert.cli \
  --dim 2 --model 2D_versatile_fluo --output ./onnx_models
```
**Important:** Protobuf must be reinstalled AFTER TensorFlow/tf2onnx to avoid runtime import errors.

### Building StarDist Extension
The compiled NMS extension lives in `stardist_ext/`:
```bash
pip install -U scikit-build-core
pip wheel ./stardist_ext -w ./wheelhouse
pip install ./wheelhouse/senoquant_stardist_ext-*.whl
```
CI builds wheels via `cibuildwheel` in `.github/workflows/build-stardist-ext.yml`.

## Code Conventions

### File Paths
- Always use `pathlib.Path` (not string paths)
- Model directories use `Path(__file__).parent / model_name` pattern

### Settings Schema in details.json
```json
{
  "settings": [
    {
      "key": "object_diameter_px",
      "label": "Object diameter (px)",
      "type": "float",  // "int", "float", or "bool"
      "decimals": 1,
      "min": 1.0, "max": 500.0, "default": 30.0,
      "enabled_by": ["other_key"],  // Optional conditional visibility
      "disabled_by": ["another_key"]
    }
  ]
}
```

### Dataclass Usage
- Heavy use of `@dataclass(slots=True)` for config objects (batch, quantification features)
- Serialization via `asdict()` → JSON for batch job persistence

### Frontend Signal Patterns
- Use Qt signals for backend → frontend communication
- Backend classes emit signals when processing completes or errors occur
- Frontend connects signals in `__init__` to update UI state

### Layer Name Conventions
- Segmentation outputs: `"Nuclear Mask"`, `"Cytoplasmic Mask"`
- Spot labels: `spot_label_name(channel_name)` → `"{channel_name} spots"`

## Common Pitfalls

1. **BioIO reader failures on large files:** Install dedicated plugins (`bioio-ome-tiff`, `bioio-nd2`, etc.) instead of relying on generic readers
2. **Protobuf version conflicts:** Always reinstall protobuf AFTER TensorFlow when doing ONNX conversion
3. **Headless testing:** Import stubs in `conftest.py` handle missing Qt/napari; don't import GUI modules at top level in tests
4. **Model not discovered:** Check folder name matches expectations; ensure `details.json` exists
5. **Batch quantification failures:** Verify `BatchViewer` shim has correct layer names matching quantification feature expectations

## Adding New Features

### New Segmentation Model
1. Create `src/senoquant/tabs/segmentation/models/<model_name>/`
2. Add `details.json` with tasks (`nuclear`/`cytoplasmic` support)
3. Optionally add `model.py` with `SenoQuantSegmentationModel` subclass
4. Implement `predict()` method returning labeled mask

### New Quantification Feature
1. Create module under `features/<feature_name>/`
2. Define `<Feature>Data(FeatureData)` dataclass
3. Create `<Feature>Feature(SenoQuantFeature)` class:
   - Set `feature_type` string (UI label)
   - Set `order` int (registry position)
   - Implement `build(context: FeatureUIContext)` → Qt widget
   - Implement `export(feature_config, temp_dir, ...)` → write files
4. Add new `FeatureData` subclass to serialization helpers in `batch/config.py`

## Documentation
- User docs: `docs/user/*.md` (installation, quickstart, segmentation, quantification, batch)
- Developer docs: `docs/developer/*.md` (architecture, models, contributing)
- Docs built with MkDocs Material: `mkdocs serve` for local preview
- CI publishes to GitHub Pages via `.github/workflows/docs.yml`
