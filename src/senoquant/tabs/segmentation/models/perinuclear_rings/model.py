"""Perinuclear rings cytoplasmic segmentation model."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from scipy import ndimage as ndi

from senoquant.tabs.segmentation.models.base import SenoQuantSegmentationModel
from senoquant.utils import layer_data_asarray

if TYPE_CHECKING:
    from pathlib import Path


class PerinuclearRingsModel(SenoQuantSegmentationModel):
    """Creates perinuclear rings from nuclear masks.

    This model generates ring-shaped labels around nuclei by eroding the
    nuclear mask inward and dilating it outward, then subtracting the
    eroded mask from the dilated mask. This is useful for detecting
    perinuclear markers that localize to the region immediately
    surrounding the nucleus.

    The erosion parameter has a minimum of 1 pixel to ensure that the
    resulting rings maintain at least 1 pixel overlap with the original
    nuclear labels, which is required for label relationship logic in
    quantification and batch processing.

    Notes
    -----
    - Only supports cytoplasmic segmentation task.
    - Requires nuclear_layer, ignores cytoplasmic_layer.
    - Maintains label IDs from the original nuclear segmentation.

    """

    def __init__(self, models_root: Path | None = None) -> None:
        """Initialize the perinuclear rings model wrapper.

        Parameters
        ----------
        models_root : pathlib.Path or None
            Optional root directory for model storage.

        """
        super().__init__("perinuclear_rings", models_root=models_root)

    def run(self, **kwargs: object) -> dict:
        """Generate perinuclear rings from nuclear segmentation.

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
                Model settings keyed by ``details.json``:
                - ``erosion_px``: pixels to erode inward (min 1)
                - ``dilation_px``: pixels to dilate outward

        Returns
        -------
        dict
            Dictionary with:
            - ``masks``: perinuclear ring label image

        Raises
        ------
        ValueError
            If task is not "cytoplasmic" or nuclear_layer is missing.

        """
        task = kwargs.get("task")
        if task != "cytoplasmic":
            msg = "Perinuclear rings only supports cytoplasmic segmentation."
            raise ValueError(msg)

        nuclear_layer = kwargs.get("nuclear_layer")
        settings = kwargs.get("settings", {})

        if nuclear_layer is None:
            msg = "Nuclear layer is required for perinuclear rings."
            raise ValueError(msg)

        nuclear_data = layer_data_asarray(nuclear_layer)
        if nuclear_data is None:
            msg = "Failed to read nuclear layer data."
            raise ValueError(msg)

        nuclear_data = nuclear_data.astype(np.uint32, copy=False)
        settings_dict = {} if not isinstance(settings, dict) else settings
        
        # Ensure erosion is at least 1 pixel for label relationship logic
        erosion_px = max(int(settings_dict.get("erosion_px", 2)), 1)
        dilation_px = max(int(settings_dict.get("dilation_px", 5)), 0)

        ring_labels = np.zeros_like(nuclear_data)

        # Process each nucleus individually to maintain label relationships
        for label_id in np.unique(nuclear_data):
            if label_id == 0:
                continue
            
            # Create binary mask for this nucleus
            nucleus_mask = nuclear_data == label_id
            
            # Erode inward (minimum 1 px to maintain overlap)
            eroded_mask = ndi.binary_erosion(
                nucleus_mask,
                iterations=erosion_px,
            )
            
            # Dilate outward
            dilated_mask = ndi.binary_dilation(
                nucleus_mask,
                iterations=dilation_px,
            )
            
            # Ring is the difference: dilated - eroded
            # This creates a ring that includes the original boundary
            ring_mask = dilated_mask & ~eroded_mask
            
            # Assign the original label ID to the ring
            ring_labels[ring_mask] = label_id

        return {"masks": ring_labels}
