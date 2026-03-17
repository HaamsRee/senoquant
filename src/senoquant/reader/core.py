"""Core BioIO reader implementation for SenoQuant."""

from __future__ import annotations

import atexit
import hashlib
import importlib
import itertools
import logging
import os
import platform
import re
from pathlib import Path
import shutil
import tempfile
from typing import Callable, Iterable
from urllib.parse import unquote, urlparse

try:
    from bioio_base.exceptions import UnsupportedFileFormatError
except Exception:  # pragma: no cover - optional dependency
    UnsupportedFileFormatError = Exception


_LOGGER = logging.getLogger(__name__)
_NETWORK_STAGE_ROOT = Path(tempfile.mkdtemp(prefix="senoquant-reader-"))
_STAGED_NETWORK_PATHS: dict[str, str] = {}
_WINDOWS_TRUSTSTORE_TYPE_FLAG = "-Djavax.net.ssl.trustStoreType=Windows-ROOT"
_WINDOWS_TRUSTSTORE_PROVIDER_FLAG = "-Djavax.net.ssl.trustStoreProvider=SunMSCAPI"
_MACOS_TRUSTSTORE_TYPE_FLAG = "-Djavax.net.ssl.trustStoreType=KeychainStore"
_LINUX_JAVA_CACERTS_PATHS = (
    "/etc/ssl/certs/java/cacerts",
    "/etc/pki/java/cacerts",
)
_DISALLOWED_DATA_READER_MODULES: frozenset[str] = frozenset(
    {
        "bioio_tiff_glob",
    }
)
_GENERIC_CHANNEL_COLON_PATTERN = re.compile(
    r"^Channel:\d+:\d+(?::\d+)*$",
    flags=re.IGNORECASE,
)
_GENERIC_CHANNEL_INDEX_PATTERN = re.compile(
    r"^Channel\s+\d+$",
    flags=re.IGNORECASE,
)


def _cleanup_network_staging() -> None:
    """Remove staged network files created during this process."""
    shutil.rmtree(_NETWORK_STAGE_ROOT, ignore_errors=True)


atexit.register(_cleanup_network_staging)


def _is_windows_drive_path(path: str) -> bool:
    """Return True when the path looks like a Windows drive path."""
    return len(path) >= 2 and path[1] == ":" and path[0].isalpha()


def _is_network_path(path: str) -> bool:
    """Return True for UNC paths and URI-based network paths."""
    if path.startswith("\\\\"):
        return True
    if _is_windows_drive_path(path):
        return False
    if "://" not in path:
        return False
    scheme = urlparse(path).scheme.lower()
    return scheme not in {"", "file"}


def _path_display_name(path: str) -> str:
    """Return a filename-like display name for local and network paths."""
    if path.startswith("\\\\"):
        parts = [part for part in path.strip("\\").split("\\") if part]
        return parts[-1] if parts else path
    if "://" in path and not _is_windows_drive_path(path):
        parsed = urlparse(path)
        name = Path(unquote(parsed.path)).name
        return name or path
    return Path(path).name


def _network_download_source(path: str) -> str:
    """Normalize network paths for fsspec download."""
    if path.startswith("\\\\"):
        parts = [part for part in path.strip("\\").split("\\") if part]
        if len(parts) < 2:
            raise ValueError(f"Unsupported UNC path format: {path}")
        server = parts[0]
        share_and_file = "/".join(parts[1:])
        # Keep spaces and other path characters unescaped: smbclient/fsspec
        # expects a normal SMB path string, not URL-encoded segments.
        return f"smb://{server}/{share_and_file}"
    return path


