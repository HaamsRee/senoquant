"""Core BioIO reader implementation for SenoQuant."""

from __future__ import annotations

import itertools
from pathlib import Path
from typing import Callable, Iterable

try:
    from bioio_base.exceptions import UnsupportedFileFormatError
except Exception:  # pragma: no cover - optional dependency
    UnsupportedFileFormatError = Exception


def get_reader(path: str | list[str]) -> Callable | None:
    """Return a reader callable for the given path.

    Parameters
    ----------
    path : str or list of str
        Path(s) selected in the napari reader dialog.

    Returns
    -------
    callable or None
        Reader callable that returns napari layer data, or ``None`` if the
        path is not supported.

    Notes
    -----
    This uses ``bioio.BioImage.determine_plugin`` to ensure the file can be
    handled by BioIO. If the file is unsupported or BioIO is unavailable,
    ``None`` is returned so napari can try other readers.
    """
    if isinstance(path, (list, tuple)):
        if not path:
            return None
        path = path[0]
    if not isinstance(path, str) or not path:
        return None
    if not Path(path).is_file():
        return None
    try:
        import bioio
    except ImportError:
        return None
    if not hasattr(bioio.BioImage, "determine_plugin"):
        return None
    try:
        plugin = bioio.BioImage.determine_plugin(path)
    except (
        AttributeError,
        ImportError,
        ValueError,
        RuntimeError,
        FileNotFoundError,
        OSError,
        UnsupportedFileFormatError,
        Exception,
    ):
        return None
    if plugin is None:
        return None
    return _read_senoquant


def _read_senoquant(path: str) -> Iterable[tuple]:
    """Read image data using BioIO and return napari layer tuples.

    Parameters
    ----------
    path : str
        File path to read.

    Returns
    -------
    iterable of tuple
        Napari layer tuples of the form ``(data, metadata, layer_type)``.

    Notes
    -----
    When multiple scenes are present, each scene becomes a separate layer
    with metadata describing the scene index and name.
    """
    try:
        from bioio import BioImage
    except Exception as exc:  # pragma: no cover - dependency dependent
        raise ImportError(
            "BioIO is required for the SenoQuant reader."
        ) from exc

    base_name = Path(path).name
    image = _open_bioimage(path)
    layers: list[tuple] = []
    colormap_cycle = _colormap_cycle()
    scenes = image.scenes

    for scene_idx, scene_id in enumerate(scenes):
        image.set_scene(scene_id)
        layers.extend(
            _iter_channel_layers(
                image,
                base_name=base_name,
                scene_id=scene_id,
                scene_idx=scene_idx,
                total_scenes=len(scenes),
                path=path,
                colormap_cycle=colormap_cycle,
            )
        )

    return layers


def _open_bioimage(path: str):
    """Open a BioImage using bioio.

    Parameters
    ----------
    path : str
        File path to read.

    Returns
    -------
    bioio.BioImage
        BioIO image instance for the requested file.
    """
    import bioio

    plugin = None
    try:
        plugin = bioio.BioImage.determine_plugin(path)
    except Exception:
        plugin = None

    if _should_force_tifffile(plugin, path):
        image = _try_bioimage_readers(
            bioio,
            path,
            reader_names=("bioio_tifffile", "bioio_ome_tiff"),
        )
        if image is not None:
            return image

    return bioio.BioImage(path)


def _should_force_tifffile(plugin, path: str) -> bool:
    """Return True when tiff_glob should be bypassed for single-file TIFFs."""
    if "*" in path or "?" in path:
        return False
    if not path.lower().endswith((".tif", ".tiff")):
        return False
    names = set()
    if isinstance(plugin, str):
        names.add(plugin)
    else:
        for attr in ("name", "value", "__name__", "__module__"):
            value = getattr(plugin, attr, None)
            if value:
                names.add(str(value))
        entrypoint = getattr(plugin, "entrypoint", None)
        if entrypoint is not None:
            for attr in ("name", "value", "__name__", "__module__"):
                value = getattr(entrypoint, attr, None)
                if value:
                    names.add(str(value))
    return any("tiff_glob" in name or "tiff-glob" in name for name in names)


def _try_bioimage_readers(bioio, path: str, reader_names: tuple[str, ...]):
    """Try opening a BioImage with explicit reader plugins."""
    import importlib

    for reader_name in reader_names:
        module = None
        try:
            module = importlib.import_module(reader_name)
        except Exception:
            module = None
        if module is not None:
            reader_cls = getattr(module, "Reader", None)
            if reader_cls is not None:
                try:
                    return bioio.BioImage(path, reader=reader_cls)
                except Exception:
                    continue
    return None


