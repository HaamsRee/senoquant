"""Benchmark 2D single-channel nuclear segmentation models.

This script provides a small, file-based benchmarking loop for nuclear
segmentation models that follow the SenoQuant segmentation API. It is limited
to single-channel 2D inputs and compares each predicted mask against a matching
ground-truth mask using binary Dice and IoU.

The benchmark intentionally avoids the full napari widget stack. Instead, it
creates a minimal image-layer wrapper, loads segmentation models through the
existing backend, and writes one CSV file containing per-image scores plus a
mean row.
"""

from __future__ import annotations

import argparse
import csv
import importlib
import json
import sys
import types
from pathlib import Path

import numpy as np


class ImageLayer:
    """Minimal napari-like image layer.

    Parameters
    ----------
    data : array-like
        Image data that will be exposed through the ``data`` attribute.
    name : str, optional
        Layer name passed to models that may inspect the layer metadata.

    Attributes
    ----------
    data : array-like
        Stored image data.
    name : str
        Human-readable layer name.
    metadata : dict[str, object]
        Mutable metadata mapping included for compatibility with code that
        expects napari layer objects.
    """

    def __init__(self, data, name: str = "image") -> None:
        """Initialize a lightweight image layer wrapper.

        Parameters
        ----------
        data : array-like
            Input image data for the benchmark case.
        name : str, optional
            Layer name exposed to the segmentation model.
        """
        self.data = data
        self.name = name
        self.metadata: dict[str, object] = {}


def main() -> int:
    """Run the command-line interface.

    Returns
    -------
    int
        Process exit code. Returns ``0`` after a successful benchmark run.
    """
    root = Path(__file__).resolve().parent

    parser = argparse.ArgumentParser(
        description="Benchmark 2D nuclear segmentation masks against ground truth."
    )
    parser.add_argument("--model", required=True, help="Segmentation model name.")
    parser.add_argument(
        "--models-root",
        type=Path,
        default=None,
        help="Optional root folder for external segmentation models.",
    )
    parser.add_argument(
        "--images",
        type=Path,
        default=root / "images",
        help="Folder containing input images.",
    )
    parser.add_argument(
        "--ground-truth",
        type=Path,
        default=root / "ground_truth",
        help="Folder containing ground-truth masks.",
    )
    parser.add_argument(
        "--settings-json",
        type=Path,
        default=None,
        help="Optional JSON file with model settings.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional CSV output path.",
    )
    args = parser.parse_args()

    settings = load_settings(args.settings_json)
    output_path = args.output or (root / "results" / f"{args.model}.csv")
    rows = run_benchmark(
        model_name=args.model,
        images_dir=args.images.resolve(),
        ground_truth_dir=args.ground_truth.resolve(),
        settings=settings,
        models_root=args.models_root.resolve() if args.models_root else None,
    )
    write_csv(output_path, rows)
    print(f"Wrote {output_path}")
    return 0


def run_benchmark(
    *,
    model_name: str,
    images_dir: Path,
    ground_truth_dir: Path,
    settings: dict[str, object],
    models_root: Path | None,
) -> list[dict[str, object]]:
    """Run a nuclear-segmentation benchmark across all matched cases.

    Parameters
    ----------
    model_name : str
        Name of the segmentation model to load.
    images_dir : pathlib.Path
        Directory containing 2D single-channel input images.
    ground_truth_dir : pathlib.Path
        Directory containing ground-truth masks matched by basename.
    settings : dict[str, object]
        Model settings forwarded directly to ``model.run(...)``.
    models_root : pathlib.Path or None
        Optional root directory for external segmentation model folders. When
        omitted, the default SenoQuant segmentation model directory is used.

    Returns
    -------
    list[dict[str, object]]
        Per-case result rows suitable for CSV export. The final row is a
        summary row with ``case_id="MEAN"`` when at least one case was run.

    Raises
    ------
    ValueError
        Raised when a ground-truth mask is missing, when an image is not 2D,
        or when the model returns an unexpected payload.
    """
    image_paths = collect_cases(images_dir)
    ground_truth_paths = collect_cases(ground_truth_dir)
    backend = load_segmentation_backend()(models_root=models_root)
    model = backend.get_model(model_name)

    rows: list[dict[str, object]] = []
    for case_id, image_path in sorted(image_paths.items()):
        if case_id not in ground_truth_paths:
            raise ValueError(f"Missing ground truth for {case_id!r}.")

        image = load_array(image_path)
        ground_truth = load_array(ground_truth_paths[case_id])
        if image.ndim != 2 or ground_truth.ndim != 2:
            raise ValueError(f"{case_id!r} must be 2D for this benchmark.")

        result = model.run(
            task="nuclear",
            layer=ImageLayer(image),
            settings=settings,
        )
        prediction = np.asarray(result["masks"])
        row = {
            "case_id": case_id,
            "dice": dice_score(prediction, ground_truth),
            "iou": iou_score(prediction, ground_truth),
            "pred_pixels": int(np.count_nonzero(prediction > 0)),
            "gt_pixels": int(np.count_nonzero(ground_truth > 0)),
        }
        rows.append(row)

    if rows:
        rows.append(
            {
                "case_id": "MEAN",
                "dice": float(np.mean([row["dice"] for row in rows])),
                "iou": float(np.mean([row["iou"] for row in rows])),
                "pred_pixels": "",
                "gt_pixels": "",
            }
        )
    return rows


