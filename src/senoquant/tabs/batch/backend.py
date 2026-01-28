"""Backend logic for batch processing workflows."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import numpy as np

from senoquant.reader import core as reader_core
from senoquant.tabs.segmentation.backend import SegmentationBackend
from senoquant.tabs.spots.backend import SpotsBackend


@dataclass(slots=True)
class BatchItemResult:
    """Result metadata for a single processed image."""

    path: Path
    scene_id: str | None
    outputs: dict[str, Path] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


@dataclass(slots=True)
class BatchSummary:
    """Aggregated results for a batch run."""

    input_root: Path
    output_root: Path
    processed: int
    skipped: int
    failed: int
    results: list[BatchItemResult]


@dataclass(slots=True)
class _ArrayLayer:
    """Minimal layer wrapper for detector/model inputs."""

    data: np.ndarray
    rgb: bool = False


class BatchBackend:
    """Backend for batch segmentation and spot detection workflows."""

    def __init__(
        self,
        segmentation_backend: SegmentationBackend | None = None,
        spots_backend: SpotsBackend | None = None,
    ) -> None:
        self._segmentation_backend = segmentation_backend or SegmentationBackend()
        self._spots_backend = spots_backend or SpotsBackend()

    def process_folder(
        self,
        input_path: str,
        output_path: str,
        *,
        segmentation_model: str | None = None,
        segmentation_channel: int = 0,
        segmentation_settings: dict | None = None,
        spot_detector: str | None = None,
        spot_channel: int = 0,
        spot_settings: dict | None = None,
        extensions: Iterable[str] | None = None,
        include_subfolders: bool = False,
        output_format: str = "tif",
        overwrite: bool = False,
        process_all_scenes: bool = False,
    ) -> BatchSummary:
        """Run batch processing on a folder of images.

        Parameters
        ----------
        input_path : str
            Folder containing input images.
        output_path : str
            Folder where outputs should be written.
        segmentation_model : str or None
            Segmentation model name to run. When ``None``, segmentation is skipped.
        segmentation_channel : int
            Channel index to use for segmentation.
        segmentation_settings : dict or None
            Settings dictionary passed to the segmentation model.
        spot_detector : str or None
            Spot detector name to run. When ``None``, spot detection is skipped.
        spot_channel : int
            Channel index to use for spot detection.
        spot_settings : dict or None
            Settings dictionary passed to the spot detector.
        extensions : iterable of str or None
            File extensions to include (e.g. [".tif", ".png"]).
            When ``None``, all files are attempted.
        include_subfolders : bool
            Whether to recurse into subfolders.
        output_format : str
            Output format for arrays ("tif" or "npy").
        overwrite : bool
            Whether to overwrite existing outputs.
        process_all_scenes : bool
            Whether to process all scenes in multi-scene images.

        Returns
        -------
        BatchSummary
            Summary of processed files and outputs.
        """
        input_root = Path(input_path).expanduser()
        output_root = Path(output_path).expanduser()
        output_root.mkdir(parents=True, exist_ok=True)

        normalized_exts = _normalize_extensions(extensions)
        files = list(_iter_input_files(input_root, normalized_exts, include_subfolders))

        results: list[BatchItemResult] = []
        processed = skipped = failed = 0
        seg_settings = segmentation_settings or {}
        spot_settings = spot_settings or {}

        if not segmentation_model and not spot_detector:
            return BatchSummary(
                input_root=input_root,
                output_root=output_root,
                processed=0,
                skipped=0,
                failed=0,
                results=[],
            )

        for path in files:
            scenes = self._iter_scenes(path, process_all_scenes)
            for scene_id in scenes:
                item_result = BatchItemResult(path=path, scene_id=scene_id)
                try:
                    output_dir = self._resolve_output_dir(
                        output_root, path, scene_id, overwrite
                    )
                    if output_dir is None:
                        skipped += 1
                        results.append(item_result)
                        continue

                    if segmentation_model:
                        image = self._load_channel_data(
                            path, segmentation_channel, scene_id
                        )
                        if image is None:
                            raise RuntimeError("Failed to read image data.")
                        seg_layer = _ArrayLayer(image)
                        model = self._segmentation_backend.get_model(
                            segmentation_model
                        )
                        seg_result = model.run(
                            task="nuclear",
                            layer=seg_layer,
                            settings=seg_settings,
                        )
                        masks = seg_result.get("masks")
                        if masks is not None:
                            out_path = _write_array(
                                output_dir,
                                "nuclear_labels",
                                masks,
                                output_format,
                            )
                            item_result.outputs["nuclear_labels"] = out_path

                    if spot_detector:
                        spot_image = self._load_channel_data(
                            path, spot_channel, scene_id
                        )
                        if spot_image is None:
                            raise RuntimeError("Failed to read image data.")
                        spot_layer = _ArrayLayer(spot_image)
                        detector = self._spots_backend.get_detector(spot_detector)
                        spot_result = detector.run(
                            layer=spot_layer,
                            settings=spot_settings,
                        )
                        mask = spot_result.get("mask")
                        if mask is not None:
                            out_path = _write_array(
                                output_dir,
                                "spot_labels",
                                mask,
                                output_format,
                            )
                            item_result.outputs["spot_labels"] = out_path

                    processed += 1
                except Exception as exc:
                    failed += 1
                    item_result.errors.append(str(exc))
                results.append(item_result)

        return BatchSummary(
            input_root=input_root,
            output_root=output_root,
            processed=processed,
            skipped=skipped,
            failed=failed,
            results=results,
        )

    def _iter_scenes(self, path: Path, process_all: bool) -> list[str | None]:
        """Return a list of scene identifiers to process."""
        if not process_all:
            return [None]
        try:
            image = reader_core._open_bioimage(str(path))
        except Exception:
            return [None]
        try:
            scenes = list(getattr(image, "scenes", []) or [])
        finally:
            if hasattr(image, "close"):
                try:
                    image.close()
                except Exception:
                    pass
        return scenes or [None]

    def _resolve_output_dir(
        self,
        output_root: Path,
        path: Path,
        scene_id: str | None,
        overwrite: bool,
    ) -> Path | None:
        """Return output directory for a file/scene, or None to skip."""
        base_name = _basename_for_path(path)
        output_dir = output_root / base_name
        if scene_id:
            output_dir = output_dir / _safe_scene_dir(scene_id)
        if output_dir.exists() and not overwrite:
            return None
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir

    def _load_channel_data(
        self,
        path: Path,
        channel_index: int,
        scene_id: str | None,
    ) -> np.ndarray | None:
        """Load a single-channel image array for the given path."""
        image = reader_core._open_bioimage(str(path))
        try:
            if scene_id:
                image.set_scene(scene_id)
            axes_present = reader_core._axes_present(image)
            dims = getattr(image, "dims", None)
            c_size = getattr(dims, "C", 1) if "C" in axes_present else 1
            z_size = getattr(dims, "Z", 1) if "Z" in axes_present else 1

            if c_size > 1:
                order = "CZYX" if z_size > 1 else "CYX"
            else:
                order = "ZYX" if z_size > 1 else "YX"

            kwargs: dict[str, int] = {}
            if "T" in axes_present and "T" not in order:
                kwargs["T"] = 0
            if "C" in axes_present and "C" not in order:
                kwargs["C"] = 0
            if "Z" in axes_present and "Z" not in order:
                kwargs["Z"] = 0

            data = image.get_image_data(order, **kwargs)
            if c_size > 1:
                if channel_index >= c_size or channel_index < 0:
                    raise ValueError(
                        f"Channel index {channel_index} out of range for {path.name}."
                    )
                data = data[channel_index]
            return np.asarray(data)
        finally:
            if hasattr(image, "close"):
                try:
                    image.close()
                except Exception:
                    pass


def _normalize_extensions(extensions: Iterable[str] | None) -> set[str] | None:
    """Normalize extension list to lowercase with leading dots."""
    if extensions is None:
        return None
    normalized = set()
    for ext in extensions:
        if not ext:
            continue
        cleaned = ext.strip().lower()
        if not cleaned:
            continue
        if not cleaned.startswith("."):
            cleaned = f".{cleaned}"
        normalized.add(cleaned)
    return normalized or None


def _iter_input_files(
    root: Path, extensions: set[str] | None, include_subfolders: bool
) -> Iterable[Path]:
    """Yield input files from a root folder."""
    if not root.exists():
        return
    iterator = root.rglob("*") if include_subfolders else root.iterdir()
    for path in iterator:
        if not path.is_file():
            continue
        if extensions is None:
            yield path
            continue
        name = path.name.lower()
        if any(name.endswith(ext) for ext in extensions):
            yield path


def _basename_for_path(path: Path) -> str:
    """Return a filesystem-friendly base name for a file path."""
    name = path.name
    lowered = name.lower()
    for ext in (".ome.tiff", ".ome.tif", ".tiff", ".tif"):
        if lowered.endswith(ext):
            return name[: -len(ext)]
    if "." in name:
        return name.rsplit(".", 1)[0]
    return name


def _safe_scene_dir(scene_id: str) -> str:
    """Return a sanitized scene identifier for folder naming."""
    safe = scene_id.strip().replace("/", "_").replace("\\", "_")
    return safe or "scene"


def _write_array(
    output_dir: Path, name: str, data: np.ndarray, output_format: str
) -> Path:
    """Write an array to disk in the requested format."""
    output_format = output_format.lower().strip()
    if output_format == "npy":
        path = output_dir / f"{name}.npy"
        np.save(path, data)
        return path

    path = output_dir / f"{name}.tif"
    try:
        import tifffile

        tifffile.imwrite(str(path), data)
        return path
    except Exception:
        fallback = output_dir / f"{name}.npy"
        np.save(fallback, data)
        return fallback
