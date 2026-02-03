"""UFish-based spot enhancement utilities."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
from types import MethodType
from typing import TYPE_CHECKING, Any, cast

import numpy as np

from senoquant.tabs.segmentation.models.hf import (
    DEFAULT_REPO_ID,
    ensure_hf_model,
)

try:  # pragma: no cover - optional dependency
    from ufish.api import UFish
except ImportError:  # pragma: no cover - optional dependency
    _repo_root = Path(__file__).resolve().parents[5]
    _vendored_root = _repo_root / "_vendor" / "ufish"
    if _vendored_root.exists():
        vendored_root = str(_vendored_root)
        if vendored_root not in sys.path:
            sys.path.insert(0, vendored_root)
        try:
            from ufish.api import UFish
        except ImportError:
            UFish = None
    else:
        UFish = None

try:  # pragma: no cover - optional dependency
    import onnxruntime as ort
except ImportError:  # pragma: no cover - optional dependency
    ort = None

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ufish.api import UFish as UFishType


@dataclass(slots=True)
class UFishConfig:
    """Configuration for UFish enhancement."""

    weights_path: str | None = None
    load_from_internet: bool = False
    device: str | None = None


class _UFishState:
    def __init__(self) -> None:
        self.model: UFishType | None = None
        self.weights_loaded = False
        self.device: str | None = None
        self.weights_path: str | None = None


_UFISH_STATE = _UFishState()
_UFISH_HF_FILENAME = "ufish.onnx"


def _ensure_ufish_available() -> None:
    if UFish is None:  # pragma: no cover - import guard
        msg = "ufish is required for spot enhancement."
        raise ImportError(msg)


def _resolve_default_weights_path() -> Path:
    """Resolve the default UFish ONNX path, downloading from HF if needed."""
    target_dir = Path(__file__).resolve().parent
    return ensure_hf_model(
        _UFISH_HF_FILENAME,
        target_dir,
        repo_id=DEFAULT_REPO_ID,
    )


def _preferred_providers() -> list[str]:
    if ort is None:
        return []
    available = set(ort.get_available_providers())
    preferred = [
        "CUDAExecutionProvider",
        "ROCMExecutionProvider",
        "DmlExecutionProvider",
        "DirectMLExecutionProvider",
        "CoreMLExecutionProvider",
        "CPUExecutionProvider",
    ]
    providers = [provider for provider in preferred if provider in available]
    return providers or list(available)


def _select_onnx_providers(device: str | None) -> list[str]:
    preferred = _preferred_providers()
    if not device:
        return preferred
    if device == "cuda":
        return [
            p
            for p in preferred
            if p in {"CUDAExecutionProvider", "CPUExecutionProvider"}
        ]
    if device == "dml":
        return [
            p
            for p in preferred
            if p
            in {
                "DmlExecutionProvider",
                "DirectMLExecutionProvider",
                "CPUExecutionProvider",
            }
        ]
    if device == "mps":
        return [
            p
            for p in preferred
            if p in {"CoreMLExecutionProvider", "CPUExecutionProvider"}
        ]
    return preferred


def _patch_onnx_loader(model: UFishType) -> None:
    if ort is None:
        return
    ort_any = cast("Any", ort)

    def _load_onnx(
        self: UFishType,
        onnx_path: str,
        providers: list[str] | None = None,
    ) -> None:
        providers = providers or _select_onnx_providers(
            getattr(self, "_device", None),
        )
        self.ort_session = ort_any.InferenceSession(
            str(onnx_path),
            providers=providers,
        )
        self.model = None

    model._load_onnx = MethodType(_load_onnx, model)  # noqa: SLF001


def _get_ufish(config: UFishConfig) -> UFishType:
    _ensure_ufish_available()
    if _UFISH_STATE.model is None or _UFISH_STATE.device != config.device:
        ufish_cls = cast("type[UFishType]", UFish)
        ufish_any = cast("Any", ufish_cls)
        if config.device:
            _UFISH_STATE.model = ufish_any(device=config.device)
        else:
            _UFISH_STATE.model = ufish_any()
        _patch_onnx_loader(cast("UFishType", _UFISH_STATE.model))
        _UFISH_STATE.weights_loaded = False
        _UFISH_STATE.device = config.device
        _UFISH_STATE.weights_path = None
    return cast("UFishType", _UFISH_STATE.model)


def _ensure_weights(model: UFishType, config: UFishConfig) -> None:
    if config.weights_path:
        weights_path = Path(config.weights_path).expanduser().resolve()
    else:
        try:
            weights_path = _resolve_default_weights_path()
        except RuntimeError as exc:
            msg = (
                "Could not download UFish weights from Hugging Face. "
                "Install `huggingface_hub`, configure network access, "
                "or provide UFishConfig(weights_path=...)."
            )
            raise RuntimeError(msg) from exc

    resolved_path = str(weights_path)
    if _UFISH_STATE.weights_loaded and _UFISH_STATE.weights_path == resolved_path:
        return
    model.load_weights(resolved_path)
    _UFISH_STATE.weights_loaded = True
    _UFISH_STATE.weights_path = resolved_path


def enhance_image(
    image: np.ndarray,
    *,
    config: UFishConfig | None = None,
) -> np.ndarray:
    """Enhance an image using UFish and return the enhanced image."""
    if config is None:
        config = UFishConfig()
    model = _get_ufish(config)
    _ensure_weights(model, config)
    image = np.asarray(image)
    _pred_spots, enhanced = model.predict(image)
    return np.asarray(enhanced)
