"""Shared runtime primitives for default StarDist ONNX segmentation models.

This module centralizes the execution pipeline used by the default 2D and 3D
StarDist ONNX models. Variant-specific values (layouts, model filenames,
scaling constants, and postprocessing requirements) are supplied via
``StarDistOnnxVariantConfig`` while ``StarDistOnnxBaseModel`` handles:

- layer extraction and validation,
- optional intensity normalization,
- ONNX session setup and tiled inference,
- StarDist postprocessing into instance labels.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import onnxruntime as ort
from scipy import ndimage as ndi

from senoquant.tabs.segmentation.models.base import SenoQuantSegmentationModel
from senoquant.tabs.segmentation.stardist_onnx_utils.model_runtime_mixin import (
    StarDistOnnxRuntimeMixin,
)
from senoquant.tabs.segmentation.stardist_onnx_utils.onnx_framework import (
    normalize,
    predict_tiled,
)
from senoquant.utils import layer_data_asarray

if TYPE_CHECKING:
    from senoquant.tabs.segmentation.stardist_onnx_utils.onnx_framework.inspect.valid_sizes import (
        ValidSizePattern,
    )


@dataclass(frozen=True, slots=True)
class StarDistOnnxVariantConfig:
    """Variant-specific runtime parameters for StarDist ONNX models.

    Attributes
    ----------
    model_key : str
        Folder/model identifier (for example ``"default_2d"``).
    expected_ndim : int
        Required spatial dimensionality of input image arrays.
    expected_shape_label : str
        Human-readable shape label used in validation error messages.
    input_layout : str
        ONNX input tensor layout string (for example ``"NHWC"`` or
        ``"NDHWC"``).
    prob_layout : str
        ONNX probability output layout string.
    dist_layout : str
        ONNX distance/ray output layout string.
    object_diameter_reference_px : float
        Reference object diameter in pixels used to derive image scaling.
    scale_axes : tuple of str
        Axis names used when reporting the scale dictionary passed to
        StarDist postprocessing (for example ``("Y", "X")``).
    default_onnx_filename : str
        Preferred ONNX filename downloaded from the model repository when
        local files are missing.
    model_relative_candidates : tuple of str
        Candidate ONNX paths (relative to ``model_dir``) checked in order.
    div_by_fallback : int
        Per-axis divisibility fallback used when graph inspection fails.
    cap_xy_only : bool
        Whether tile-size capping should only apply to XY axes (3D behavior)
        instead of all axes.
    snap_skip_axes : tuple of int
        Axes excluded when snapping tile shapes to valid ONNX size patterns.
    enforce_post_snap_divisibility : bool
        Whether to re-apply ``div_by`` rounding after valid-size snapping.
    require_stardist_3d : bool
        If ``True``, run 3D StarDist postprocessing; otherwise use 2D.
    compiled_ops_error : str
        Error message raised when required compiled StarDist ops are missing.
    """

    model_key: str
    expected_ndim: int
    expected_shape_label: str
    input_layout: str
    prob_layout: str
    dist_layout: str
    object_diameter_reference_px: float
    scale_axes: tuple[str, ...]
    default_onnx_filename: str
    model_relative_candidates: tuple[str, ...]
    div_by_fallback: int
    cap_xy_only: bool
    snap_skip_axes: tuple[int, ...]
    enforce_post_snap_divisibility: bool
    require_stardist_3d: bool
    compiled_ops_error: str


class StarDistOnnxBaseModel(StarDistOnnxRuntimeMixin, SenoQuantSegmentationModel):
    """Shared executable model for StarDist ONNX 2D/3D variants.

    Notes
    -----
    Concrete model modules should provide a ``StarDistOnnxVariantConfig`` and
    instantiate this base class with that configuration. The runtime mixin
    supplies ONNX graph/tiling helpers while this class orchestrates end-to-end
    inference and postprocessing.
    """

    def __init__(
        self,
        *,
        variant: StarDistOnnxVariantConfig,
        models_root=None,
    ) -> None:
        """Initialize a StarDist ONNX runtime model.

        Parameters
        ----------
        variant : StarDistOnnxVariantConfig
            Variant-specific behavior and model-discovery configuration.
        models_root : pathlib.Path or None, optional
            Optional override for the root models directory used by
            ``SenoQuantSegmentationModel``.
        """
        super().__init__(variant.model_key, models_root=models_root)
        self._variant = variant
        self._sessions: dict[Path, ort.InferenceSession] = {}
        self._rays_class = None
        self._has_stardist_2d_lib = False
        self._has_stardist_3d_lib = False
        self._div_by_cache: dict[Path, tuple[int, ...]] = {}
        self._overlap_cache: dict[Path, tuple[int, ...]] = {}
        self._valid_size_cache: dict[Path, list["ValidSizePattern"] | None] = {}

    def run(self, **kwargs) -> dict:
        """Run StarDist ONNX nuclear segmentation.

        Parameters
        ----------
        **kwargs
            Runtime options passed by the segmentation frontend.
            Supported keys:

            - ``task`` : str
              Must be ``"nuclear"``.
            - ``layer`` : object
              napari image layer containing 2D or 3D single-channel data.
            - ``settings`` : dict, optional
              Model settings parsed from ``details.json`` and UI controls.

        Returns
        -------
        dict
            Mapping with these keys:

            - ``masks`` : numpy.ndarray
              Labeled instance segmentation output.
            - ``prob`` : numpy.ndarray
              Predicted foreground probability map.
            - ``dist`` : numpy.ndarray
              Predicted radial distance features.
            - ``info`` : dict
              StarDist postprocessing metadata (NMS points/probabilities/etc.).

        Raises
        ------
        ValueError
            If task or input dimensionality is invalid.
        RuntimeError
            If required compiled StarDist operations are unavailable.
        """
        task = kwargs.get("task")
        if task != "nuclear":
            raise ValueError("StarDist ONNX only supports nuclear segmentation.")

        layer = kwargs.get("layer")
        settings = kwargs.get("settings", {})
        image = self._extract_layer_data(layer, required=True)
        original_shape = image.shape

        if image.ndim != self._variant.expected_ndim:
            raise ValueError(
                "StarDist ONNX "
                f"{self._variant.expected_ndim}D expects a "
                f"{self._variant.expected_shape_label} image."
            )

        image = image.astype(np.float32, copy=False)
        image, scale = self._scale_input(image, settings)
        image = self._scale_intensity(image)
        if settings.get("normalize", True):
            pmin = float(settings.get("pmin", 1.0))
            pmax = float(settings.get("pmax", 99.8))
            image = normalize(image, pmin=pmin, pmax=pmax)

        model_path = self._resolve_model_path(image.ndim)
        session = self._get_session(image.ndim)
        input_name, output_names = self._resolve_io_names(session)

        grid = self._infer_grid(
            image,
            session,
            input_name,
            output_names,
            self._variant.input_layout,
            self._variant.prob_layout,
            model_path=model_path,
        )

        tile_shape, overlap = self._infer_tiling(
            image,
            model_path,
            session,
            input_name,
            output_names,
            self._variant.input_layout,
        )
        div_by = self._div_by_cache.get(model_path, grid)

        try:
            prob, dist = self._predict(
                image=image,
                session=session,
                input_name=input_name,
                output_names=output_names,
                grid=grid,
                tile_shape=tile_shape,
                overlap=overlap,
                div_by=div_by,
            )
        except Exception:
            if "CoreMLExecutionProvider" not in session.get_providers():
                raise
            session = self._get_session(
                image.ndim,
                providers_override=["CPUExecutionProvider"],
            )
            prob, dist = self._predict(
                image=image,
                session=session,
                input_name=input_name,
                output_names=output_names,
                grid=grid,
                tile_shape=tile_shape,
                overlap=overlap,
                div_by=div_by,
            )

        prob_thresh = float(settings.get("prob_thresh", 0.5))
        nms_thresh = float(settings.get("nms_thresh", 0.4))

        self._ensure_stardist_lib_stubs()

        if self._variant.require_stardist_3d:
            from senoquant.tabs.segmentation.stardist_onnx_utils.onnx_framework import (
                instances_from_prediction_3d,
            )

            if not self._has_stardist_3d_lib:
                raise RuntimeError(self._variant.compiled_ops_error)
            rays = self._get_rays_class()(n=dist.shape[-1])
            labels, info = instances_from_prediction_3d(
                prob,
                dist,
                grid=grid,
                prob_thresh=prob_thresh,
                nms_thresh=nms_thresh,
                rays=rays,
                scale=scale,
                img_shape=original_shape,
            )
        else:
            from senoquant.tabs.segmentation.stardist_onnx_utils.onnx_framework import (
                instances_from_prediction_2d,
            )

            if not self._has_stardist_2d_lib:
                raise RuntimeError(self._variant.compiled_ops_error)
            labels, info = instances_from_prediction_2d(
                prob,
                dist,
                grid=grid,
                prob_thresh=prob_thresh,
                nms_thresh=nms_thresh,
                scale=scale,
                img_shape=original_shape,
            )

        return {"masks": labels, "prob": prob, "dist": dist, "info": info}

    def _predict(
        self,
        *,
        image: np.ndarray,
        session: ort.InferenceSession,
        input_name: str,
        output_names: list[str],
        grid: tuple[int, ...],
        tile_shape: tuple[int, ...],
        overlap: tuple[int, ...],
        div_by: tuple[int, ...],
    ) -> tuple[np.ndarray, np.ndarray]:
        """Execute tiled ONNX inference and return StarDist outputs.

        Parameters
        ----------
        image : numpy.ndarray
            Normalized input image in spatial form (without batch/channel
            dimensions).
        session : onnxruntime.InferenceSession
            Prepared ONNX Runtime session.
        input_name : str
            Name of the ONNX input tensor.
        output_names : list of str
            Names of ONNX outputs in ``[probability, distance]`` order.
        grid : tuple of int
            Estimated StarDist grid/stride by axis.
        tile_shape : tuple of int
            Per-axis tile shape used by tiled inference.
        overlap : tuple of int
            Per-axis overlap between neighboring tiles.
        div_by : tuple of int
            Per-axis divisibility constraints expected by the network.

        Returns
        -------
        tuple of numpy.ndarray
            ``(prob, dist)`` model outputs.
        """
        return predict_tiled(
            image,
            session,
            input_name=input_name,
            output_names=output_names,
            grid=grid,
            input_layout=self._variant.input_layout,
            prob_layout=self._variant.prob_layout,
            dist_layout=self._variant.dist_layout,
            tile_shape=tile_shape,
            overlap=overlap,
            div_by=div_by,
        )

    def _scale_input(
        self,
        image: np.ndarray,
        settings: dict,
    ) -> tuple[np.ndarray, dict[str, float] | None]:
        """Scale an input image to match the model training diameter.

        Parameters
        ----------
        image : numpy.ndarray
            Input image in model-native dimensionality.
        settings : dict
            Runtime settings; ``object_diameter_px`` is used if present.

        Returns
        -------
        tuple
            ``(scaled_image, scale_dict_or_none)`` where ``scale_dict_or_none``
            maps variant axes to scalar zoom factors, or ``None`` when no
            scaling is applied.

        Raises
        ------
        ValueError
            If ``object_diameter_px`` is non-positive or scaling collapses any
            dimension to an empty shape.
        """
        diameter_px = float(settings.get("object_diameter_px", 30.0))
        if diameter_px <= 0:
            raise ValueError("Object diameter (px) must be positive.")
        scale_factor = self._variant.object_diameter_reference_px / diameter_px
        if np.isclose(scale_factor, 1.0):
            return image, None

        scale = tuple(scale_factor for _ in range(image.ndim))
        scaled = ndi.zoom(image, scale, order=1)
        if min(scaled.shape) < 1:
            raise ValueError(
                "Scaling factor produced an empty image; adjust object diameter."
            )
        axis_scale = {axis: scale_factor for axis in self._variant.scale_axes}
        return scaled.astype(np.float32, copy=False), axis_scale

    @staticmethod
    def _scale_intensity(image: np.ndarray) -> np.ndarray:
        """Normalize image intensities to ``[0, 1]`` using min/max scaling.

        Parameters
        ----------
        image : numpy.ndarray
            Input image.

        Returns
        -------
        numpy.ndarray
            Normalized image. Original data is returned unchanged for invalid
            ranges (NaN/Inf bounds or zero dynamic range).
        """
        imin = float(np.nanmin(image))
        imax = float(np.nanmax(image))
        if not np.isfinite(imin) or not np.isfinite(imax):
            return image
        if imax <= imin:
            return image
        return ((image - imin) / (imax - imin)).astype(np.float32, copy=False)

    def _extract_layer_data(self, layer, required: bool) -> np.ndarray:
        """Extract NumPy data from a napari layer object.

        Parameters
        ----------
        layer : object or None
            napari layer-like object with a ``data`` attribute.
        required : bool
            If ``True``, missing layer input raises an exception.

        Returns
        -------
        numpy.ndarray
            Layer data as a squeezed NumPy array.

        Raises
        ------
        ValueError
            If ``required`` is ``True`` and ``layer`` is ``None``.
        """
        if layer is None:
            if required:
                raise ValueError("Layer is required for StarDist ONNX.")
            return None
        return layer_data_asarray(layer)

    def _get_session(
        self,
        ndim: int,
        *,
        providers_override: list[str] | None = None,
    ) -> ort.InferenceSession:
        """Return and cache an ONNX Runtime session for this variant.

        Parameters
        ----------
        ndim : int
            Expected model dimensionality used to resolve the ONNX file.
        providers_override : list of str or None, optional
            Explicit provider list. When provided, a session is recreated using
            these providers.

        Returns
        -------
        onnxruntime.InferenceSession
            Cached or newly created inference session.
        """
        model_path = self._resolve_model_path(ndim)
        session = self._sessions.get(model_path)
        if session is None or providers_override is not None:
            providers = providers_override or self._preferred_providers()
            preload = getattr(ort, "preload_dlls", None)
            if callable(preload):
                preload()
            session = ort.InferenceSession(str(model_path), providers=providers)
            self._sessions[model_path] = session
        return session

    @staticmethod
    def _preferred_providers() -> list[str]:
        """Return preferred ONNX Runtime providers in descending priority.

        Returns
        -------
        list of str
            Available providers, ordered to prefer GPU/accelerated runtimes
            over CPU when possible.
        """
        available = set(ort.get_available_providers())
        preferred = [
            "CUDAExecutionProvider",
            "ROCMExecutionProvider",
            "DirectMLExecutionProvider",
            "CoreMLExecutionProvider",
            "CPUExecutionProvider",
        ]
        providers = [provider for provider in preferred if provider in available]
        if not providers:
            providers = list(available)
        return providers
