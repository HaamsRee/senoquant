# Contributing

Thank you for your interest in contributing to SenoQuant! This guide will help you set up your development environment and understand the project workflow.

## Development Setup

### Environment Creation

```bash
conda create -n senoquant-dev python=3.11
conda activate senoquant-dev
pip install uv
uv pip install "napari[all]"
uv pip install -e .
```

### Verify Installation

Launch napari and open the plugin from the `Plugins` menu:

```bash
napari
```

Select `Plugins` → `SenoQuant` to verify the plugin loads correctly.

## Testing

### Running Tests

The project uses `pytest` with an 80% coverage requirement:

```bash
conda activate senoquant-dev
pytest
```

### Test Configuration

- **Config file**: `pytest.ini` specifies coverage thresholds and test discovery
- **Fixtures**: `tests/conftest.py` provides stubs for headless GUI dependencies (DummySignal, mock napari layers)
- **Coverage**: Tests require ≥80% line coverage to pass

### Writing Tests

When adding new functionality:

1. **Create test modules** in the corresponding `tests/` subdirectory
2. **Use fixtures** from `conftest.py` for napari layer mocks
3. **Leverage `tmp_path`** for isolated file operations
4. **Mock external dependencies** (BioIO, Qt signals) where appropriate

Example test structure:
```python
def test_new_feature(tmp_path):
    # Arrange
    test_file = tmp_path / "test.tif"
    test_file.write_bytes(b"fake data")
    
    # Act
    result = my_function(test_file)
    
    # Assert
    assert result is not None
```

### Headless Testing

Tests run without a display server:
- Qt dependencies are stubbed in `conftest.py`
- Avoid importing GUI modules at top level in test files
- Use `pytest-qt` plugin for Qt-specific testing if needed

## Documentation

### Building Documentation Locally

Install documentation dependencies:

```bash
pip install mkdocs mkdocs-material mkdocstrings[python]
```

Serve documentation locally for live preview:

```bash
mkdocs serve
```

Visit `http://127.0.0.1:8000` to view the docs.

Build static site:

```bash
mkdocs build
```

### Documentation Structure

- **User Guide** (`docs/user/`): End-user documentation for each plugin tab
- **Developer Guide** (`docs/developer/`): Architecture, models, features, and contribution info
- **API Reference** (`docs/api/`): Auto-generated via mkdocstrings (do not edit manually)

### Writing Documentation

- Use **Markdown** with Material for MkDocs extensions
- Include **code examples** with proper syntax highlighting
- Add **screenshots** to `docs/assets/` for UI documentation
- Reference **specific line numbers** when linking to code: `[file.py](file.py#L10)`

## Code Conventions

### Style Guidelines

- **Type hints**: Use modern Python 3.11+ type annotations
- **Docstrings**: NumPy style for public APIs
- **Imports**: Use absolute imports from `senoquant`
- **File paths**: Always use `pathlib.Path` (not string paths)

### Architecture Patterns

- **Frontend/Backend split**: Each tab has `frontend.py` (Qt UI) and `backend.py` (pure logic)
- **Settings schema**: Define in `details.json` with `type`, `min`, `max`, `default` keys
- **Model discovery**: Place models in `models/<name>/` with `details.json` + optional `model.py`
- **Dataclasses**: Use `@dataclass(slots=True)` for config objects

### Naming Conventions

- **Segmentation outputs**: `<image>_<model>_nuc_labels` or `<image>_<model>_cyto_labels`
- **Spot outputs**: `<image>_<detector>_spot_labels`
- **Private methods**: Prefix with `_` (e.g., `_compute_internal()`)
- **Signals**: Qt signals use past tense (e.g., `segmentation_completed`, `error_occurred`)

## Dependencies

### Core Dependencies

- **napari**: Not pinned in `pyproject.toml`; install separately
- **Qt**: Via QtPy (supports PyQt5/PyQt6/PySide2/PySide6)
- **BioIO**: Format-agnostic image reader with 50+ plugins
- **ONNX Runtime**: For StarDist model inference

### Optional Dependencies

Defined in `pyproject.toml`:

- `.[distributed]`: Dask for parallel processing
- `.[gpu]`: GPU acceleration extras
- `.[all]`: Full stack including napari and optional deps

### BioIO Reader Plugins

For reliable format support, install dedicated readers:

```bash
pip install bioio-tifffile bioio-ome-tiff bioio-nd2 bioio-lif bioio-czi
```

See [Data & Readers](../user/data.md) for complete list.

## Adding New Features

### Segmentation Model

1. **Create folder**: `src/senoquant/tabs/segmentation/models/my_model/`
2. **Add metadata**: `details.json` with model info, tasks, and settings
3. **Implement logic** (optional): `model.py` subclassing `SenoQuantSegmentationModel`
4. **Test**: Verify model appears in Segmentation tab dropdown

See [Models & Detectors](models.md) for detailed guide.

### Spot Detector

Same pattern as segmentation models but in `src/senoquant/tabs/spots/models/`.

### Quantification Feature

1. **Create module**: `src/senoquant/tabs/quantification/features/my_feature/`
2. **Define data class**: Subclass `FeatureData` for configuration state
3. **Implement feature**: Subclass `SenoQuantFeature` with `build()` and `export()` methods
4. **Register**: Add to `FEATURE_DATA_FACTORY` in `features/__init__.py`

See [Quantification Features](quantification-features.md) for detailed guide.

## Submitting Changes

### Pull Request Checklist

- [ ] Tests pass locally (`pytest`)
- [ ] Code follows style conventions
- [ ] New features have test coverage
- [ ] Documentation updated (user docs, docstrings, developer guides)
- [ ] No breaking changes to batch config format (maintain backward compatibility)

### Commit Messages

Use descriptive commit messages:

```
Add RMP spot detector with rotational morphology

- Implement rotational morphological processing algorithm
- Add settings UI for angle step and threshold
- Include tests for normalization and watershed
```

## Common Pitfalls

1. **BioIO reader failures on large files**: Install dedicated plugins (`bioio-ome-tiff`, `bioio-nd2`, etc.)
2. **Protobuf version conflicts**: Always reinstall protobuf AFTER TensorFlow when doing ONNX conversion
3. **Headless testing**: Import stubs in `conftest.py` handle missing Qt/napari; don't import GUI modules at top level in tests
4. **Model not discovered**: Check folder name matches expectations; ensure `details.json` exists
5. **Batch quantification failures**: Verify `BatchViewer` shim has correct layer names

## Getting Help

- **GitHub Issues**: Report bugs or request features
- **Discussions**: Ask questions or share use cases
- **Documentation**: Consult user and developer guides

## License

SenoQuant is released under the MIT License. By contributing, you agree to license your contributions under the same license.