def load_segmentation_backend():
    """Load the SenoQuant segmentation backend without importing the UI root.

    Returns
    -------
    type
        The ``SegmentationBackend`` class from
        ``senoquant.tabs.segmentation.backend``.

    Notes
    -----
    The main ``senoquant`` package imports the widget layer eagerly. This
    helper injects minimal package objects into ``sys.modules`` so the
    segmentation backend can be imported directly from ``src/senoquant``.
    """
    repo_root = Path(__file__).resolve().parents[1]
    senoquant_root = repo_root / "src" / "senoquant"

    if "senoquant" not in sys.modules:
        module = types.ModuleType("senoquant")
        module.__path__ = [str(senoquant_root)]  # type: ignore[attr-defined]
        module.__package__ = "senoquant"
        sys.modules["senoquant"] = module

    if "senoquant.tabs" not in sys.modules:
        module = types.ModuleType("senoquant.tabs")
        module.__path__ = [str(senoquant_root / "tabs")]  # type: ignore[attr-defined]
        module.__package__ = "senoquant.tabs"
        sys.modules["senoquant.tabs"] = module

    backend_module = importlib.import_module("senoquant.tabs.segmentation.backend")
    return backend_module.SegmentationBackend


def collect_cases(folder: Path) -> dict[str, Path]:
    """Collect benchmark files from a directory.

    Parameters
    ----------
    folder : pathlib.Path
        Directory containing image or ground-truth files.

    Returns
    -------
    dict[str, pathlib.Path]
        Mapping from case identifier to file path. Case identifiers are derived
        by stripping all filename suffixes.

    Raises
    ------
    FileNotFoundError
        Raised when ``folder`` does not exist.
    ValueError
        Raised when no benchmark files are found.
    """
    if not folder.exists():
        raise FileNotFoundError(f"Missing folder: {folder}")

    cases: dict[str, Path] = {}
    for path in sorted(folder.iterdir()):
        if not path.is_file() or path.name.startswith("."):
            continue
        case_id = strip_all_suffixes(path.name)
        cases[case_id] = path
    if not cases:
        raise ValueError(f"No files found in {folder}")
    return cases


def strip_all_suffixes(name: str) -> str:
    """Remove all suffixes from a filename.

    Parameters
    ----------
    name : str
        Filename or path-like leaf name.

    Returns
    -------
    str
        Basename with every suffix removed. For example,
        ``"sample.ome.tif"`` becomes ``"sample"``.
    """
    value = name
    while True:
        suffix = Path(value).suffix
        if not suffix:
            return value
        value = value[: -len(suffix)]


def load_settings(path: Path | None) -> dict[str, object]:
    """Load model settings from JSON.

    Parameters
    ----------
    path : pathlib.Path or None
        Path to a JSON file containing a single object. When ``None``, an empty
        settings mapping is returned.

    Returns
    -------
    dict[str, object]
        Parsed settings dictionary.

    Raises
    ------
    ValueError
        Raised when the JSON payload is not an object.
    """
    if path is None:
        return {}
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("Settings JSON must contain an object.")
    return dict(payload)


def load_array(path: Path) -> np.ndarray:
    """Load an array from a supported benchmark file format.

    Parameters
    ----------
    path : pathlib.Path
        Input file path.

    Returns
    -------
    numpy.ndarray
        Loaded array data.

    Raises
    ------
    ValueError
        Raised when the file type is unsupported or an ``.npz`` archive does
        not contain exactly one array.

    Notes
    -----
    Supported file types are:

    - ``.npy``
    - ``.npz`` containing exactly one array
    - ``.tif``
    - ``.tiff``
    """
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


def dice_score(prediction, ground_truth) -> float:
    """Compute the binary Dice score between two masks.

    Parameters
    ----------
    prediction : array-like
        Predicted label or binary mask array. Any non-zero value is treated as
        foreground.
    ground_truth : array-like
        Ground-truth label or binary mask array. Any non-zero value is treated
        as foreground.

    Returns
    -------
    float
        Dice similarity coefficient in the range ``[0, 1]``. Returns ``1.0``
        when both masks are empty.
    """
    pred = np.asarray(prediction) > 0
    truth = np.asarray(ground_truth) > 0
    intersection = int(np.count_nonzero(pred & truth))
    pred_pixels = int(np.count_nonzero(pred))
    truth_pixels = int(np.count_nonzero(truth))
    if pred_pixels == 0 and truth_pixels == 0:
        return 1.0
    return (2.0 * intersection) / max(pred_pixels + truth_pixels, 1)


def iou_score(prediction, ground_truth) -> float:
    """Compute the binary intersection-over-union between two masks.

    Parameters
    ----------
    prediction : array-like
        Predicted label or binary mask array. Any non-zero value is treated as
        foreground.
    ground_truth : array-like
        Ground-truth label or binary mask array. Any non-zero value is treated
        as foreground.

    Returns
    -------
    float
        Intersection-over-union in the range ``[0, 1]``. Returns ``1.0`` when
        both masks are empty.
    """
    pred = np.asarray(prediction) > 0
    truth = np.asarray(ground_truth) > 0
    intersection = int(np.count_nonzero(pred & truth))
    union = int(np.count_nonzero(pred | truth))
    if union == 0:
        return 1.0
    return intersection / union


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    """Write benchmark rows to CSV.

    Parameters
    ----------
    path : pathlib.Path
        Output CSV path.
    rows : list[dict[str, object]]
        Benchmark rows returned by :func:`run_benchmark`.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["case_id", "dice", "iou", "pred_pixels", "gt_pixels"],
        )
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    raise SystemExit(main())
