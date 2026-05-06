"""Tests for local/remote path I/O helpers."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

import sys

from senoquant.utils import path_io


def test_normalize_uri_converts_unc_to_smb() -> None:
    """Convert UNC paths into SMB URIs."""
    normalized = path_io.normalize_uri(r"\\server\share\folder\file.tif")
    assert normalized == "smb://server/share/folder/file.tif"


def test_native_display_path_uses_platform_separators() -> None:
    """Format local paths for display without changing URI strings."""
    assert path_io.native_display_path("C:/tmp/input") == str(Path("C:/tmp/input"))
    assert path_io.native_display_path("/tmp/input") == str(Path("/tmp/input"))
    assert path_io.native_display_path("memory://bucket/input") == "memory://bucket/input"


def test_join_handles_local_and_remote(tmp_path: Path) -> None:
    """Join path fragments for both filesystem types."""
    local = path_io.join(tmp_path, "out", "file.txt")
    assert local.endswith("out/file.txt") or local.endswith("out\\file.txt")

    remote = path_io.join("memory://root/base", "child", "file.txt")
    assert remote == "memory://root/base/child/file.txt"

    remote_with_spaces = path_io.join("memory://root/base", " dir ", " file .txt ")
    assert remote_with_spaces == "memory://root/base/ dir / file .txt "


def test_local_write_json_write_numpy_and_copy(tmp_path: Path) -> None:
    """Write JSON/numpy outputs and copy files locally."""
    payload = {"schema": "senoquant.settings"}
    json_path = tmp_path / "out" / "settings.json"
    np_path = tmp_path / "out" / "array.npy"

    saved_json = path_io.write_json(json_path, payload)
    saved_np = path_io.write_numpy(np_path, np.ones((2, 2), dtype=np.uint16))

    assert path_io.exists(saved_json)
    assert path_io.exists(saved_np)
    assert json.loads(Path(saved_json).read_text(encoding="utf-8"))["schema"] == "senoquant.settings"

    source = tmp_path / "source.txt"
    source.write_text("copy", encoding="utf-8")
    copied = path_io.copy_local_to_target(source, tmp_path / "copy" / "source.txt")
    assert path_io.exists(copied)


def test_remote_write_and_copy_to_memory_filesystem(tmp_path: Path) -> None:
    """Write JSON/numpy and upload local files to memory://."""
    fsspec = pytest.importorskip("fsspec")
    fs = fsspec.filesystem("memory")

    json_uri = "memory://path-io-tests/out/settings.json"
    np_uri = "memory://path-io-tests/out/data.npy"

    path_io.write_json(json_uri, {"ok": True})
    path_io.write_numpy(np_uri, np.ones((2, 2), dtype=np.uint16))

    local = tmp_path / "local.txt"
    local.write_text("hello", encoding="utf-8")
    copied_uri = path_io.copy_local_to_target(local, "memory://path-io-tests/out/local.txt")

    assert copied_uri == "memory://path-io-tests/out/local.txt"
    assert fs.exists("path-io-tests/out/settings.json") or fs.exists("/path-io-tests/out/settings.json")
    assert fs.exists("path-io-tests/out/data.npy") or fs.exists("/path-io-tests/out/data.npy")
    assert fs.exists("path-io-tests/out/local.txt") or fs.exists("/path-io-tests/out/local.txt")

@pytest.mark.skipif(
    sys.platform == "win32", 
    reason="Windows natively strips trailing spaces from file and folder names."
)
def test_write_json_preserves_whitespace_in_local_filename(tmp_path: Path) -> None:
    """Preserve leading/trailing spaces inside local path segments."""
    json_path = tmp_path / " out " / " settings .json "
    saved = path_io.write_json(json_path, {"ok": True})

    assert Path(saved).name == " settings .json "
    assert path_io.exists(saved)


def test_remote_write_json_preserves_whitespace_in_uri() -> None:
    """Preserve spaces in remote URI segments."""
    fsspec = pytest.importorskip("fsspec")
    fs = fsspec.filesystem("memory")

    uri = "memory://path-io-tests/ out / settings .json "
    saved = path_io.write_json(uri, {"ok": True})

    assert saved == uri
    assert fs.exists("path-io-tests/ out / settings .json ") or fs.exists(
        "/path-io-tests/ out / settings .json "
    )
