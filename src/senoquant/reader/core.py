"""Core BioIO reader implementation for SenoQuant."""

from __future__ import annotations

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

    return bioio.BioImage(path)


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


def _iter_channel_layers(
    image,
    *,
    base_name: str,
    scene_id: str,
    scene_idx: int,
    total_scenes: int,
    path: str,
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

    Returns
    -------
    list of tuple
        Napari layer tuples for each channel.
    """
    dims = getattr(image, "dims", None)
    t_size = getattr(dims, "T", 1) if dims is not None else 1
    c_size = getattr(dims, "C", 1) if dims is not None else 1
    z_size = getattr(dims, "Z", 1) if dims is not None else 1

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
        kwargs = {"T": t_index}
        if z_size == 1:
            kwargs["Z"] = 0
        data = image.get_image_data(order, **kwargs)
        channel_iter = range(c_size)
    else:
        order = "ZYX" if z_size > 1 else "YX"
        kwargs = {"T": t_index, "C": 0}
        if z_size == 1 and order == "YX":
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
            "metadata": {
                "bioio_metadata": image.metadata,
                "scene_info": scene_meta,
                "path": path,
                "channel_index": channel_index,
                "physical_pixel_sizes": physical_sizes,
            },
        }
        layers.append((layer_data, meta, "image"))

    return layers
