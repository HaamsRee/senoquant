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
        napari layer tuples of the form ``(data, metadata, layer_type)``.

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
    try:
        layers: list[tuple] = []
        colormap_cycle = _colormap_cycle()
        # Try to get channel colors from OME metadata
        channel_colors = _get_channel_colors_from_ome(image)
        # If all channel colors are the same (e.g., all white), fall back to cycle
        if channel_colors and _all_channels_same_color(channel_colors):
            channel_colors = None
        scenes = list(getattr(image, "scenes", []) or [])
        selected_scene_indices = _select_scene_indices(path, scenes)
        if not selected_scene_indices:
            return layers

        for scene_idx in selected_scene_indices:
            scene_id = scenes[scene_idx]
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
                    channel_colors=channel_colors,
                )
            )

        return layers
    finally:
        if hasattr(image, "close"):
            try:
                image.close()
            except Exception:
                pass


def _select_scene_indices(path: str, scenes: list[str]) -> list[int]:
    """Return scene indices selected by the user for loading."""
    if not scenes:
        return []
    if len(scenes) == 1:
        return [0]

    selected = _prompt_scene_selection(path, scenes)
    if selected is None:
        return []
    return selected


def _prompt_scene_selection(path: str, scenes: list[str]) -> list[int] | None:
    """Show a scene-selection dialog and return selected indices.

    Returns
    -------
    list[int] or None
        Selected scene indices. Returns ``None`` when the dialog is cancelled.
        If Qt is not available, all scenes are selected.
    """
    try:
        from qtpy.QtCore import Qt
        from qtpy.QtWidgets import (
            QApplication,
            QDialog,
            QDialogButtonBox,
            QHBoxLayout,
            QLabel,
            QListWidget,
            QListWidgetItem,
            QMessageBox,
            QPushButton,
            QVBoxLayout,
        )
    except Exception:
        return list(range(len(scenes)))

    app = QApplication.instance()
    if app is None:
        return list(range(len(scenes)))

    dialog = QDialog(_napari_dialog_parent(app))
    dialog.setWindowTitle("Select scenes to load")
    dialog.setMinimumWidth(520)
    _apply_napari_dialog_theme(dialog, app)

    layout = QVBoxLayout(dialog)
    layout.addWidget(QLabel(f"File: {Path(path).name}"))
    layout.addWidget(QLabel(f"Select scenes to load ({len(scenes)} total):"))

    scene_list = QListWidget(dialog)
    for index, scene_id in enumerate(scenes):
        scene_name = str(scene_id).strip() or f"Scene {index}"
        item = QListWidgetItem(f"{index}: {scene_name}")
        item.setData(Qt.UserRole, index)
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked)
        scene_list.addItem(item)
    scene_list.setMinimumHeight(300)
    layout.addWidget(scene_list)

    controls = QHBoxLayout()
    select_all_button = QPushButton("Select all")
    clear_all_button = QPushButton("Clear all")
    controls.addWidget(select_all_button)
    controls.addWidget(clear_all_button)
    controls.addStretch(1)
    layout.addLayout(controls)

    select_all_button.clicked.connect(
        lambda: _set_scene_checks(scene_list, Qt.Checked)
    )
    clear_all_button.clicked.connect(lambda: _set_scene_checks(scene_list, Qt.Unchecked))

    buttons = QDialogButtonBox(
        QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=dialog
    )
    layout.addWidget(buttons)

    def _accept_if_valid() -> None:
        checked = _checked_scene_indices(scene_list)
        if checked:
            dialog.accept()
            return
        QMessageBox.warning(
            dialog,
            "No scenes selected",
            "Select at least one scene to load.",
        )

    buttons.accepted.connect(_accept_if_valid)
    buttons.rejected.connect(dialog.reject)

    if dialog.exec() != QDialog.Accepted:
        return None
    return _checked_scene_indices(scene_list)


