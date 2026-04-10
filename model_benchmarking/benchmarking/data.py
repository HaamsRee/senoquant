"""File loading and lightweight runtime utilities for benchmarking."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import numpy as np


def collect_cases(folder: Path) -> dict[str, Path]:
    """Collect benchmark files from a directory."""
    if not folder.exists():
        raise FileNotFoundError(f"Missing folder: {folder}")

    cases: dict[str, Path] = {}
    for path in sorted(folder.iterdir()):
        if not path.is_file() or path.name.startswith("."):
            continue
        cases[strip_all_suffixes(path.name)] = path

    if not cases:
        raise ValueError(f"No files found in {folder}")
    return cases


def strip_all_suffixes(name: str) -> str:
    """Remove every suffix from a filename."""
    value = name
    while True:
        suffix = Path(value).suffix
        if not suffix:
            return value
        value = value[: -len(suffix)]


def load_settings(path: Path | None) -> dict[str, object]:
    """Load model settings from JSON."""
    if path is None:
        return {}

    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if not isinstance(payload, dict):
        raise ValueError("Settings JSON must contain an object.")
    return dict(payload)


def load_array(path: Path) -> np.ndarray:
    """Load a benchmark array from ``.npy``, ``.npz``, or TIFF."""
    suffix = path.suffix.lower()
    if suffix == ".npy":
        return np.load(path, allow_pickle=False)
    if suffix == ".npz":
        with np.load(path, allow_pickle=False) as payload:
            keys = list(payload.keys())
            if len(keys) != 1:
                raise ValueError(f"{path} must contain exactly one array.")
            return payload[keys[0]]
    if suffix in {".tif", ".tiff"}:
        import tifffile

        return tifffile.imread(path)
    raise ValueError(f"Unsupported file type: {path}")


def configure_matplotlib_cache() -> None:
    """Point matplotlib at a writable cache directory when needed."""
    cache_root = Path(tempfile.gettempdir()) / "senoquant-matplotlib-cache"
    cache_root.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(cache_root))
    os.environ.setdefault("XDG_CACHE_HOME", str(cache_root))


def format_metric_value(value: float) -> str:
    """Format a metric value for compact display."""
    formatted = f"{value:.2f}".rstrip("0").rstrip(".")
    return formatted or "0"
