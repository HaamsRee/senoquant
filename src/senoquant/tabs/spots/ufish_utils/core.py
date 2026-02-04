"""UFish-based spot enhancement utilities.

This module wraps UFish inference for SenoQuant spot detection workflows.
It handles:

- optional import of UFish from site-packages or vendored sources,
- ONNX Runtime execution-provider selection,
- model/weights caching between calls, and
- default ONNX weight retrieval from the SenoQuant Hugging Face model repo.

Notes
-----
Weight loading priority is:

1. explicit ``UFishConfig.weights_path``,
2. legacy ``UFishConfig.load_from_internet``, then
3. default ``ufish.onnx`` resolved via :func:`ensure_hf_model`.
"""

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
    """Configuration for UFish enhancement.

    Parameters
    ----------
    weights_path : str or None, optional
        Explicit local path to ONNX/PyTorch weights. When provided, this path
        is used directly and takes precedence over all other loading modes.
    load_from_internet : bool, optional
        Legacy compatibility mode that calls
        ``UFish.load_weights_from_internet()`` directly.
    device : {"cuda", "dml", "mps"} or None, optional
        Preferred accelerator mode used to influence ONNX Runtime provider
        ordering when constructing UFish sessions.
    """

    weights_path: str | None = None
    load_from_internet: bool = False
    device: str | None = None


class _UFishState:
    """In-process cache for the UFish model and loaded weights."""

    def __init__(self) -> None:
        """Initialize empty cached state."""
        self.model: UFishType | None = None
        self.weights_loaded = False
        self.device: str | None = None
        self.weights_path: str | None = None


_UFISH_STATE = _UFishState()
_UFISH_HF_FILENAME = "ufish.onnx"


def _ensure_ufish_available() -> None:
    """Raise a helpful error when UFish cannot be imported.

    Raises
    ------
    ImportError
        If the ``ufish`` package is unavailable from both normal and vendored
        import locations.
    """
    if UFish is None:  # pragma: no cover - import guard
        msg = "ufish is required for spot enhancement."
        raise ImportError(msg)


def _resolve_default_weights_path() -> Path:
    """Resolve the default UFish ONNX path.

    Returns
    -------
    pathlib.Path
        Local path to ``ufish.onnx``. The file is downloaded to the
        ``ufish_utils`` directory if it does not already exist.

    Raises
    ------
    RuntimeError
        If the Hugging Face download helper is unavailable or download fails.
    """
    target_dir = Path(__file__).resolve().parent
    return ensure_hf_model(
        _UFISH_HF_FILENAME,
        target_dir,
        repo_id=DEFAULT_REPO_ID,
    )


def _preferred_providers() -> list[str]:
    """Return ONNX Runtime providers ordered by GPU preference.

    Returns
    -------
    list[str]
        Providers available in the current runtime, ordered from most
        preferred accelerator to CPU fallback.
    """
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
    """Choose execution providers for a requested device hint.

    Parameters
    ----------
    device : str or None
        Device hint from :class:`UFishConfig`.

    Returns
    -------
    list[str]
        Provider names to pass to ``onnxruntime.InferenceSession``.
    """
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
    """Monkey-patch UFish ONNX loader to use SenoQuant provider selection.

    Parameters
    ----------
    model : UFishType
        UFish instance whose private ``_load_onnx`` method will be replaced.
    """
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
    """Return a cached UFish instance for the requested configuration.

    Parameters
    ----------
    config : UFishConfig
        Runtime configuration used to determine whether the cached model can be
        reused or must be re-instantiated.

    Returns
    -------
    UFishType
        Ready-to-use UFish instance with patched ONNX loading behavior.
    """
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
    """Ensure model weights are loaded according to configuration.

    Parameters
    ----------
    model : UFishType
        Active UFish model instance.
    config : UFishConfig
        Weight source and device settings.

    Raises
    ------
    RuntimeError
        If neither Hugging Face/default loading nor fallback loading succeeds.
    """
    if config.weights_path:
        weights_path = Path(config.weights_path).expanduser().resolve()
        resolved_path = str(weights_path)
        if _UFISH_STATE.weights_loaded and _UFISH_STATE.weights_path == resolved_path:
            return
        model.load_weights(resolved_path)
        _UFISH_STATE.weights_loaded = True
        _UFISH_STATE.weights_path = resolved_path
        return

    if config.load_from_internet:
        if _UFISH_STATE.weights_loaded and _UFISH_STATE.weights_path == "internet":
            return
        model.load_weights_from_internet()
        _UFISH_STATE.weights_loaded = True
        _UFISH_STATE.weights_path = "internet"
        return

    try:
        weights_path = _resolve_default_weights_path()
    except RuntimeError:
        # Keep legacy behavior when HF download dependencies are unavailable.
        if _UFISH_STATE.weights_loaded and _UFISH_STATE.weights_path == "default":
            return
        model.load_weights()
        _UFISH_STATE.weights_loaded = True
        _UFISH_STATE.weights_path = "default"
        return
    except Exception as exc:
        try:
            if _UFISH_STATE.weights_loaded and _UFISH_STATE.weights_path == "default":
                return
            model.load_weights()
            _UFISH_STATE.weights_loaded = True
            _UFISH_STATE.weights_path = "default"
            return
        except Exception:
            msg = (
                "Could not load UFish weights from local default or Hugging Face. "
                "Provide UFishConfig(weights_path=...) or ensure model download access."
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
    """Enhance an image using UFish.

    Parameters
    ----------
    image : numpy.ndarray
        Input image array. UFish supports 2D images and common 3D stack
        layouts handled by UFish internally.
    config : UFishConfig or None, optional
        Optional runtime configuration. If omitted, default behavior is used.

    Returns
    -------
    numpy.ndarray
        Enhanced image produced by UFish with the same dimensionality as the
        input image.

    Raises
    ------
    ImportError
        If UFish cannot be imported.
    RuntimeError
        If weights cannot be loaded from configured/default sources.
    """
    if config is None:
        config = UFishConfig()
    model = _get_ufish(config)
    _ensure_weights(model, config)
    image = np.asarray(image)
    _pred_spots, enhanced = model.predict(image)
    return np.asarray(enhanced)
