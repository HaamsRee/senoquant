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
        "name": name,
        "description": f"{name} test model",
        "version": "0.1.0",
        "settings": [],
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

def test_segmentation_backend_list_cytoplasmic_models() -> None:
    """Test listing cytoplasmic models from default backend.

    Returns
    -------
    None
    """
    backend = SegmentationBackend()
    cyto_models = backend.list_model_names(task="cytoplasmic")
    
    # Should have at least nuclear_dilation
    assert len(cyto_models) > 0
    assert "nuclear_dilation" in cyto_models


def test_segmentation_backend_get_nuclear_dilation() -> None:
    """Test retrieving nuclear dilation model.

    Returns
    -------
    None
    """
    backend = SegmentationBackend()
    model = backend.get_model("nuclear_dilation")
    
    assert model is not None
    assert model.name == "nuclear_dilation"
    assert model.supports_task("cytoplasmic")
    assert not model.supports_task("nuclear")


def test_model_base_supports_task() -> None:
    """Test model task support checking.

    Returns
    -------
    None
    """
    backend = SegmentationBackend()
    model = backend.get_model("default_2d")
    
    # default_2d should support nuclear
    assert model.supports_task("nuclear")


def test_model_base_display_order() -> None:
    """Test model display ordering.

    Returns
    -------
    None
    """
    backend = SegmentationBackend()
    model = backend.get_model("default_2d")
    order = model.display_order()
    
    # Order should be numeric or None
    assert order is None or isinstance(order, (int, float))


def test_model_base_list_settings() -> None:
    """Test model settings listing.

    Returns
    -------
    None
    """
    backend = SegmentationBackend()
    model = backend.get_model("default_2d")
    settings = model.list_settings()
    
    # Should return a list of settings
    assert isinstance(settings, list)


def test_segmentation_backend_preload_models() -> None:
    """Test preloading all models.

    Returns
    -------
    None
    """
    backend = SegmentationBackend()
    # preload_models should not raise
    backend.preload_models()
    # After preloading, models should be cached
    assert backend._preloaded is True


def test_segmentation_backend_get_preloaded_model() -> None:
    """Test getting preloaded model.

    Returns
    -------
    None
    """
    backend = SegmentationBackend()
    # Get a model that hasn't been loaded yet
    model = backend.get_preloaded_model("default_2d")
    assert model is not None
    assert model.name == "default_2d"


def test_segmentation_backend_load_model_class_not_exists() -> None:
    """Test _load_model_class returns None when model.py doesn't exist.

    Returns
    -------
    None
    """
    backend = SegmentationBackend()
    # A model that doesn't exist should return None
    result = backend._load_model_class("nonexistent_model_xyz")
    assert result is None


def test_segmentation_backend_list_model_names_empty_root(tmp_path: Path) -> None:
    """Test list_model_names with non-existent root.

    Returns
    -------
    None
    """
    non_existent = tmp_path / "nonexistent"
    backend = SegmentationBackend(models_root=non_existent)
    names = backend.list_model_names()
    assert names == []


def test_segmentation_backend_list_model_names_with_task(tmp_path: Path) -> None:
    """Test list_model_names with task filter.

    Returns
    -------
    None
    """
    _write_model(tmp_path, "model_nuclear", supported=True)
    _write_model(tmp_path, "model_other", supported=False)

    backend = SegmentationBackend(models_root=tmp_path)
    # Filter by nuclear task
    names = backend.list_model_names(task="nuclear")
    assert "model_nuclear" in names
