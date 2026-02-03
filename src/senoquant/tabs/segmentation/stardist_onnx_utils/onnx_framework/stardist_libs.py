"""Helpers for locating and loading StarDist compiled extensions."""

from __future__ import annotations

import importlib.machinery
import importlib.util
import sys
import types
from pathlib import Path


def ensure_stardist_libs(  # noqa: C901, PLR0912, PLR0915
    utils_root: Path,
    stardist_pkg: str,
) -> tuple[bool, bool]:
    """Ensure StarDist compiled extensions can be imported.

    Parameters
    ----------
    utils_root : pathlib.Path
        Root path to the ``stardist_onnx_utils`` package.
    stardist_pkg : str
        Fully-qualified package name for the vendored StarDist package.

    Returns
    -------
    tuple[bool, bool]
        Tuple of ``(has_2d, has_3d)`` indicating which compiled
        extensions are available.

    """
    csbdeep_root = utils_root / "_csbdeep"
    if csbdeep_root.exists():
        csbdeep_path = str(csbdeep_root)
        if csbdeep_path not in sys.path:
            sys.path.insert(0, csbdeep_path)

    if stardist_pkg not in sys.modules:
        pkg = types.ModuleType(stardist_pkg)
        pkg.__path__ = [str(utils_root / "_stardist")]
        sys.modules[stardist_pkg] = pkg

    base_pkg = f"{stardist_pkg}.lib"
    lib_dirs: list[Path] = []
    seen_dirs: set[Path] = set()

    def _append_if_exists(path: Path) -> None:
        if not path.exists():
            return
        resolved = path.resolve()
        if resolved in seen_dirs:
            return
        seen_dirs.add(resolved)
        lib_dirs.append(resolved)

    _append_if_exists(utils_root / "_stardist" / "lib")
    for entry in list(sys.path):
        if not entry:
            continue
        try:
            legacy_candidate = (
                Path(entry)
                / "senoquant"
                / "tabs"
                / "segmentation"
                / "stardist_onnx_utils"
                / "_stardist"
                / "lib"
            )
            ext_candidate = Path(entry) / "senoquant_stardist_ext" / "lib"
        except (TypeError, ValueError, OSError):
            continue
        _append_if_exists(legacy_candidate)
        _append_if_exists(ext_candidate)

    if base_pkg in sys.modules:
        pkg = sys.modules[base_pkg]
        pkg.__path__ = [str(p) for p in lib_dirs]
    else:
        pkg = types.ModuleType(base_pkg)
        pkg.__path__ = [str(p) for p in lib_dirs]
        sys.modules[base_pkg] = pkg

    for module_name in (f"{base_pkg}.stardist2d", f"{base_pkg}.stardist3d"):
        try:
            spec = importlib.util.find_spec(module_name)
        except (ImportError, AttributeError, ValueError):
            spec = None
        if spec and spec.origin:
            try:
                candidate = Path(spec.origin).parent
            except (TypeError, OSError):
                candidate = None
            if candidate is not None and candidate.exists():
                lib_dirs.append(candidate)

    mod2d = f"{base_pkg}.stardist2d"
    mod3d = f"{base_pkg}.stardist3d"

    def _stub(*_args: object, **_kwargs: object) -> None:
        msg = "StarDist compiled ops are unavailable."
        raise RuntimeError(msg)

    def _module_available(module_name: str) -> bool:
        module = sys.modules.get(module_name)
        if module is not None:
            return getattr(module, "__file__", None) is not None
        try:
            spec = importlib.util.find_spec(module_name)
        except (ImportError, AttributeError, ValueError):
            return False
        return bool(spec and spec.origin)

    def _try_load_dll(module_name: str, dll_path: Path) -> bool:
        try:
            loader = importlib.machinery.ExtensionFileLoader(
                module_name,
                str(dll_path),
            )
            spec = importlib.util.spec_from_file_location(
                module_name,
                str(dll_path),
                loader=loader,
            )
            if spec is None or spec.loader is None:
                return False
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            sys.modules[module_name] = module
        except (ImportError, OSError, AttributeError, ValueError):
            return False
        else:
            return True

    if not _module_available(mod2d):
        for lib_dir in lib_dirs:
            candidates = sorted(lib_dir.glob("stardist2d*.dll"))
            if candidates and _try_load_dll(mod2d, candidates[0]):
                break
    if not _module_available(mod3d):
        for lib_dir in lib_dirs:
            candidates = sorted(lib_dir.glob("stardist3d*.dll"))
            if candidates and _try_load_dll(mod3d, candidates[0]):
                break

    has_2d = _module_available(mod2d)
    has_3d = _module_available(mod3d)

    if has_2d and mod2d in sys.modules and getattr(
        sys.modules[mod2d], "__file__", None,
    ) is None:
        del sys.modules[mod2d]
    if not has_2d and mod2d not in sys.modules:
        module = types.ModuleType(mod2d)
        module.c_star_dist = _stub  # type: ignore[attr-defined]
        module.c_non_max_suppression_inds_old = _stub  # type: ignore[attr-defined]
        module.c_non_max_suppression_inds = _stub  # type: ignore[attr-defined]
        sys.modules[mod2d] = module

    if has_3d and mod3d in sys.modules and getattr(
        sys.modules[mod3d], "__file__", None,
    ) is None:
        del sys.modules[mod3d]
    if not has_3d and mod3d not in sys.modules:
        module = types.ModuleType(mod3d)
        module.c_star_dist3d = _stub  # type: ignore[attr-defined]
        module.c_polyhedron_to_label = _stub  # type: ignore[attr-defined]
        module.c_non_max_suppression_inds = _stub  # type: ignore[attr-defined]
        sys.modules[mod3d] = module

    return has_2d, has_3d
