"""Shared fixtures for headless tab tests."""

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _stub_model_downloads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Provide local model weights for the inference stubs without downloads."""
    from senoquant.tabs.segmentation.models import hf

    weights = tmp_path / "model-weights"
    weights.write_bytes(b"stub weights")
    monkeypatch.setattr(hf, "hf_hub_download", lambda **_kwargs: str(weights))