def _stage_network_path(path: str) -> str:
    """Download a network path to a local temp file for BioIO readers."""
    cached = _STAGED_NETWORK_PATHS.get(path)
    if cached is not None and Path(cached).is_file():
        return cached

    source = _network_download_source(path)
    digest = hashlib.sha256(path.encode("utf-8")).hexdigest()[:16]
    suffix = Path(_path_display_name(path)).suffix
    staged_path = _NETWORK_STAGE_ROOT / f"{digest}{suffix}"
    temp_path = staged_path.with_suffix(staged_path.suffix + ".part")
    _NETWORK_STAGE_ROOT.mkdir(parents=True, exist_ok=True)

    try:
        import fsspec
    except Exception as exc:  # pragma: no cover - optional dependency
        raise ImportError(
            "fsspec is required to stage network image paths."
        ) from exc

    try:
        with fsspec.open(source, "rb") as src, temp_path.open("wb") as dst:
            shutil.copyfileobj(src, dst, length=1024 * 1024)
        temp_path.replace(staged_path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise

    staged = str(staged_path)
    _STAGED_NETWORK_PATHS[path] = staged
    _LOGGER.info("Staged network image %s to %s", path, staged)
    return staged


def _resolve_reader_path(path: str) -> str:
    """Resolve input to a local path consumable by BioIO readers."""
    if _is_network_path(path):
        return _stage_network_path(path)
    if Path(path).is_file():
        return path
    raise FileNotFoundError(path)


def _linux_java_truststore_path() -> str | None:
    """Return the first available Linux Java truststore path."""
    for candidate in _LINUX_JAVA_CACERTS_PATHS:
        if Path(candidate).is_file():
            return candidate
    return None


def _java_truststore_flags_for_platform() -> list[tuple[str, str]]:
    """Return platform-specific JVM truststore flags (token, flag)."""
    system = platform.system()
    if system == "Windows":
        return [
            ("javax.net.ssl.trustStoreType", _WINDOWS_TRUSTSTORE_TYPE_FLAG),
            ("javax.net.ssl.trustStoreProvider", _WINDOWS_TRUSTSTORE_PROVIDER_FLAG),
        ]
    if system == "Darwin":
        return [
            ("javax.net.ssl.trustStoreType", _MACOS_TRUSTSTORE_TYPE_FLAG),
        ]
    if system == "Linux":
        truststore_path = _linux_java_truststore_path()
        if truststore_path is None:
            return []
        return [
            (
                "javax.net.ssl.trustStore",
                f"-Djavax.net.ssl.trustStore={truststore_path}",
            ),
            (
                "javax.net.ssl.trustStorePassword",
                "-Djavax.net.ssl.trustStorePassword=changeit",
            ),
        ]
    return []


def _ensure_java_truststore() -> None:
    """Configure Java/Maven truststore settings for current platform."""
    setup_mode = os.environ.get("SENOQUANT_JAVA_TRUSTSTORE_SETUP", "auto").strip().lower()
    if setup_mode in {"0", "false", "off", "no"}:
        return

    flags = _java_truststore_flags_for_platform()
    if not flags:
        return

    for env_name in ("JAVA_TOOL_OPTIONS", "MAVEN_OPTS"):
        current = os.environ.get(env_name, "").strip()
        additions: list[str] = []
        for token, flag in flags:
            if token not in current:
                additions.append(flag)
        if not additions:
            continue
        updated = f"{current} {' '.join(additions)}".strip()
        os.environ[env_name] = updated
        _LOGGER.info("Configured %s JVM truststore options for %s.", env_name, platform.system())


def _path_extension_candidates(path: str) -> tuple[str, ...]:
    """Return candidate extensions (longest to shortest) for a path."""
    name = _path_display_name(path).strip().lower()
    if "." not in name:
        return ()
    parts = [part for part in name.split(".") if part]
    if len(parts) <= 1:
        return ()
    candidates: list[str] = []
    for index in range(1, len(parts)):
        candidates.append(f".{'.'.join(parts[index:])}")
    return tuple(candidates)


def _reader_module_priority_for_path(path: str) -> tuple[str, ...]:
    """Return prioritized BioIO reader module names for a path."""
    ordered_modules: list[str] = []
    plugins_by_extension = _plugins_by_extension()
    for extension in _path_extension_candidates(path):
        plugin_entries = plugins_by_extension.get(extension, ())
        for plugin_entry in plugin_entries:
            module_name = _plugin_entry_module_name(plugin_entry)
            if module_name:
                if module_name in _DISALLOWED_DATA_READER_MODULES:
                    continue
                ordered_modules.append(module_name)
    deduped: list[str] = []
    seen: set[str] = set()
    for module_name in ordered_modules:
        if module_name in seen:
            continue
        seen.add(module_name)
        deduped.append(module_name)
    return tuple(deduped)


def _plugins_by_extension() -> dict[str, tuple[object, ...]]:
    """Return normalized BioIO plugin registry grouped by extension."""
    try:
        import bioio
    except Exception:
        return {}

    try:
        plugins = bioio.plugins.get_plugins(use_cache=True)
    except Exception:
        return {}

    if not hasattr(plugins, "items"):
        return {}

    normalized: dict[str, list[object]] = {}
    for extension_key, entries in plugins.items():
        extension = _normalize_extension(extension_key)
        if extension is None:
            continue
        if isinstance(entries, (list, tuple)):
            normalized.setdefault(extension, []).extend(entries)
            continue
        normalized.setdefault(extension, []).append(entries)
    return {key: tuple(value) for key, value in normalized.items()}


def _normalize_extension(value: object) -> str | None:
    """Normalize an extension-like value into lowercase ``.ext`` format."""
    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    if not text:
        return None
    if not text.startswith("."):
        text = f".{text.lstrip('.')}"
    return text


def _plugin_entry_module_name(plugin_entry: object) -> str | None:
    """Extract importable module name from a BioIO plugin entry."""
    entrypoint = getattr(plugin_entry, "entrypoint", None)
    value = getattr(entrypoint, "value", None)
    if not isinstance(value, str):
        return None
    module_name = value.strip().split(":", 1)[0].strip()
    if not module_name:
        return None
    return module_name


def _load_reader_class(module_name: str):
    """Load ``Reader`` class from a BioIO plugin module."""
    try:
        module = importlib.import_module(module_name)
    except Exception:
        return None
    reader_class = getattr(module, "Reader", None)
    if reader_class is None:
        return None
    return reader_class


def _reader_identifier(reader_obj: object | None) -> str | None:
    """Return ``module.Class`` style identifier for reader class/instance."""
    if reader_obj is None:
        return None
    reader_class = reader_obj if isinstance(reader_obj, type) else type(reader_obj)
    module_name = getattr(reader_class, "__module__", "")
    class_name = getattr(reader_class, "__name__", "")
    if not class_name:
        return None
    return f"{module_name}.{class_name}" if module_name else class_name


def _is_bioformats_reader(reader_obj: object | None) -> bool:
    """Return True when the reader appears to be BioFormats-based."""
    identifier = _reader_identifier(reader_obj)
    if not identifier:
        return False
    return "bioformats" in identifier.lower()


def _candidate_fast_reader_classes(path: str) -> tuple[object, ...]:
    """Return importable non-BioFormats reader classes for the given path."""
    candidates: list[object] = []
    for module_name in _reader_module_priority_for_path(path):
        reader_class = _load_reader_class(module_name)
        if reader_class is None:
            continue
        if _is_bioformats_reader(reader_class):
            continue
        candidates.append(reader_class)
    return tuple(candidates)


def _bioformats_reader_class_for_path(path: str):
    """Return BioFormats reader class matched from BioIO plugin registry."""
    plugins_by_extension = _plugins_by_extension()
    candidate_modules: list[str] = []
    for extension in _path_extension_candidates(path):
        for plugin_entry in plugins_by_extension.get(extension, ()):
            module_name = _plugin_entry_module_name(plugin_entry)
            if not module_name:
                continue
            candidate_modules.append(module_name)
    if not candidate_modules:
        for plugin_entries in plugins_by_extension.values():
            for plugin_entry in plugin_entries:
                module_name = _plugin_entry_module_name(plugin_entry)
                if module_name:
                    candidate_modules.append(module_name)

    seen: set[str] = set()
    for module_name in candidate_modules:
        if module_name in seen:
            continue
        seen.add(module_name)
        reader_class = _load_reader_class(module_name)
        if reader_class is None:
            continue
        if _is_bioformats_reader(reader_class):
            return reader_class
    return None


def _open_bioimage_with_reader(path: str, reader, *, dask_tiles: bool = True):
    """Open a BioImage with an explicit reader and optional dask tiling."""
    import bioio

    kwargs = {}
    if dask_tiles and _is_bioformats_reader(reader):
        kwargs["dask_tiles"] = True
    return bioio.BioImage(path, reader=reader, **kwargs)


def _bioimage_reader_identity(image) -> str | None:
    """Return reader identity for an open BioImage-like object."""
    return _reader_identifier(getattr(image, "reader", None))


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
            _LOGGER.debug("get_reader returning None: empty path list provided.")
            return None
        path = path[0]
    if not isinstance(path, str) or not path:
        _LOGGER.debug("get_reader returning None: invalid path input %r.", path)
        return None
    try:
        reader_path = _resolve_reader_path(path)
    except FileNotFoundError:
        _LOGGER.debug(
            "get_reader returning None: path is neither a local file nor a supported network path: %s",
            path,
        )
        return None
    except Exception as exc:
        _LOGGER.warning(
            "get_reader failed to resolve input path %s",
            path,
            exc_info=exc,
        )
        return None
    try:
        import bioio
    except ImportError:
        _LOGGER.debug("get_reader returning None: bioio is not installed.")
        return None
    if not hasattr(bioio.BioImage, "determine_plugin"):
        _LOGGER.debug(
            "get_reader returning None: bioio.BioImage.determine_plugin is unavailable."
        )
        return None
    try:
        _ensure_java_truststore()
    except Exception as exc:
        _LOGGER.debug("Failed to preconfigure Java truststore options.", exc_info=exc)
    try:
        plugin = bioio.BioImage.determine_plugin(reader_path)
    except (
        AttributeError,
        ImportError,
        ValueError,
        RuntimeError,
        FileNotFoundError,
        OSError,
        UnsupportedFileFormatError,
        Exception,
    ) as exc:
        _LOGGER.warning(
            "get_reader failed to determine a BioIO plugin for %s (resolved to %s)",
            path,
            reader_path,
            exc_info=exc,
        )
        return None
    if plugin is None:
        _LOGGER.debug(
            "get_reader returning None: no BioIO plugin matched %s (resolved to %s)",
            path,
            reader_path,
        )
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
        _LOGGER.error("BioIO import failed while reading %s", path, exc_info=exc)
        raise ImportError(
            "BioIO is required for the SenoQuant reader."
        ) from exc

    base_name = _path_display_name(path)
    try:
        reader_path = _resolve_reader_path(path)
    except Exception as exc:
        _LOGGER.error("Failed to resolve reader path for %s", path, exc_info=exc)
        raise
    try:
        image = _open_bioimage(reader_path)
    except Exception as exc:
        _LOGGER.error(
            "Failed to open BioImage for %s (resolved to %s)",
            path,
            reader_path,
            exc_info=exc,
        )
        raise
    metadata_image = _open_metadata_bioimage(reader_path, fallback_image=image)
    try:
        layers: list[tuple] = []
        data_reader_name = _bioimage_reader_identity(image)
        metadata_reader_name = _bioimage_reader_identity(metadata_image)
        if metadata_image is not image:
            _LOGGER.info(
                "Using data reader %s with metadata reader %s for %s",
                data_reader_name or "<unknown>",
                metadata_reader_name or "<unknown>",
                path,
            )
        colormap_cycle = _colormap_cycle()
        # Try to get channel colors from OME metadata
        channel_colors = _get_channel_colors_from_ome(metadata_image)
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
            scene_metadata_image = metadata_image
            if scene_metadata_image is not image:
                metadata_scene_id = _set_scene_with_index_fallback(
                    scene_metadata_image,
                    scene_id=scene_id,
                    scene_idx=scene_idx,
                )
                if metadata_scene_id is None:
                    _LOGGER.warning(
                        "Metadata reader failed to set scene %s for %s; falling back to data reader metadata.",
                        scene_id,
                        path,
                    )
                    scene_metadata_image = image
                elif metadata_scene_id != scene_id:
                    _LOGGER.debug(
                        "Metadata reader scene-id mismatch for %s: requested %s, using %s at index %d.",
                        path,
                        scene_id,
                        metadata_scene_id,
                        scene_idx,
                    )
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
                    metadata_image=scene_metadata_image,
                    data_reader_name=data_reader_name,
                    metadata_reader_name=(
                        _bioimage_reader_identity(scene_metadata_image)
                        or metadata_reader_name
                    ),
                )
            )

        return layers
    except Exception as exc:
        _LOGGER.error("Failed while reading image layers for %s", path, exc_info=exc)
        raise


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


