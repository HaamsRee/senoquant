"""Tests for Hugging Face model utilities."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest


class TestEnsureHfModel:
    """Tests for ensure_hf_model function."""

    def test_resolve_repo_id_from_env(self, monkeypatch) -> None:
        """Test repo ID resolution from environment variable."""
        from senoquant.tabs.segmentation.models.hf import _resolve_repo_id

        monkeypatch.setenv("SENOQUANT_MODEL_REPO", "custom/repo")
        result = _resolve_repo_id("default/repo")
        assert result == "custom/repo"

    def test_resolve_repo_id_default(self, monkeypatch) -> None:
        """Test repo ID resolution uses default when env not set."""
        from senoquant.tabs.segmentation.models.hf import (
            DEFAULT_REPO_ID,
            _resolve_repo_id,
        )

        monkeypatch.delenv("SENOQUANT_MODEL_REPO", raising=False)
        result = _resolve_repo_id(DEFAULT_REPO_ID)
        assert result == DEFAULT_REPO_ID

    def test_ensure_hf_model_with_huggingface_hub(self, tmp_path, monkeypatch) -> None:
        """Test ensure_hf_model downloads from Hugging Face when available."""
        from senoquant.tabs.segmentation.models.hf import ensure_hf_model

        packaged_dir = tmp_path / "package" / "models"
        cache_dir = tmp_path / "managed-cache"
        mock_path = cache_dir / "test_model.onnx"
        mock_download = MagicMock(return_value=str(mock_path))
        monkeypatch.setattr(
            "senoquant.tabs.segmentation.models.hf.hf_hub_download",
            mock_download,
        )
        monkeypatch.setenv("SENOQUANT_MODEL_DIR", str(cache_dir))

        result = ensure_hf_model(
            "test_model.onnx",
            packaged_dir,
            repo_id="test/repo",
        )

        assert result == mock_path
        mock_download.assert_called_once_with(
            repo_id="test/repo",
            filename="test_model.onnx",
            revision=None,
            cache_dir=str(cache_dir),
        )
        assert not packaged_dir.exists()

    def test_ensure_hf_model_uses_default_hf_cache(
        self, tmp_path, monkeypatch
    ) -> None:
        """Leave cache placement to Hugging Face outside native launchers."""
        from senoquant.tabs.segmentation.models.hf import ensure_hf_model

        mock_path = tmp_path / "test_model.onnx"
        mock_download = MagicMock(return_value=str(mock_path))
        monkeypatch.setattr(
            "senoquant.tabs.segmentation.models.hf.hf_hub_download",
            mock_download,
        )
        monkeypatch.delenv("SENOQUANT_MODEL_DIR", raising=False)

        ensure_hf_model(
            "test_model.onnx",
            tmp_path / "package",
            repo_id="test/repo",
        )

        assert mock_download.call_args.kwargs["cache_dir"] is None
        assert "local_dir" not in mock_download.call_args.kwargs

    def test_ensure_hf_model_without_huggingface_hub(self, tmp_path) -> None:
        """Test ensure_hf_model raises when huggingface_hub not available."""
        from senoquant.tabs.segmentation.models.hf import (
            ensure_hf_model,
            hf_hub_download,
        )

        # When hf_hub_download is None, should raise RuntimeError
        if hf_hub_download is None:
            with pytest.raises(RuntimeError):
                ensure_hf_model(
                    "test_model.onnx",
                    tmp_path,
                    repo_id="test/repo",
                )

    def test_ensure_hf_model_file_exists(self, tmp_path) -> None:
        """Test ensure_hf_model returns existing file without downloading."""
        from senoquant.tabs.segmentation.models.hf import ensure_hf_model

        # Create a mock file that already exists
        existing_file = tmp_path / "existing_model.onnx"
        existing_file.write_text("mock model data")

        result = ensure_hf_model(
            "existing_model.onnx",
            tmp_path,
            repo_id="test/repo",
        )

        assert result == existing_file