def _napari_dialog_parent(app):
    """Return a good parent window for napari-linked dialogs."""
    try:
        import napari

        viewer = napari.current_viewer()
    except Exception:
        viewer = None
    if viewer is not None:
        window = getattr(viewer, "window", None)
        qt_window = getattr(window, "_qt_window", None)
        if qt_window is not None:
            return qt_window
    return app.activeWindow()


def _apply_napari_dialog_theme(dialog, app) -> None:
    """Apply napari/app stylesheet so popup theming is consistent."""
    stylesheet = ""
    try:
        import napari

        viewer = napari.current_viewer()
        theme_id = getattr(viewer, "theme", None) if viewer is not None else None
        if theme_id:
            try:
                from napari.qt import get_stylesheet

                stylesheet = str(get_stylesheet(theme_id) or "")
            except Exception:
                stylesheet = ""
    except Exception:
        stylesheet = ""

    if not stylesheet:
        try:
            stylesheet = str(app.styleSheet() or "")
        except Exception:
            stylesheet = ""
    if not stylesheet:
        try:
            parent = dialog.parentWidget()
            stylesheet = str(parent.styleSheet() if parent is not None else "")
        except Exception:
            stylesheet = ""

    if stylesheet:
        dialog.setStyleSheet(stylesheet)


def _set_scene_checks(scene_list, state) -> None:
    """Set check state for all scene list items."""
    for row in range(scene_list.count()):
        item = scene_list.item(row)
        if item is not None:
            item.setCheckState(state)


def _checked_scene_indices(scene_list) -> list[int]:
    """Return checked scene indices from a QListWidget."""
    from qtpy.QtCore import Qt

    selected: list[int] = []
    for row in range(scene_list.count()):
        item = scene_list.item(row)
        if item is None:
            continue
        if item.checkState() == Qt.Checked:
            selected.append(int(item.data(Qt.UserRole)))
    return selected