def _set_scene_with_index_fallback(
    image,
    *,
    scene_id: str,
    scene_idx: int,
) -> str | None:
    """Set scene by id, then fall back to index-matched scene id."""
    try:
        image.set_scene(scene_id)
        return scene_id
    except Exception as id_exc:
        scenes = list(getattr(image, "scenes", []) or [])
        if 0 <= scene_idx < len(scenes):
            index_scene_id = scenes[scene_idx]
            try:
                image.set_scene(index_scene_id)
                return str(index_scene_id)
            except Exception as index_exc:
                _LOGGER.debug(
                    "Failed metadata scene index fallback for scene %s at index %d.",
                    scene_id,
                    scene_idx,
                    exc_info=index_exc,
                )
        _LOGGER.debug(
            "Failed to set metadata scene %s directly.",
            scene_id,
            exc_info=id_exc,
        )
        return None


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
    layout.addWidget(QLabel(f"File: {_path_display_name(path)}"))
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
    """Open a BioImage, preferring fast non-BioFormats readers for data.

    Parameters
    ----------
    path : str
        File path to read.

    Returns
    -------
    bioio.BioImage
        BioIO image instance for pixel loading.
    """
    _ensure_java_truststore()
    import bioio

    detected_plugin = None
    if hasattr(bioio.BioImage, "determine_plugin"):
        try:
            detected_plugin = bioio.BioImage.determine_plugin(path)
        except Exception as exc:
            _LOGGER.debug(
                "Failed to determine preferred BioIO plugin for %s",
                path,
                exc_info=exc,
            )

    if detected_plugin is not None and not _is_bioformats_reader(detected_plugin):
        try:
            return _open_bioimage_with_reader(path, detected_plugin, dask_tiles=True)
        except Exception as exc:
            _LOGGER.debug(
                "Detected non-BioFormats reader %s failed for %s",
                _reader_identifier(detected_plugin) or "<unknown>",
                path,
                exc_info=exc,
            )

    detected_identifier = _reader_identifier(detected_plugin)
    for reader_class in _candidate_fast_reader_classes(path):
        if _reader_identifier(reader_class) == detected_identifier:
            continue
        try:
            image = _open_bioimage_with_reader(path, reader_class, dask_tiles=True)
            _LOGGER.info(
                "Opened %s with fast BioIO reader %s",
                path,
                _reader_identifier(reader_class) or "<unknown>",
            )
            return image
        except Exception as exc:
            _LOGGER.debug(
                "Fast BioIO reader %s failed for %s",
                _reader_identifier(reader_class) or "<unknown>",
                path,
                exc_info=exc,
            )

    if detected_plugin is not None:
        try:
            return _open_bioimage_with_reader(path, detected_plugin, dask_tiles=True)
        except Exception as exc:
            _LOGGER.warning(
                "Detected BioIO reader %s failed for %s; trying default auto reader.",
                _reader_identifier(detected_plugin) or "<unknown>",
                path,
                exc_info=exc,
            )

    return bioio.BioImage(path)


