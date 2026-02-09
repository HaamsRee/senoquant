"""Tests for spots backend utilities.

Notes
-----
Covers detector loading and colocalization computation.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from senoquant.tabs.spots.backend import SpotsBackend
from senoquant.tabs.spots.models.base import SenoQuantSpotDetector


def _write_detector(tmp_path: Path, name: str) -> None:
    model_dir = tmp_path / name
    model_dir.mkdir(parents=True)
    (model_dir / "details.json").write_text(
        json.dumps(
            {
                "name": name,
                "description": f"{name} test detector",
                "version": "0.1.0",
                "settings": [],
            }
        )
    )
    (model_dir / "model.py").write_text(
        "from senoquant.tabs.spots.models.base import SenoQuantSpotDetector\n"
        "class CustomDetector(SenoQuantSpotDetector):\n"
        "    def __init__(self, models_root=None):\n"
        "        super().__init__(\"" + name + "\", models_root=models_root)\n"
    )


def test_compute_colocalization() -> None:
    """Compute colocalization centroids.

    Returns
    -------
    None
    """
    data_a = np.array([[1, 0], [0, 0]], dtype=np.int32)
    data_b = np.array([[1, 0], [0, 0]], dtype=np.int32)
    backend = SpotsBackend(models_root=Path("/tmp"))
    result = backend.compute_colocalization(data_a, data_b)
    assert result["points"].shape[1] == 2


def test_list_detector_names(tmp_path: Path) -> None:
    """List detectors from custom root.

    Returns
    -------
    None
    """
    _write_detector(tmp_path, "detector_a")
    backend = SpotsBackend(models_root=tmp_path)
    assert backend.list_detector_names() == ["detector_a"]


def test_get_detector_loads_subclass(tmp_path: Path) -> None:
    """Load detector subclass from model.py.

    Returns
    -------
    None
    """
    _write_detector(tmp_path, "detector_b")
    backend = SpotsBackend(models_root=tmp_path)
    detector = backend.get_detector("detector_b")
    assert isinstance(detector, SenoQuantSpotDetector)
    assert detector.name == "detector_b"
