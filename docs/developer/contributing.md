# Contributing

## Development setup

```bash
conda create -n senoquant python=3.11
conda activate senoquant
pip install uv
uv pip install "napari[all]"
uv pip install -e .
```

Run napari and open the plugin from the Plugins menu.

## Tests

There are currently no automated tests in `tests/`. If you add new
functionality, consider adding coverage alongside it.

## Notes on dependencies

- `napari` is not listed as a runtime dependency. Install it separately.
- BioIO readers can be sensitive to large files; dedicated reader plugins
  may improve reliability (see the README for examples).
