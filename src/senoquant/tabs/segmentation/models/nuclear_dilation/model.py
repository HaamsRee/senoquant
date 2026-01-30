"""Nuclear dilation cytoplasmic segmentation model."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from scipy import ndimage as ndi

from senoquant.tabs.segmentation.models.base import SenoQuantSegmentationModel
from senoquant.utils import layer_data_asarray

if TYPE_CHECKING:
    from pathlib import Path


class NuclearDilationModel(SenoQuantSegmentationModel):
    """Dilates nuclear masks to approximate cytoplasm.

    This model only requires a nuclear segmentation mask and dilates it
    to approximate cytoplasmic boundaries. It is useful when cytoplasmic
    staining is weak or unavailable.

    Notes
    -----
    - Only supports cytoplasmic segmentation task.
    - Requires nuclear_layer, ignores cytoplasmic_layer.

    """

    def __init__(self, models_root: Path | None = None) -> None:
        """Initialize the nuclear dilation model wrapper.

        Parameters
        ----------
        models_root : pathlib.Path or None
            Optional root directory for model storage.

        """
        super().__init__("nuclear_dilation", models_root=models_root)

    def run(self, **kwargs: object) -> dict:
        """Run nuclear dilation for cytoplasmic segmentation.

        Parameters
        ----------
        **kwargs
            task : str
                Must be "cytoplasmic" for this model.
            nuclear_layer : napari.layers.Labels
                Nuclear segmentation mask layer.
            cytoplasmic_layer : napari.layers.Image or None
                Ignored by this model.
            settings : dict
                Model settings keyed by ``details.json``.

        Returns
        -------
        dict
            Dictionary with:
            - ``masks``: dilated nuclear label image

        """
        task = kwargs.get("task")
        if task != "cytoplasmic":
            msg = "Nuclear dilation only supports cytoplasmic segmentation."
            raise ValueError(msg)

        nuclear_layer = kwargs.get("nuclear_layer")
        settings = kwargs.get("settings", {})

        if nuclear_layer is None:
            msg = "Nuclear layer is required for nuclear dilation."
            raise ValueError(msg)

        nuclear_data = layer_data_asarray(nuclear_layer)
        if nuclear_data is None:
            msg = "Failed to read nuclear layer data."
            raise ValueError(msg)

        nuclear_data = nuclear_data.astype(np.uint32, copy=False)
        settings_dict = {} if not isinstance(settings, dict) else settings
        dilation_iterations = max(int(settings_dict.get("dilation_iterations", 5)), 1)

        dilated_labels = np.zeros_like(nuclear_data)
        for label_id in np.unique(nuclear_data):
            if label_id == 0:
                continue
            mask = nuclear_data == label_id
            dilated_mask = ndi.binary_dilation(
                mask,
                iterations=dilation_iterations,
            )
            dilated_labels[dilated_mask] = label_id

        return {"masks": dilated_labels}
