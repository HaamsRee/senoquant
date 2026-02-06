# Contributing

Thank you for your interest in contributing to SenoQuant. This guide helps you set up a development environment and follow the project workflow.

## Development setup

### Environment creation

```bash
conda create -n senoquant-dev python=3.11
conda activate senoquant-dev
pip install uv
uv pip install "napari[all]"
uv pip install -e .
```

### Verify installation

Launch napari and open the plugin from the `Plugins` menu.

```bash
napari
```

Select `Plugins` -> `SenoQuant` to verify the plugin loads correctly.

## Testing

### Running tests

The project uses `pytest` with an 80% coverage requirement.

```bash
conda activate senoquant-dev
pytest
```

### Test configuration

- **Config file**: `pytest.ini` specifies coverage thresholds and test discovery.
- **Fixtures**: `tests/conftest.py` provides stubs for headless GUI dependencies (DummySignal and mock napari layers).
- **Coverage**: Tests require >=80% line coverage to pass.

### Writing tests

When adding new functionality:

1. **Create test modules** in the corresponding `tests/` subdirectory.
2. **Use fixtures** from `conftest.py` for napari layer mocks.
3. **Leverage `tmp_path`** for isolated file operations.
4. **Mock external dependencies** (BioIO and Qt signals) where appropriate.

Example test structure:

```python
def test_new_feature(tmp_path):
    # Arrange.
    test_file = tmp_path / "test.tif"
    test_file.write_bytes(b"fake data")

    # Act.
    result = my_function(test_file)

    # Assert.
    assert result is not None
```

### Headless testing

Tests run without a display server.

- Qt dependencies are stubbed in `conftest.py`.
- Avoid importing GUI modules at top level in test files.
- Use `pytest-qt` for Qt-specific testing when needed.

## Documentation

### Building documentation locally

Install documentation dependencies.

```bash
pip install mkdocs mkdocs-material mkdocstrings[python]
```

Serve documentation locally for live preview.

```bash
mkdocs serve
```

Visit `http://127.0.0.1:8000` to view the docs.

Build the static site.

```bash
mkdocs build
```

### Documentation structure

- **User guide** (`docs/user/`): End-user documentation for each plugin tab.
- **Developer guide** (`docs/developer/`): Architecture, models, features, and contribution details.
- **API reference** (`docs/api/`): Auto-generated via mkdocstrings (do not edit manually).

### Writing documentation

- Use **Markdown** with Material for MkDocs extensions.
- Include **code examples** with proper syntax highlighting.
- Add **screenshots** to `docs/assets/` for UI documentation.
- Reference specific line numbers when linking to code, for example: `[file.py](file.py#L10)`.

## Code conventions

### Style guidelines

- **Type hints**: Use modern Python 3.11+ type annotations.
- **Docstrings**: Use NumPy style for public APIs.
- **Imports**: Use absolute imports from `senoquant`.
- **File paths**: Use `pathlib.Path` instead of string paths.

### Architecture patterns

- **Frontend/backend split**: Each tab has `frontend.py` (Qt UI) and `backend.py` (pure logic).
- **Settings schema**: Define settings in `details.json` with `type`, `min`, `max`, and `default` keys.
- **Model discovery**: Place models in `models/<name>/` with `details.json` and optional `model.py`.
- **Dataclasses**: Use `@dataclass(slots=True)` for config objects.

### Naming conventions

- **Segmentation outputs**: `<image>_<model>_nuc_labels` or `<image>_<model>_cyto_labels`.
- **Spot outputs**: `<image>_<detector>_spot_labels`.
- **Private methods**: Prefix with `_` (for example, `_compute_internal()`).
- **Signals**: Qt signals use past tense (for example, `segmentation_completed` and `error_occurred`).

## Dependencies

### Core dependencies

- **napari**: Not pinned in `pyproject.toml`; install separately.
- **Qt**: Via QtPy (supports PyQt5, PyQt6, PySide2, and PySide6).
- **BioIO**: Format-agnostic image reader with 50+ plugins.
- **ONNX Runtime**: For StarDist model inference.

### Optional dependencies

Defined in `pyproject.toml`:

- `.[all]`: Full stack including napari and optional dependencies.

## Extending SenoQuant

### Segmentation model

1. **Create folder**: `src/senoquant/tabs/segmentation/models/my_model/`.
2. **Add metadata**: `details.json` with model info, tasks, and settings.
3. **Implement logic**: `model.py` subclassing `SenoQuantSegmentationModel`.
4. **Test**: Verify the model appears in the Segmentation tab dropdown.

See [Models & Detectors](models.md) for the detailed guide.

### Spot detector

Use the same pattern as segmentation models under `src/senoquant/tabs/spots/models/`.

### Quantification feature

1. **Create module**: `src/senoquant/tabs/quantification/features/my_feature/`.
2. **Define data class**: Subclass `FeatureData` for configuration state.
3. **Implement feature**: Subclass `SenoQuantFeature` with `build()` and `export()` methods.
4. **Register**: Add to `FEATURE_DATA_FACTORY` in `features/__init__.py`.
5. **Batch settings bundles**: Update batch feature serialize/deserialize cases in `src/senoquant/tabs/batch/config.py`.

See [Quantification features](quantification-features.md) for the detailed guide.

### Visualization plot

1. **Create module**: `src/senoquant/tabs/visualization/plots/my_plot.py`.
2. **Define plot class**: Subclass `SenoQuantPlot` with `feature_type` and `order`.
3. **Implement output**: Write files in `plot(temp_dir, input_path, export_format, ...)`.
4. **Register typed data**: Add custom `PlotData` class to `FEATURE_DATA_FACTORY` when needed.
5. **Test**: Add handler and backend tests under `tests/senoquant/tabs/visualization/`.

See [Visualization tab](visualization.md) for implementation details.

### New tab

Create a new tab package under `src/senoquant/tabs/`, export it from `src/senoquant/tabs/__init__.py`, and wire it into `src/senoquant/_widget.py`.

See [Adding tabs](adding-tabs.md) for the full wiring checklist.

## Submitting changes

### Pull request checklist

- [ ] Tests pass locally (`pytest`).
- [ ] Code follows style conventions.
- [ ] New features have test coverage.
- [ ] Documentation is updated (user docs, docstrings, and developer guides).
- [ ] No breaking changes to the batch config format (maintain backward compatibility).

### Commit messages

Use descriptive commit messages.

```text
Improve U-FISH spot detector threshold behavior

- Adjust threshold handling for edge cases.
- Update detector settings help text.
- Add regression tests for low-signal images.
```

## Common pitfalls

1. **Protobuf version conflicts**: Reinstall protobuf after TensorFlow when doing ONNX conversion.
2. **Headless testing**: `conftest.py` stubs handle missing Qt/napari; avoid top-level GUI imports in test files.
3. **Model not discovered**: Check folder naming and confirm `details.json` exists.
4. **Batch quantification failures**: Verify the `BatchViewer` shim has correct layer names.

## Getting help

- **GitHub issues**: Report bugs or request features.
- **Discussions**: Ask questions or share use cases.
- **Documentation**: Consult the user and developer guides.

## License

SenoQuant is released under the BSD 3-Clause License. By contributing, you agree to license your contributions under the same license.
