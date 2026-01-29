"""Tests for batch layer shims.

Notes
-----
Validates that lightweight layer wrappers preserve metadata and allow
layer collection replacement.
"""

from __future__ import annotations

import numpy as np

from senoquant.tabs.batch.layers import BatchViewer, Image, Labels


def test_batch_layers_store_metadata() -> None:
    """Store metadata in layer wrappers.

    Returns
    -------
    None
    """
    data = np.zeros((2, 2))
    meta = {"pixel": 1}
    image_layer = Image(data, "image", metadata=meta)
    label_layer = Labels(data, "labels", metadata=meta)

    assert image_layer.metadata == meta
    assert label_layer.metadata == meta


def test_batch_viewer_replaces_layers() -> None:
    """Replace layer lists in the viewer shim.

    Returns
    -------
    None
    """
    viewer = BatchViewer()
    viewer.set_layers([Image(None, "image")])
    assert len(viewer.layers) == 1
