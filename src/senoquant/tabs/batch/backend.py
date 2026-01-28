"""Backend logic for batch processing workflows."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import numpy as np

from senoquant.tabs.quantification.backend import QuantificationBackend
from senoquant.tabs.segmentation.backend import SegmentationBackend
from senoquant.tabs.spots.backend import SpotsBackend

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
    spot_label_name,
    write_array,
)


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


class BatchBackend:
    """Backend for batch segmentation and spot detection workflows."""

    def __init__(
        self,
        segmentation_backend: SegmentationBackend | None = None,
        spots_backend: SpotsBackend | None = None,
    ) -> None:
        self._segmentation_backend = segmentation_backend or SegmentationBackend()
        self._spots_backend = spots_backend or SpotsBackend()

    def run_job(self, job: BatchJobConfig) -> BatchSummary:
        """Run a batch job using a BatchJobConfig."""
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
        quantification_features: Iterable[object] | None = None,
        quantification_format: str = "xlsx",
        quantification_tab: object | None = None,
        extensions: Iterable[str] | None = None,
        include_subfolders: bool = False,
        output_format: str = "tif",
        overwrite: bool = False,
        process_all_scenes: bool = False,
    ) -> BatchSummary:
        """Run batch processing on a folder of images."""
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

        for path in files:
            scenes = self._iter_scenes(path, process_all_scenes)
            for scene_id in scenes:
                item_result = BatchItemResult(path=path, scene_id=scene_id)
                try:
                    output_dir = _resolve_output_dir(
                        output_root, path, scene_id, overwrite
                    )
                    if output_dir is None:
                        skipped += 1
                        results.append(item_result)
                        continue

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
                            out_path = write_array(
                                output_dir,
                                "nuclear_labels",
                                masks,
                                output_format,
                            )
                            labels_data["nuclear_labels"] = masks
                            labels_meta["nuclear_labels"] = metadata
                            item_result.outputs["nuclear_labels"] = out_path

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
                            out_path = write_array(
                                output_dir,
                                "cyto_labels",
                                masks,
                                output_format,
                            )
                            labels_data["cyto_labels"] = masks
                            labels_meta["cyto_labels"] = cyto_meta
                            item_result.outputs["cyto_labels"] = out_path

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
                            label_name = spot_label_name(
                                channel_choice, normalized_channels
                            )
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


def _resolve_output_dir(
    output_root: Path,
    path: Path,
    scene_id: str | None,
    overwrite: bool,
) -> Path | None:
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
    if quantification_tab is not None:
        setattr(quantification_tab, "_viewer", viewer)
    for context in features:
        handler = getattr(context, "feature_handler", None)
        if handler is None:
            continue
        tab = getattr(handler, "_tab", None)
        if tab is not None:
            setattr(tab, "_viewer", viewer)
