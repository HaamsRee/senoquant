"""Tests for segmentation backend model management.

Notes
-----
Uses temporary model directories to validate model discovery and loading.
"""

from __future__ import annotations

import json
from pathlib import Path

from senoquant.tabs.segmentation.backend import SegmentationBackend
from senoquant.tabs.segmentation.models.base import SenoQuantSegmentationModel


def _write_model(tmp_path: Path, name: str, supported: bool) -> None:
    model_dir = tmp_path / name
    model_dir.mkdir(parents=True)
    details = {
        "tasks": {
            "nuclear": {"supported": supported},
            "cytoplasmic": {"supported": False},
        }
    }
    (model_dir / "details.json").write_text(json.dumps(details))
    (model_dir / "model.py").write_text(
        "from senoquant.tabs.segmentation.models.base import SenoQuantSegmentationModel\n"
        "class CustomModel(SenoQuantSegmentationModel):\n"
        "    def __init__(self, models_root=None):\n"
        "        super().__init__(\"" + name + "\", models_root=models_root)\n"
    )


def test_list_model_names_filters_task(tmp_path: Path) -> None:
    """List model names with task filtering.

    Returns
    -------
    None
    """
    _write_model(tmp_path, "model_a", supported=True)
    _write_model(tmp_path, "model_b", supported=False)

    backend = SegmentationBackend(models_root=tmp_path)
    names = backend.list_model_names(task="nuclear")
    assert names == ["model_a"]


def test_get_model_loads_subclass(tmp_path: Path) -> None:
    """Load model subclass from model.py.

    Returns
    -------
    None
    """
    _write_model(tmp_path, "model_c", supported=True)
    backend = SegmentationBackend(models_root=tmp_path)
    model = backend.get_model("model_c")
    assert isinstance(model, SenoQuantSegmentationModel)
    assert model.name == "model_c"
