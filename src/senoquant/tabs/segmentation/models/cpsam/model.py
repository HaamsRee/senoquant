"""CPSAM segmentation model implementation."""

from __future__ import annotations

from pathlib import Path
import numpy as np

from senoquant.utils import layer_data_asarray
from ..hf import DEFAULT_REPO_ID, ensure_hf_model
from ..base import SenoQuantSegmentationModel


class CPSAMModel(SenoQuantSegmentationModel):
    """CPSAM segmentation model implementation."""

    def __init__(self, models_root=None) -> None:
        """Initialize the CPSAM model wrapper."""
        super().__init__("cpsam", models_root=models_root)
        from cellpose.models import CellposeModel

        model_path = Path(self.model_dir) / "cpsam"
        if not model_path.exists():
            try:
                model_path = ensure_hf_model(
                    "cpsam",
                    self.model_dir,
                    repo_id=DEFAULT_REPO_ID,
                )
            except RuntimeError:
                pass
        # Always request GPU; Cellpose will fall back if unavailable.
        self._model = CellposeModel(gpu=True, pretrained_model=str(model_path))

    def run(self, **kwargs) -> dict:
        """Run CPSAM using the Cellpose API.

        Parameters
        ----------
        **kwargs
            task : str
                Segmentation task ("nuclear" or "cytoplasmic").
            layer : napari.layers.Image or None
                Nuclear image layer for nuclear task.
            cytoplasmic_layer : napari.layers.Image or None
                Cytoplasmic image layer for cytoplasmic task.
            nuclear_layer : napari.layers.Image or None
                Nuclear image layer for cytoplasmic task.
            settings : dict
                Model settings keyed by the details.json schema.

        Returns
        -------
        dict
            Dictionary containing masks, flows, and styles from Cellpose.
        """
        task = kwargs.get("task")
        settings = kwargs.get("settings", {})

        do_3d = bool(settings.get("use_3d", False))
        normalize = bool(settings.get("normalize", True))
        diameter = settings.get("diameter")
        flow_threshold = settings.get("flow_threshold", 0.4)
        cellprob_threshold = settings.get("cellprob_threshold", 0.0)
        n_iterations = settings.get("n_iterations", 0)

        if task == "nuclear":
            layer = kwargs.get("layer")
            image = self._extract_layer_data(layer, required=True)
            input_data = self._prepare_input(image)
        elif task == "cytoplasmic":
            cyto_layer = kwargs.get("cytoplasmic_layer")
            nuclear_layer = kwargs.get("nuclear_layer")
            cyto_image = self._extract_layer_data(cyto_layer, required=True)
            nuclear_image = self._extract_layer_data(
                nuclear_layer, required=False
            )
            if nuclear_image is None:
                input_data = self._prepare_input(cyto_image)
            else:
                input_data = self._prepare_input(
                    nuclear_image,
                    cyto_image,
                )
        else:
            raise ValueError("Unknown task for CPSAM.")

        masks, flows, styles = self._model.eval(
            input_data,
            normalize=normalize,
            diameter=diameter,
            flow_threshold=flow_threshold,
            cellprob_threshold=cellprob_threshold,
            do_3D=do_3d,
            z_axis=0 if do_3d else None,
            niter=n_iterations,
        )

        return {"masks": masks, "flows": flows, "styles": styles}

    def _extract_layer_data(self, layer, required: bool) -> np.ndarray | None:
        """Return numpy data for the given napari layer.

        Parameters
        ----------
        layer : object or None
            Napari layer to convert.
        required : bool
            Whether a missing layer should raise an error.

        Returns
        -------
        numpy.ndarray or None
            Layer data or None if not required and missing.
        """
        if layer is None:
            if required:
                raise ValueError("Layer is required for CPSAM.")
            return None
        return layer_data_asarray(layer)

    def _prepare_input(
        self,
        nuclear: np.ndarray,
        cytoplasmic: np.ndarray | None = None,
    ) -> np.ndarray:
        """Prepare CPSAM input as YX, ZYX, CYX, or ZCYX.

        Parameters
        ----------
        nuclear : numpy.ndarray
            Nuclear image data.
        cytoplasmic : numpy.ndarray or None
            Cytoplasmic image data, when provided.

        Returns
        -------
        numpy.ndarray
            Input array suitable for Cellpose eval.
        """
        if nuclear.ndim not in (2, 3):
            raise ValueError("Input image must be 2D or 3D.")
        if cytoplasmic is not None and cytoplasmic.shape != nuclear.shape:
            raise ValueError("Nuclear and cytoplasmic images must match in shape.")

        if cytoplasmic is None:
            return nuclear.astype(np.float32)

        axis = 0 if nuclear.ndim == 2 else 1
        stacked = np.stack([nuclear, cytoplasmic], axis=axis)
        return stacked.astype(np.float32)
