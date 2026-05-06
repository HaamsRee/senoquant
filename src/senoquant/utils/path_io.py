"""Path I/O helpers for local and remote filesystem targets.

This module centralizes save-path handling for local paths, UNC paths,
and URI-based remote paths (for example ``smb://`` or ``memory://``).
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
from typing import Any
from urllib.parse import unquote, urlparse

import numpy as np


def _is_windows_drive_path(path: str) -> bool:
    """Return True when the path resembles a Windows drive path."""
    return len(path) >= 2 and path[1] == ":" and path[0].isalpha()


def _unc_to_smb_uri(path: str) -> str:
    """Convert a UNC path into an SMB URI."""
    parts = [part for part in path.strip("\\").split("\\") if part]
    if len(parts) < 2:
        raise ValueError(f"Unsupported UNC path format: {path}")
    server = parts[0]
    share_and_file = "/".join(parts[1:])
    return f"smb://{server}/{share_and_file}"


def is_remote(path: str | Path) -> bool:
    """Return True when a path targets a non-local filesystem."""
    text = str(path)
    if not text:
        return False
    if text.startswith("\\\\"):
        return True
    if _is_windows_drive_path(text):
        return False
    if "://" in text:
        scheme = urlparse(text).scheme.lower()
        return scheme not in {"", "file"}
    if ":/" in text and not text.startswith("/"):
        # Handles malformed URI inputs like "smb:/server/share".
        scheme = text.split(":", 1)[0].lower()
        return scheme not in {"", "file"}
    return False


def normalize_uri(path: str | Path) -> str:
    """Normalize local, UNC, and URI-based paths."""
    text = str(path)
    if not text:
        return text
    if text.startswith("\\\\"):
        return _unc_to_smb_uri(text)
    if _is_windows_drive_path(text):
        return text
    parsed = urlparse(text)
    if parsed.scheme and not _is_windows_drive_path(text):
        scheme = parsed.scheme.lower()
        if scheme == "file":
            local = unquote(parsed.path)
            return str(Path(local).expanduser())
        if scheme == "smb":
            if parsed.netloc:
                rest = unquote(parsed.path).replace("\\", "/").lstrip("/")
                return f"smb://{parsed.netloc}/{rest}" if rest else f"smb://{parsed.netloc}"
            rest = text.split(":", 1)[1].replace("\\", "/").lstrip("/")
            return f"smb://{rest}"
        return text
    return str(Path(text).expanduser())


def native_display_path(path: str | Path) -> str:
    """Return a local path string using the current platform's separators.

    URI-style paths are preserved because rewriting separators inside a URI can
    change its meaning. This helper is intended for UI display, not storage.
    """
    text = str(path)
    if not text or "://" in text or is_remote(text):
        return text
    return str(Path(text).expanduser())


def join(base: str | Path, *parts: str | Path) -> str:
    """Join path fragments for local and remote targets."""
    base_text = normalize_uri(base)
    if is_remote(base_text):
        parsed = urlparse(base_text)
        clean_parts = [str(part).replace("\\", "/").strip("/") for part in parts]
        if parsed.scheme and parsed.netloc:
            prefix = f"{parsed.scheme}://{parsed.netloc}"
            path_parts = [parsed.path.strip("/"), *clean_parts]
            combined = "/".join(item for item in path_parts if item)
            return f"{prefix}/{combined}" if combined else prefix
        root = base_text.rstrip("/\\")
        for part in clean_parts:
            if part:
                root = f"{root}/{part}"
        return root
    return str(Path(base_text).joinpath(*[str(part) for part in parts]))


def _require_fsspec():
    """Import fsspec lazily for remote-path operations."""
    try:
        import fsspec
    except Exception as exc:  # pragma: no cover - optional dependency
        raise ImportError("fsspec is required for remote output paths.") from exc
    return fsspec


def _remote_fs_and_path(path: str):
    """Return fsspec filesystem and filesystem path for a URI."""
    fsspec = _require_fsspec()
    return fsspec.core.url_to_fs(path)


def _parent_uri(path: str) -> str:
    """Return parent URI for local or remote paths."""
    if is_remote(path):
        parsed = urlparse(path)
        if parsed.scheme and parsed.netloc:
            clean = parsed.path.rstrip("/")
            if "/" not in clean.lstrip("/"):
                return f"{parsed.scheme}://{parsed.netloc}"
            parent = clean.rsplit("/", 1)[0]
            return f"{parsed.scheme}://{parsed.netloc}{parent}"
        return path.rsplit("/", 1)[0]
    return str(Path(path).parent)


def exists(path: str | Path) -> bool:
    """Return whether the path exists."""
    target = normalize_uri(path)
    if is_remote(target):
        fs, fs_path = _remote_fs_and_path(target)
        return bool(fs.exists(fs_path))
    return Path(target).exists()


def mkdirs(path: str | Path) -> str:
    """Create the directory (and parents) if needed."""
    target = normalize_uri(path)
    if is_remote(target):
        fs, fs_path = _remote_fs_and_path(target)
        fs.makedirs(fs_path, exist_ok=True)
        return target
    Path(target).mkdir(parents=True, exist_ok=True)
    return target


def write_json(path: str | Path, payload: dict[str, Any]) -> str:
    """Write JSON payload to local or remote path."""
    target = normalize_uri(path)
    mkdirs(_parent_uri(target))
    if is_remote(target):
        fsspec = _require_fsspec()
        with fsspec.open(target, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        return target
    target_path = Path(target)

    with target_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    return str(target_path)


def write_numpy(path: str | Path, data: np.ndarray) -> str:
    """Write a numpy array to local or remote path."""
    target = normalize_uri(path)
    mkdirs(_parent_uri(target))
    if is_remote(target):
        fsspec = _require_fsspec()
        with fsspec.open(target, "wb") as handle:
            np.save(handle, np.asarray(data))
        return target
    target_path = Path(target)
    np.save(target_path, np.asarray(data))
    return str(target_path)


def copy_local_to_target(local_path: str | Path, target_path: str | Path) -> str:
    """Copy a local file to a local or remote target path."""
    source = Path(local_path).expanduser()
    if not source.is_file():
        raise FileNotFoundError(source)
    target = normalize_uri(target_path)
    mkdirs(_parent_uri(target))
    if is_remote(target):
        fsspec = _require_fsspec()
        with source.open("rb") as src, fsspec.open(target, "wb") as dst:
            shutil.copyfileobj(src, dst, length=1024 * 1024)
        return target
    local_target = Path(target)
    shutil.copy2(source, local_target)
    return str(local_target)
