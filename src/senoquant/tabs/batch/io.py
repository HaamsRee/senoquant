"""I/O helpers for batch processing.

This module provides filesystem and image-loading utilities used by the
batch backend. Functions are intentionally stateless and easy to mock in
tests.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import numpy as np

from senoquant.reader import core as reader_core
from .config import BatchChannelConfig


def normalize_extensions(extensions: Iterable[str] | None) -> set[str] | None:
    """Normalize extension list to lowercase with leading dots.

    Parameters
    ----------
    extensions : iterable of str or None
        Raw extension strings (with or without dots).

    Returns
    -------
    set of str or None
        Normalized extensions or None when no filtering is requested.
    """
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


def iter_input_files(
    root: Path, extensions: set[str] | None, include_subfolders: bool
) -> Iterable[Path]:
    """Yield input files from a root folder.

    Parameters
    ----------
    root : Path
        Directory to scan.
    extensions : set of str or None
        Allowed file extensions. None disables filtering.
    include_subfolders : bool
        Whether to scan subfolders recursively.

    Yields
    ------
    Path
        File paths that match the extension criteria.
    """
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


def basename_for_path(path: Path) -> str:
    """Return a filesystem-friendly base name for a file path.

    Parameters
    ----------
    path : Path
        Input file path.

    Returns
    -------
    str
        Base name with common microscopy extensions removed.
    """
    name = path.name
    lowered = name.lower()
    for ext in (".ome.tiff", ".ome.tif", ".tiff", ".tif"):
        if lowered.endswith(ext):
            return name[: -len(ext)]
    if "." in name:
        return name.rsplit(".", 1)[0]
    return name


def safe_scene_dir(scene_id: str) -> str:
    """Return a sanitized scene identifier for folder naming.

    Parameters
    ----------
    scene_id : str
        Scene identifier from BioIO.

    Returns
    -------
    str
        Filesystem-safe scene folder name.
    """
    safe = scene_id.strip().replace("/", "_").replace("\\", "_")
    return safe or "scene"


def write_array(
    output_dir: Path, name: str, data: np.ndarray, output_format: str
) -> Path:
    """Write an array to disk in the requested format.

    Parameters
    ----------
    output_dir : Path
        Destination folder.
    name : str
        Base name for the output file.
    data : numpy.ndarray
        Array data to serialize.
    output_format : str
        Output format (``"tif"`` or ``"npy"``).

    Returns
    -------
    Path
        Path to the written file.
    """
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


def resolve_channel_index(
    choice: str | int | None,
    channel_map: list[BatchChannelConfig],
) -> int:
    """Resolve a channel selection into a numeric index.

    Parameters
    ----------
    choice : str or int or None
        Channel selection from the UI (name or index).
    channel_map : list of BatchChannelConfig
        Mapping from names to indices.

    Returns
    -------
    int
        Resolved channel index.

    Raises
    ------
    ValueError
        If the selection is missing or unknown.
    """
    if isinstance(choice, int):
        return choice
    if choice is None:
        raise ValueError("Channel selection is required.")
    text = str(choice).strip()
    if not text:
        raise ValueError("Channel selection is required.")
    if text.isdigit():
        return int(text)
    for channel in channel_map:
        if channel.name == text:
            return channel.index
    raise ValueError(f"Unknown channel selection: {text}.")


def spot_label_name(
    choice: str | int,
    channel_map: list[BatchChannelConfig],
) -> str:
    """Build the output label name for a spot channel.

    Parameters
    ----------
    choice : str or int
        Channel selection.
    channel_map : list of BatchChannelConfig
        Channel mapping list for name lookup.

    Returns
    -------
    str
        Standardized spot label name.
    """
    if isinstance(choice, int):
        name = str(choice)
    else:
        name = str(choice).strip()
        if name.isdigit():
            return f"spot_labels_{name}"
        for channel in channel_map:
            if channel.name == name:
                name = channel.name
                break
    return f"spot_labels_{sanitize_label(name)}"


def sanitize_label(name: str) -> str:
    """Sanitize a label name for filesystem use."""
    safe = []
    for char in name.strip():
        if char.isalnum():
            safe.append(char)
        else:
            safe.append("_")
    result = "".join(safe).strip("_")
    return result or "spots"


def load_channel_data(
    path: Path,
    channel_index: int,
    scene_id: str | None,
) -> tuple[np.ndarray | None, dict]:
    """Load a single-channel image array for the given path.

    Parameters
    ----------
    path : Path
        Input file path.
    channel_index : int
        Channel index to extract.
    scene_id : str or None
        Optional scene identifier.

    Returns
    -------
    tuple of (numpy.ndarray or None, dict)
        The extracted image data and metadata.
    """
    image = reader_core._open_bioimage(str(path))
    try:
        if scene_id:
            image.set_scene(scene_id)
        metadata = {"physical_pixel_sizes": reader_core._physical_pixel_sizes(image)}
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
        return np.asarray(data), metadata
    finally:
        if hasattr(image, "close"):
            try:
                image.close()
            except Exception:
                pass



def list_scenes(path: Path) -> list[str]:
    """Return scene identifiers for a BioIO image path.

    Parameters
    ----------
    path : Path
        Input file path.

    Returns
    -------
    list of str
        Scene identifiers, or an empty list if unavailable.
    """
    try:
        image = reader_core._open_bioimage(str(path))
    except Exception:
        return []
    try:
        scenes = list(getattr(image, "scenes", []) or [])
    finally:
        if hasattr(image, "close"):
            try:
                image.close()
            except Exception:
                pass
    return scenes