def _open_bioimage(path: str):
    """Open a BioImage using bioio with bioformats reader.

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

    try:
        import bioio_bioformats

        # Use dask_tiles=True to enable tile-based reading for large images.
        # This avoids the 2GB limit in BioFormats.
        return bioio.BioImage(
            path,
            reader=bioio_bioformats.Reader,
            dask_tiles=True,
        )
    except ImportError:
        # Fallback to auto-detection if bioio-bioformats is not available
        return bioio.BioImage(path)


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
        "green",
        "red",
        "yellow",
    ]
    return itertools.cycle(names)


def _all_channels_same_color(channel_colors: list[dict | None]) -> bool:
    """Check if all non-None channel colors are the same based on RGB values.

    Parameters
    ----------
    channel_colors : list of dict or None
        List of colormap dictionaries from OME metadata.

    Returns
    -------
    bool
        True if all channels have the same RGB color.
    """
    # Filter out None values
    valid_colors = [c for c in channel_colors if c is not None]
    if not valid_colors:
        return False

    # Extract RGB values from the 'colors' array (second color is the channel color)
    rgb_values = []
    for c in valid_colors:
        colors = c.get("colors", [])
        if len(colors) >= 2:
            # Get the second color (the channel color, not black)
            color = colors[1]
            rgb_values.append((color[0], color[1], color[2]))

    # Check if all RGB values are the same
    return len(set(rgb_values)) == 1


def _get_channel_colors_from_ome(image) -> list[dict | None]:
    """Extract channel colors from OME metadata.

    Parameters
    ----------
    image : bioio.BioImage
        BioIO image with the current scene selected.

    Returns
    -------
    list of dict or None
        List of colormap dictionaries for each channel, or None if not available.
        Each dict has 'colors', 'name', and 'interpolation' keys for napari.
    """
    try:
        ome = image.ome_metadata
    except Exception:
        return []

    if not hasattr(ome, "images") or not ome.images:
        return []

    # Get the first image's pixels channels
    img = ome.images[0]
    if not hasattr(img, "pixels") or not hasattr(img.pixels, "channels"):
        return []

    channels = img.pixels.channels
    if not channels:
        return []

    channel_colors = []
    for i, ch in enumerate(channels):
        try:
            color = getattr(ch, "color", None)
            if color is None:
                channel_colors.append(None)
                continue

            # Get RGB values from OME Color object
            rgb_tuple = color.as_rgb_tuple()
            # Convert to 0-1 range for napari
            r, g, b = (x / 255.0 for x in rgb_tuple)

            # Get the original color name (could be a string or tuple)
            original = getattr(color, "_original", None)
            if isinstance(original, str):
                color_name = original
            elif isinstance(original, tuple):
                # It's an RGBA tuple, use the string representation
                color_name = str(color)
            else:
                color_name = str(color)

            # Create a colormap from black to the channel color
            # This allows the channel to be visible regardless of its base color
            colors = [[0.0, 0.0, 0.0, 1.0], [r, g, b, 1.0]]

            channel_colors.append(
                {
                    "colors": colors,
                    "name": f"channel_{i}_{color_name}",
                    "interpolation": "linear",
                }
            )
        except Exception:
            channel_colors.append(None)

    return channel_colors


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
    channel_colors: list[dict | None] | None = None,
) -> list[tuple]:
    """Split BioIO data into single-channel (Z)YX napari layers.

    Uses dask-based delayed reading to handle large images that would
    otherwise exceed the 2GB memory limit in BioFormats.

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
    channel_colors : list of dict or None, optional
        List of colormap dictionaries from OME metadata for each channel.

    Returns
    -------
    list of tuple
        napari layer tuples for each channel.
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

    # Use dask-based delayed reading to handle large images
    # This avoids the 2GB limit in BioFormats by not loading all data at once
    if c_size > 1:
        order = "CZYX" if z_size > 1 else "CYX"
        kwargs = {}
        if "T" in axes_present and "T" not in order:
            kwargs["T"] = t_index
        if "Z" in axes_present and "Z" not in order:
            kwargs["Z"] = 0
        # Use get_image_dask_data for lazy loading instead of get_image_data
        data = _get_dask_data(image, order, **kwargs)
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
        # Use get_image_dask_data for lazy loading instead of get_image_data
        data = _get_dask_data(image, order, **kwargs)
        channel_iter = [0]

    for channel_index in channel_iter:
        # For dask arrays, we keep them as-is (lazy) - napari can handle them
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
        # Use OME channel color if available, otherwise fall back to cycle
        if channel_colors and channel_index < len(channel_colors):
            ome_color = channel_colors[channel_index]
            if ome_color is not None:
                meta["colormap"] = ome_color
            elif colormap_cycle is not None:
                meta["colormap"] = next(colormap_cycle)
        elif colormap_cycle is not None:
            meta["colormap"] = next(colormap_cycle)
        layers.append((layer_data, meta, "image"))

    return layers


def _get_dask_data(image, order: str, **kwargs):
    """Get image data using dask for lazy loading, then compute to numpy.

    With dask_tiles=True enabled in the BioImage, the dask array is already
    chunked into tiles that avoid the 2GB BioFormats limit. We simply
    compute the result to a numpy array for napari compatibility.

    Parameters
    ----------
    image : bioio.BioImage
        BioIO image with the current scene selected.
    order : str
        Dimension order (e.g., "CZYX", "CYX", "ZYX", "YX").
    **kwargs
        Additional dimension indices to select specific planes.

    Returns
    -------
    numpy array
        Computed numpy array of the image data.
    """
    try:
        # Get dask data (already chunked by dask_tiles=True)
        dask_data = image.get_image_dask_data(order, **kwargs)
        # Compute to numpy array for napari compatibility
        return dask_data.compute()
    except Exception as e:
        # Fall back to regular loading if dask fails
        try:
            return image.get_image_data(order, **kwargs)
        except Exception:
            raise RuntimeError(
                f"Failed to load image data. Error: {e}"
            ) from e
