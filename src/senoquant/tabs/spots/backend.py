"""Backend logic for the Spots tab."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
from skimage.measure import label, regionprops

from .models import SenoQuantSpotDetector


class SpotsBackend:
    """Manage spot detectors and their storage locations.

    Parameters
    ----------
    models_root : pathlib.Path or None
        Optional root folder for detector storage. Defaults to the local models
        directory for this tab.
    """

    def __init__(self, models_root: Path | None = None) -> None:
        self._models_root = models_root or (Path(__file__).parent / "models")
        self._detectors: dict[str, SenoQuantSpotDetector] = {}

    def get_detector(self, name: str) -> SenoQuantSpotDetector:
        """Return a detector wrapper for the given name.

        Parameters
        ----------
        name : str
            Detector name used to locate or create the detector folder.

        Returns
        -------
        SenoQuantSpotDetector
            Detector instance.
        """
        detector = self._detectors.get(name)
        if detector is None:
            detector_cls = self._load_detector_class(name)
            if detector_cls is None:
                detector = SenoQuantSpotDetector(name, self._models_root)
            else:
                detector = detector_cls(models_root=self._models_root)
            self._detectors[name] = detector
        return detector

    def list_detector_names(self) -> list[str]:
        """List available detector folders under the models root.

        Returns
        -------
        list[str]
            Sorted detector folder names ordered by display_order, then by name.
        """
        if not self._models_root.exists():
            return []

        entries: list[tuple[float, str]] = []
        for path in self._models_root.iterdir():
            if path.is_dir() and not path.name.startswith("__"):
                detector = self.get_detector(path.name)
                order = detector.display_order()
                order_key = order if order is not None else float("inf")
                entries.append((order_key, path.name))
        entries.sort(key=lambda item: (item[0], item[1]))
        return [name for _, name in entries]

    def _load_detector_class(self, name: str) -> type[SenoQuantSpotDetector] | None:
        """Load the detector class from a detector folder's model.py.

        Parameters
        ----------
        name : str
            Detector folder name under the models root.

        Returns
        -------
        type[SenoQuantSpotDetector] or None
            Concrete detector class to instantiate.
        """
        model_path = self._models_root / name / "model.py"
        if not model_path.exists():
            return None

        module_name = f"senoquant.tabs.spots.models.{name}.model"
        package_name = f"senoquant.tabs.spots.models.{name}"
        spec = importlib.util.spec_from_file_location(module_name, model_path)
        if spec is None or spec.loader is None:
            return None

        module = importlib.util.module_from_spec(spec)
        module.__package__ = package_name
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        candidates = [
            obj
            for obj in module.__dict__.values()
            if isinstance(obj, type)
            and issubclass(obj, SenoQuantSpotDetector)
            and obj is not SenoQuantSpotDetector
        ]
        if not candidates:
            return None
        return candidates[0]

    def compute_colocalization(
        self, data_a: np.ndarray, data_b: np.ndarray
    ) -> dict:
        """Compute colocalization centroids from two label arrays.

        Parameters
        ----------
        data_a : numpy.ndarray
            First label layer data.
        data_b : numpy.ndarray
            Second label layer data.

        Returns
        -------
        dict
            Dictionary containing the ``points`` array.
        """
        intersection = (data_a > 0) & (data_b > 0)
        if not np.any(intersection):
            return {"points": np.empty((0, intersection.ndim), dtype=np.float32)}

        labeled = label(intersection)
        if labeled.max() == 0:
            return {"points": np.empty((0, intersection.ndim), dtype=np.float32)}

        points = [region.centroid for region in regionprops(labeled)]
        coords = np.asarray(points, dtype=np.float32)
        return {"points": coords}
