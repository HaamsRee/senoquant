"""Hugging Face model download utilities."""

from __future__ import annotations

import os
from pathlib import Path

try:
    from huggingface_hub import hf_hub_download  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - optional dependency
    hf_hub_download = None


def _resolve_repo_id(default_repo: str) -> str:
    """Resolve the model repository ID from environment or default."""
    env_repo = os.environ.get("SENOQUANT_MODEL_REPO")
    if env_repo:
        return env_repo.strip()
    return default_repo


DEFAULT_REPO_ID = "HaamsRee/senoquant-models"
MODEL_CACHE_ENV = "SENOQUANT_MODEL_DIR"


def ensure_hf_model(
    filename: str,
    target_dir: Path,
    *,
    repo_id: str,
    revision: str | None = None,
) -> Path:
    """Ensure a model file exists, downloading from HF if needed.

    Parameters
    ----------
    filename : str
        File name to download from the HF repo.
    target_dir : pathlib.Path
        Directory to check for a model shipped alongside SenoQuant.
    repo_id : str
        Hugging Face repo id, e.g. "HaamsRee/senoquant-models".
    revision : str or None, optional
        Optional revision/tag/commit to pin.

    Returns
    -------
    pathlib.Path
        Local path to the downloaded model file.

    """
    target_dir = Path(target_dir)
    candidate = target_dir / filename
    if candidate.exists():
        return candidate

    if hf_hub_download is None:
        message = (
            "huggingface_hub is required to download models. "
            "Install it with `pip install huggingface_hub`."
        )
        raise RuntimeError(message)

    resolved_repo = _resolve_repo_id(repo_id)
    cache_dir = os.environ.get(MODEL_CACHE_ENV, "").strip() or None
    path = hf_hub_download(
        repo_id=resolved_repo,
        filename=filename,
        revision=revision,
        cache_dir=cache_dir,
    )
    return Path(path)
