"""Batch processing backend.

This module coordinates per-image batch processing for segmentation,
spot detection, and quantification. It provides a single entry point
(`BatchBackend.run_job`) that consumes a :class:`BatchJobConfig` and
produces a :class:`BatchSummary` describing outputs and errors.

The batch run flow is:

1. Normalize input extensions and discover files.
2. Resolve channel mapping for named channels.
3. For each file (and each scene, if enabled):
   a. Optionally run nuclear segmentation.
   b. Optionally run cytoplasmic segmentation.
   c. Optionally run spot detection for selected channels.
   d. Optionally run quantification using a temporary viewer shim.
4. Persist mask outputs and quantification results.

Notes
-----
This backend is intentionally UI-agnostic. UI widgets build a
``BatchJobConfig`` and pass it here for execution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import numpy as np

from senoquant.tabs.quantification.backend import QuantificationBackend
from senoquant.tabs.segmentation.backend import SegmentationBackend
from senoquant.tabs.spots.backend import SpotsBackend
from senoquant.tabs.spots.frontend import _filter_labels_by_size

from .config import BatchChannelConfig, BatchJobConfig
from .layers import BatchViewer, Image, Labels
from .io import (
    basename_for_path,
    iter_input_files,
    load_channel_data,
    list_scenes,
    normalize_extensions,
    resolve_channel_index,
    safe_scene_dir,
    write_array,
)


@dataclass(slots=True)
class BatchItemResult:
    """Result metadata for a single processed image.

    Attributes
    ----------
    path : Path
        Input file path.
    scene_id : str or None
        Scene identifier for multi-scene files.
    outputs : dict of str to Path
        Mapping of output labels to written files.
    errors : list of str
        Collected error messages for this item.
    """

    path: Path
    scene_id: str | None
    outputs: dict[str, Path] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


@dataclass(slots=True)
class BatchSummary:
    """Aggregated results for a batch run.

    Attributes
    ----------
    input_root : Path
        Root input directory.
    output_root : Path
        Root output directory.
    processed : int
        Number of successfully processed items.
    skipped : int
        Number of skipped items.
    failed : int
        Number of failed items.
    results : list of BatchItemResult
        Per-item metadata for the run.
    """

    input_root: Path
    output_root: Path
    processed: int
    skipped: int
    failed: int
    results: list[BatchItemResult]


class BatchBackend:
    """Backend for batch segmentation and spot detection workflows."""

    def __init__(
        self,
        segmentation_backend: SegmentationBackend | None = None,
        spots_backend: SpotsBackend | None = None,
    ) -> None:
        """Initialize the backend.

        Parameters
        ----------
        segmentation_backend : SegmentationBackend or None, optional
            Backend used to resolve segmentation models. A default
            instance is created when omitted.
        spots_backend : SpotsBackend or None, optional
            Backend used to resolve spot detection models. A default
            instance is created when omitted.
        """
        self._segmentation_backend = segmentation_backend or SegmentationBackend()
        self._spots_backend = spots_backend or SpotsBackend()

    def run_job(self, job: BatchJobConfig) -> BatchSummary:
        """Run a batch job using a configuration object.

        Parameters
        ----------
        job : BatchJobConfig
            Fully-populated batch configuration.

        Returns
        -------
        BatchSummary
            Summary of the batch run (counts + per-item metadata).
        """
        return self.process_folder(
            job.input_path,
            job.output_path,
            channel_map=job.channel_map,
            nuclear_model=job.nuclear.model if job.nuclear.enabled else None,
            nuclear_channel=job.nuclear.channel or None,
            nuclear_settings=job.nuclear.settings,
            cyto_model=job.cytoplasmic.model if job.cytoplasmic.enabled else None,
            cyto_channel=job.cytoplasmic.channel or None,
            cyto_nuclear_channel=job.cytoplasmic.nuclear_channel or None,
            cyto_settings=job.cytoplasmic.settings,
            spot_detector=job.spots.detector if job.spots.enabled else None,
            spot_channels=job.spots.channels,
            spot_settings=job.spots.settings,
            spot_min_size=job.spots.min_size,
            spot_max_size=job.spots.max_size,
            quantification_features=job.quantification.features,
            quantification_format=job.quantification.format,
            extensions=job.extensions,
            include_subfolders=job.include_subfolders,
            output_format=job.output_format,
            overwrite=job.overwrite,
            process_all_scenes=job.process_all_scenes,
        )

    def process_folder(
        self,
        input_path: str,
        output_path: str,
        *,
        channel_map: Iterable[BatchChannelConfig | dict] | None = None,
        nuclear_model: str | None = None,
        nuclear_channel: str | int | None = None,
        nuclear_settings: dict | None = None,
        cyto_model: str | None = None,
        cyto_channel: str | int | None = None,
        cyto_nuclear_channel: str | int | None = None,
        cyto_settings: dict | None = None,
        spot_detector: str | None = None,
        spot_channels: Iterable[str | int] | None = None,
        spot_settings: dict | None = None,
        spot_min_size: int = 0,
        spot_max_size: int = 0,
        quantification_features: Iterable[object] | None = None,
        quantification_format: str = "xlsx",
        quantification_tab: object | None = None,
        extensions: Iterable[str] | None = None,
        include_subfolders: bool = False,
        output_format: str = "tif",
        overwrite: bool = False,
        process_all_scenes: bool = False,
        progress_callback: callable | None = None,
    ) -> BatchSummary:
        """Run batch processing on a folder of images.

        Parameters
        ----------
        input_path : str
            Folder containing input images.
        output_path : str
            Folder where outputs should be written.
        channel_map : iterable of BatchChannelConfig or dict, optional
            Mapping from channel names to indices.
        nuclear_model : str or None, optional
            Segmentation model name for nuclei.
        nuclear_channel : str or int or None, optional
            Channel selection for nuclei.
        nuclear_settings : dict or None, optional
            Model settings for nuclear segmentation.
        cyto_model : str or None, optional
            Segmentation model name for cytoplasm.
        cyto_channel : str or int or None, optional
            Channel selection for cytoplasm.
        cyto_nuclear_channel : str or int or None, optional
            Optional nuclear channel used by cytoplasmic models.
        cyto_settings : dict or None, optional
            Model settings for cytoplasmic segmentation.
        spot_detector : str or None, optional
            Spot detection model name.
        spot_channels : iterable of str or int or None, optional
            Channels used for spot detection.
        spot_settings : dict or None, optional
            Detector settings.
        spot_min_size : int, optional
            Minimum spot size in pixels (0 = no minimum).
        spot_max_size : int, optional
            Maximum spot size in pixels (0 = no maximum).
        quantification_features : iterable of object or None, optional
            Quantification feature contexts (UI-generated).
        quantification_format : str, optional
            Output format for quantification (``"csv"`` or ``"xlsx"``).
        quantification_tab : object or None, optional
            Quantification tab instance for viewer wiring.
        extensions : iterable of str or None, optional
            File extensions to include.
        include_subfolders : bool, optional
            Whether to recurse into subfolders.
        output_format : str, optional
            Mask output format (``"tif"`` or ``"npy"``).
        overwrite : bool, optional
            Whether to overwrite existing output folders.
        process_all_scenes : bool, optional
            Whether to process all scenes in multi-scene files.
        progress_callback : callable or None, optional
            Optional callback invoked with (current, total, message) to
            report progress during batch processing.

        Returns
        -------
        BatchSummary
            Summary of the batch run.
        """
        input_root = Path(input_path).expanduser()
        output_root = Path(output_path).expanduser()
        output_root.mkdir(parents=True, exist_ok=True)

        normalized_exts = normalize_extensions(extensions)
        files = list(iter_input_files(input_root, normalized_exts, include_subfolders))

        results: list[BatchItemResult] = []
        processed = skipped = failed = 0
        normalized_channels = _normalize_channel_map(channel_map)
        nuclear_settings = nuclear_settings or {}
        cyto_settings = cyto_settings or {}
        spot_settings = spot_settings or {}
        quant_backend = QuantificationBackend()

        # Count total items to process
        total_items = 0
        for path in files:
            scenes = self._iter_scenes(path, process_all_scenes)
            total_items += len(scenes)

        if progress_callback is not None:
            progress_callback(0, total_items, "Starting batch processing...")

        if (
            not nuclear_model
            and not cyto_model
            and not spot_detector
            and not quantification_features
        ):
            return BatchSummary(
                input_root=input_root,
                output_root=output_root,
                processed=0,
                skipped=0,
                failed=0,
                results=[],
            )

        # Iterate over files and (optionally) scene variants.
        current_item = 0
        for path in files:
            scenes = self._iter_scenes(path, process_all_scenes)
            for scene_id in scenes:
                current_item += 1
                item_result = BatchItemResult(path=path, scene_id=scene_id)
                
                if progress_callback is not None:
                    scene_label = f" (Scene: {scene_id})" if scene_id else ""
                    progress_callback(
                        current_item,
                        total_items,
                        f"Processing {path.name}{scene_label}..."
                    )
                
                try:
                    output_dir = _resolve_output_dir(
                        output_root, path, scene_id, overwrite
                    )
                    if output_dir is None:
                        skipped += 1
                        results.append(item_result)
                        continue

                    # Collect labels for later quantification.
                    labels_data: dict[str, np.ndarray] = {}
                    labels_meta: dict[str, dict] = {}

                    if nuclear_model:
                        channel_idx = resolve_channel_index(
                            nuclear_channel, normalized_channels
                        )
                        image, metadata = load_channel_data(
                            path, channel_idx, scene_id
                        )
                        if image is None:
                            raise RuntimeError("Failed to read nuclear image data.")
                        seg_layer = Image(image, "nuclear", metadata)
                        model = self._segmentation_backend.get_model(nuclear_model)
                        seg_result = model.run(
                            task="nuclear",
                            layer=seg_layer,
                            settings=nuclear_settings,
                        )
                        masks = seg_result.get("masks")
                        if masks is not None:
                            channel_name = _resolve_channel_name(
                                nuclear_channel, normalized_channels
                            )
                            label_name = f"{channel_name}_{nuclear_model}_nuc_labels"
                            out_path = write_array(
                                output_dir,
                                label_name,
                                masks,
                                output_format,
                            )
                            labels_data[label_name] = masks
                            labels_meta[label_name] = metadata
                            item_result.outputs[label_name] = out_path

                    if cyto_model:
                        channel_idx = resolve_channel_index(
                            cyto_channel, normalized_channels
                        )
                        cyto_image, cyto_meta = load_channel_data(
                            path, channel_idx, scene_id
                        )
                        if cyto_image is None:
                            raise RuntimeError(
                                "Failed to read cytoplasmic image data."
                            )
                        cyto_layer = Image(cyto_image, "cytoplasmic", cyto_meta)
                        cyto_nuclear_layer = None
                        if cyto_nuclear_channel is not None:
                            nuclear_idx = resolve_channel_index(
                                cyto_nuclear_channel, normalized_channels
                            )
                            nuclear_image, nuclear_meta = load_channel_data(
                                path, nuclear_idx, scene_id
                            )
                            if nuclear_image is None:
                                raise RuntimeError(
                                    "Failed to read cytoplasmic nuclear data."
                                )
                            cyto_nuclear_layer = Image(
                                nuclear_image, "nuclear", nuclear_meta
                            )
                        model = self._segmentation_backend.get_model(cyto_model)
                        seg_result = model.run(
                            task="cytoplasmic",
                            layer=cyto_layer,
                            nuclear_layer=cyto_nuclear_layer,
                            settings=cyto_settings,
                        )
                        masks = seg_result.get("masks")
                        if masks is not None:
                            channel_name = _resolve_channel_name(
                                cyto_channel, normalized_channels
                            )
                            label_name = f"{channel_name}_{cyto_model}_cyto_labels"
                            out_path = write_array(
                                output_dir,
                                label_name,
                                masks,
                                output_format,
                            )
                            labels_data[label_name] = masks
                            labels_meta[label_name] = cyto_meta
                            item_result.outputs[label_name] = out_path

                    if spot_detector:
                        resolved_spot_channels = list(spot_channels or [])
                        for channel_choice in resolved_spot_channels:
                            channel_idx = resolve_channel_index(
                                channel_choice, normalized_channels
                            )
                            spot_image, spot_meta = load_channel_data(
                                path, channel_idx, scene_id
                            )
                            if spot_image is None:
                                raise RuntimeError(
                                    "Failed to read spot image data."
                                )
                            spot_layer = Image(spot_image, "spots", spot_meta)
                            detector = self._spots_backend.get_detector(
                                spot_detector
                            )
                            spot_result = detector.run(
                                layer=spot_layer,
                                settings=spot_settings,
                            )
                            mask = spot_result.get("mask")
                            if mask is None:
                                continue
                            # Apply size filtering if enabled
                            if spot_min_size > 0 or spot_max_size > 0:
                                mask = _filter_labels_by_size(mask, spot_min_size, spot_max_size)
                            channel_name = _resolve_channel_name(
                                channel_choice, normalized_channels
                            )
                            label_name = f"{channel_name}_{spot_detector}_spot_labels"
                            out_path = write_array(
                                output_dir,
                                label_name,
                                mask,
                                output_format,
                            )
                            labels_data[label_name] = mask
                            labels_meta[label_name] = spot_meta
                            item_result.outputs[label_name] = out_path

                    if quantification_features:
                        viewer = _build_viewer_for_quantification(
                            path,
                            scene_id,
                            normalized_channels,
                            labels_data,
                            labels_meta,
                        )
                        _apply_quantification_viewer(
                            quantification_features, quantification_tab, viewer
                        )
                        result = quant_backend.process(
                            quantification_features,
                            str(output_dir),
                            "",
                            quantification_format,
                        )
                        item_result.outputs["quantification_root"] = result.output_root

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
        scenes = list_scenes(path)
        return scenes or [None]


def _normalize_channel_map(
    channel_map: Iterable[BatchChannelConfig | dict] | None,
) -> list[BatchChannelConfig]:
    """Normalize channel mapping payloads into config objects.

    Parameters
    ----------
    channel_map : iterable of BatchChannelConfig or dict or None
        Channel mapping definitions from the UI or JSON payload.

    Returns
    -------
    list of BatchChannelConfig
        Normalized channel mapping list.
    """
    if channel_map is None:
        return []
    normalized: list[BatchChannelConfig] = []
    for entry in channel_map:
        if isinstance(entry, BatchChannelConfig):
            name = entry.name.strip()
            index = entry.index
        elif isinstance(entry, dict):
            name = str(entry.get("name", "")).strip()
            index = int(entry.get("index", 0))
        else:
            continue
        if not name:
            name = f"Channel {index}"
        normalized.append(BatchChannelConfig(name=name, index=index))
    return normalized


def _resolve_channel_name(
    choice: str | int,
    channel_map: list[BatchChannelConfig],
) -> str:
    """Resolve a user-friendly channel name from a choice.

    Parameters
    ----------
    choice : str or int
        Channel selection (name or index).
    channel_map : list of BatchChannelConfig
        Channel mapping list for name lookup.

    Returns
    -------
    str
        Channel name for use in output labels.
    """
    if isinstance(choice, int):
        return str(choice)
    text = str(choice).strip()
    if text.isdigit():
        return text
    for channel in channel_map:
        if channel.name == text:
            return channel.name
    return text


def _resolve_output_dir(
    output_root: Path,
    path: Path,
    scene_id: str | None,
    overwrite: bool,
) -> Path | None:
    """Resolve (and optionally create) the output directory for a run.

    Parameters
    ----------
    output_root : Path
        Root output folder.
    path : Path
        Input file path.
    scene_id : str or None
        Optional scene identifier.
    overwrite : bool
        Whether to overwrite existing folders.

    Returns
    -------
    Path or None
        Output directory path, or None when skipped.
    """
    base_name = basename_for_path(path)
    output_dir = output_root / base_name
    if scene_id:
        output_dir = output_dir / safe_scene_dir(scene_id)
    if output_dir.exists() and not overwrite:
        return None
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _build_viewer_for_quantification(
    path: Path,
    scene_id: str | None,
    channel_map: list[BatchChannelConfig],
    labels_data: dict[str, np.ndarray],
    labels_meta: dict[str, dict],
) -> BatchViewer:
    """Build a minimal viewer shim for quantification exports.

    Parameters
    ----------
    path : Path
        Input file path.
    scene_id : str or None
        Optional scene identifier.
    channel_map : list of BatchChannelConfig
        Channel mapping definitions used to load images.
    labels_data : dict of str to numpy.ndarray
        Generated label masks keyed by label name.
    labels_meta : dict of str to dict
        Metadata associated with each labels layer.

    Returns
    -------
    BatchViewer
        Viewer shim with Image/Labels layers.
    """
    layers: list[object] = []
    for channel in channel_map:
        image, metadata = load_channel_data(path, channel.index, scene_id)
        if image is None:
            continue
        layers.append(Image(image, channel.name, metadata))
    for name, data in labels_data.items():
        metadata = labels_meta.get(name, {})
        layers.append(Labels(data, name, metadata))
    return BatchViewer(layers)


def _apply_quantification_viewer(
    features: Iterable[object],
    quantification_tab: object | None,
    viewer: BatchViewer,
) -> None:
    """Attach a batch viewer to quantification handlers.

    Parameters
    ----------
    features : iterable of object
        Feature UI contexts (from QuantificationTab).
    quantification_tab : object or None
        Quantification tab instance (optional).
    viewer : BatchViewer
        Viewer shim with layers to expose to feature handlers.
    """
    if quantification_tab is not None:
        setattr(quantification_tab, "_viewer", viewer)
    for context in features:
        handler = getattr(context, "feature_handler", None)
        if handler is None:
            continue
        tab = getattr(handler, "_tab", None)
        if tab is not None:
            setattr(tab, "_viewer", viewer)