def _open_metadata_bioimage(path: str, *, fallback_image):
    """Open metadata-focused BioImage, preferring BioFormats when available."""
    bioformats_reader = _bioformats_reader_class_for_path(path)
    if bioformats_reader is None:
        return fallback_image
    if _is_bioformats_reader(getattr(fallback_image, "reader", None)):
        return fallback_image
    try:
        return _open_bioimage_with_reader(
            path,
            bioformats_reader,
            dask_tiles=False,
        )
    except Exception as exc:
        _LOGGER.info(
            "BioFormats metadata open failed for %s; using data reader metadata fallback.",
            path,
            exc_info=exc,
        )
        return fallback_image


def _colormap_cycle() -> Iterable[str]:
    """Return an iterator cycling through approved colormap names.

    Returns
    -------
    iterable of str
        Cycle of colormap names to assign to reader layers.
    """
    names = [
        "blue",
        "green",
        "red",
        "yellow",
        "cyan",
        "bop blue",
        "bop orange",
        "bop purple",
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


def _extract_channel_names(image) -> list[str]:
    """Extract normalized channel names from a BioImage-like object."""
    try:
        names = getattr(image, "channel_names", None)
    except Exception:
        return []

    if names is None:
        return []
    if isinstance(names, str):
        raw_names = [names]
    else:
        try:
            raw_names = list(names)
        except Exception:
            return []

    normalized: list[str] = []
    for name in raw_names:
        if name is None:
            normalized.append("")
            continue
        try:
            normalized.append(str(name).strip())
        except Exception:
            normalized.append("")
    return normalized


def _is_generic_channel_name(name: str) -> bool:
    """Return True for placeholder channel-name values."""
    normalized = str(name).strip()
    if not normalized:
        return True
    return bool(
        _GENERIC_CHANNEL_COLON_PATTERN.fullmatch(normalized)
        or _GENERIC_CHANNEL_INDEX_PATTERN.fullmatch(normalized)
    )


def _all_channel_names_generic(names: list[str]) -> bool:
    """Return True when every channel name is a generic placeholder."""
    return bool(names) and all(_is_generic_channel_name(name) for name in names)


def _resolve_channel_names(metadata_image, data_image, c_size: int) -> list[str]:
    """Resolve channel names with metadata-reader-first fallback to data reader."""
    resolved = _extract_channel_names(metadata_image)

    if not resolved or _all_channel_names_generic(resolved):
        data_names = _extract_channel_names(data_image)
        if data_names and (not resolved or data_names != resolved):
            resolved = data_names

    final_names: list[str] = []
    for index in range(c_size):
        name = ""
        if index < len(resolved):
            name = resolved[index].strip()
        final_names.append(name or f"Channel {index}")
    return final_names


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
    metadata_image=None,
    data_reader_name: str | None = None,
    metadata_reader_name: str | None = None,
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
    metadata_image : bioio.BioImage, optional
        BioImage used as metadata source. Falls back to ``image`` when omitted.
    data_reader_name : str or None, optional
        Reader identifier used for pixel loading.
    metadata_reader_name : str or None, optional
        Reader identifier used for metadata extraction.

    Returns
    -------
    list of tuple
        napari layer tuples for each channel.
    """
    metadata_source = metadata_image if metadata_image is not None else image
    metadata_reader_name = metadata_reader_name or data_reader_name
    dims = getattr(image, "dims", None)
    axes_present = _axes_present(image)
    t_size = getattr(dims, "T", 1) if "T" in axes_present else 1
    c_size = getattr(dims, "C", 1) if "C" in axes_present else 1
    z_size = getattr(dims, "Z", 1) if "Z" in axes_present else 1
    resolved_channel_names = _resolve_channel_names(metadata_source, image, c_size)

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
        layer_name = f"{layer_name} - {resolved_channel_names[channel_index]}"

        physical_sizes = _physical_pixel_sizes(metadata_source)
        meta = {
            "name": layer_name,
            "blending": "additive",
            "metadata": {
                "bioio_metadata": getattr(metadata_source, "metadata", None),
                "scene_info": scene_meta,
                "path": path,
                "channel_index": channel_index,
                "channel_names": resolved_channel_names,
                "physical_pixel_sizes": physical_sizes,
                "data_reader": data_reader_name,
                "metadata_reader": metadata_reader_name,
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