def _colormap_cycle() -> Iterable[str]:
    """Return an iterator cycling through approved colormap names.

    Returns
    -------
    iterable of str
        Cycle of colormap names to assign to reader layers.
    """
    names = [
        "blue",
        "bop blue",
        "bop orange",
        "bop purple",
        "cyan",
        # "fire",
        # "gist_earth",
        # "gray",
        # "gray_r",
        "green",
        # "HiLo",
        # "hsv",
        # "I Blue",
        # "I Bordeaux",
        # "I Forest",
        # "I Orange",
        # "I Purple",
        # "ice",
        # "inferno",
        # "magenta",
        # "magma",
        # "nan",
        # "PiYG",
        # "plasma",
        "red",
        # "turbo",
        # "twilight",
        # "twilight_shifted",
        # "viridis",
        "yellow",
    ]
    return itertools.cycle(names)


def _physical_pixel_sizes(image) -> dict[str, float | None]:
    """Return physical pixel sizes (um) for the active scene."""
    try:
        sizes = image.physical_pixel_sizes
    except Exception:
        return {"Z": None, "Y": None, "X": None}
    return {
        "Z": sizes.Z,
        "Y": sizes.Y,
        "X": sizes.X,
    }


def _axes_present(image) -> set[str]:
    """Return the set of axis labels present in the BioIO image."""
    dims = getattr(image, "dims", None)
    if dims is None:
        return set()
    if isinstance(dims, str):
        return set(dims)
    order = getattr(dims, "order", None)
    if isinstance(order, str):
        return set(order)
    axes = getattr(dims, "axes", None)
    if not axes:
        return set()
    result: set[str] = set()
    for axis in axes:
        if isinstance(axis, str):
            result.add(axis)
            continue
        name = (
            getattr(axis, "name", None)
            or getattr(axis, "value", None)
            or getattr(axis, "axis", None)
        )
        if name:
            result.add(str(name))
    return result


def _iter_channel_layers(
    image,
    *,
    base_name: str,
    scene_id: str,
    scene_idx: int,
    total_scenes: int,
    path: str,
    colormap_cycle: Iterable[str] | None = None,
) -> list[tuple]:
    """Split BioIO data into single-channel (Z)YX napari layers.

    Parameters
    ----------
    image : bioio.BioImage
        BioIO image with the current scene selected.
    base_name : str
        Base filename for layer naming.
    scene_id : str
        Scene identifier string.
    scene_idx : int
        Scene index within the file.
    total_scenes : int
        Total number of scenes in the file.
    path : str
        Original image path to store in the metadata.
    colormap_cycle : iterable of str or None, optional
        Iterator that provides colormap names to assign to each layer.

    Returns
    -------
    list of tuple
        Napari layer tuples for each channel.
    """
    dims = getattr(image, "dims", None)
    axes_present = _axes_present(image)
    t_size = getattr(dims, "T", 1) if "T" in axes_present else 1
    c_size = getattr(dims, "C", 1) if "C" in axes_present else 1
    z_size = getattr(dims, "Z", 1) if "Z" in axes_present else 1

    scene_name = scene_id or f"Scene {scene_idx}"
    scene_meta = {
        "scene_id": scene_id,
        "scene_index": scene_idx,
        "scene_name": scene_name,
        "total_scenes": total_scenes,
    }
    layers: list[tuple] = []
    t_index = 0

    if c_size > 1:
        order = "CZYX" if z_size > 1 else "CYX"
        kwargs = {}
        if "T" in axes_present and "T" not in order:
            kwargs["T"] = t_index
        if "Z" in axes_present and "Z" not in order:
            kwargs["Z"] = 0
        data = image.get_image_data(order, **kwargs)
        channel_iter = range(c_size)
    else:
        order = "ZYX" if z_size > 1 else "YX"
        kwargs = {}
        if "T" in axes_present and "T" not in order:
            kwargs["T"] = t_index
        if "C" in axes_present and "C" not in order:
            kwargs["C"] = 0
        if "Z" in axes_present and "Z" not in order:
            kwargs["Z"] = 0
        data = image.get_image_data(order, **kwargs)
        channel_iter = [0]

    for channel_index in channel_iter:
        layer_data = data[channel_index] if c_size > 1 else data

        layer_name = f"{base_name} - {scene_name}" if total_scenes > 1 else base_name
        if c_size > 1:
            layer_name = f"{layer_name} - Channel {channel_index}"

        physical_sizes = _physical_pixel_sizes(image)
        meta = {
            "name": layer_name,
            "blending": "additive",
            "metadata": {
                "bioio_metadata": image.metadata,
                "scene_info": scene_meta,
                "path": path,
                "channel_index": channel_index,
                "physical_pixel_sizes": physical_sizes,
            },
        }
        if colormap_cycle is not None:
            meta["colormap"] = next(colormap_cycle)
        layers.append((layer_data, meta, "image"))

    return layers
