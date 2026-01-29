"""Tests for the cytoplasmic-only segmentation stub.

Notes
-----
Ensures the model initializes with the expected name.
"""

from __future__ import annotations

from senoquant.tabs.segmentation.models.cyto_only.model import CytoOnlyModel


def test_cyto_only_initializes() -> None:
    """Instantiate the cytoplasmic-only model.

    Returns
    -------
    None
    """
    model = CytoOnlyModel(models_root=None)
    assert model.name == "cyto_only"
