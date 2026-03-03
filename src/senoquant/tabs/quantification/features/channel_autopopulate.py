"""Shared helpers for channel auto-population in quantification dialogs."""

from __future__ import annotations

from typing import Any


def _layer_metadata(layer: object) -> dict[str, Any]:
    metadata = getattr(layer, "metadata", None)
    if isinstance(metadata, dict):
        return metadata
    return {}


def _to_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        return None
    if isinstance(value, str):
        text = value.strip()
        if text.lstrip("+-").isdigit():
            try:
                return int(text)
            except Exception:
                return None
    return None


def channel_label_from_layer(layer: object) -> str:
    """Return a display name for an image layer channel.

    Uses reader-provided ``channel_names`` + ``channel_index`` metadata when
    available, then falls back to the layer name.
    """
    metadata = _layer_metadata(layer)
    channel_names = metadata.get("channel_names")
    channel_index = _to_int(metadata.get("channel_index"))
    if isinstance(channel_names, (list, tuple)) and channel_index is not None:
        if 0 <= channel_index < len(channel_names):
            candidate = str(channel_names[channel_index]).strip()
            if candidate:
                return candidate

    layer_name = str(getattr(layer, "name", "")).strip()
    if layer_name:
        return layer_name
    return "Channel"


def unique_channel_label(base_name: str, used_names: set[str]) -> str:
    """Return a unique channel label based on ``base_name``."""
    base = base_name.strip() or "Channel"
    if base not in used_names:
        return base
    index = 2
    while True:
        candidate = f"{base} {index}"
        if candidate not in used_names:
            return candidate
        index += 1


def layer_identity(layer: object) -> tuple[str | None, int | None, int | None]:
    """Return ``(path, scene_index, channel_index)`` identity tuple."""
    metadata = _layer_metadata(layer)
    path_raw = metadata.get("path")
    path = str(path_raw).strip() if path_raw is not None else ""
    path_value = path or None

    scene_info = metadata.get("scene_info")
    scene_index = None
    if isinstance(scene_info, dict):
        scene_index = _to_int(scene_info.get("scene_index"))

    channel_index = _to_int(metadata.get("channel_index"))
    return (path_value, scene_index, channel_index)


def same_layer_identity(
    left: tuple[str | None, int | None, int | None],
    right: tuple[str | None, int | None, int | None],
) -> bool:
    """Return True when two ``layer_identity`` tuples represent one channel."""
    left_path, left_scene, left_channel = left
    right_path, right_scene, right_channel = right

    if left_channel is None or right_channel is None:
        return False
    if left_channel != right_channel:
        return False

    if left_path and right_path and left_path != right_path:
        return False
    if left_scene is not None and right_scene is not None and left_scene != right_scene:
        return False

    same_path = bool(left_path and right_path and left_path == right_path)
    same_scene = (
        left_scene is not None
        and right_scene is not None
        and left_scene == right_scene
    )
    return same_path or same_scene

