"""Tests for Hugging Face model utilities."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

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

        # Mock hf_hub_download
        mock_path = tmp_path / "test_model.onnx"
        mock_download = __import__("unittest.mock").mock.MagicMock(return_value=str(mock_path))
        monkeypatch.setattr(
            "senoquant.tabs.segmentation.models.hf.hf_hub_download",
            mock_download,
        )

        result = ensure_hf_model(
            "test_model.onnx",
            tmp_path,
            repo_id="test/repo",
        )

        assert result == mock_path
        mock_download.assert_called_once()

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