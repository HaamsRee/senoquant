"""StarDist ONNX segmentation model implementation."""

from __future__ import annotations

from pathlib import Path
import importlib.util
import sys
import types
from typing import TYPE_CHECKING

import numpy as np
import onnxruntime as ort
from scipy import ndimage as ndi

from senoquant.utils import layer_data_asarray
from ..hf import DEFAULT_REPO_ID, ensure_hf_model
from ..base import SenoQuantSegmentationModel
from senoquant.tabs.segmentation.stardist_onnx_utils.onnx_framework import (
    normalize,
    predict_tiled,
)
from senoquant.tabs.segmentation.stardist_onnx_utils.onnx_framework.inspect import (
    make_probe_image,
)
if TYPE_CHECKING:
    from senoquant.tabs.segmentation.stardist_onnx_utils.onnx_framework.inspect.valid_sizes import (
        ValidSizePattern,
    )


class StarDistOnnxModel(SenoQuantSegmentationModel):
    """StarDist ONNX 2D segmentation model.

    This wrapper loads an exported StarDist 2D ONNX model, runs
    preprocessing and tiled inference, and postprocesses the outputs into
    instance labels using StarDist geometry and NMS utilities.

    Notes
    -----
    - Inputs must be single-channel images in YX (2D) order.
    - ONNX model outputs are assumed to be probability and distance maps.
    """

    def __init__(self, models_root=None) -> None:
        """Initialize the StarDist ONNX model wrapper.

        Parameters
        ----------
        models_root : pathlib.Path or None
            Optional root directory for model storage.
        """
        super().__init__("default_2d", models_root=models_root)
        self._sessions: dict[Path, ort.InferenceSession] = {}
        self._rays_class = None
        self._has_stardist_2d_lib = False
        self._has_stardist_3d_lib = False
        self._div_by_cache: dict[Path, tuple[int, ...]] = {}
        self._overlap_cache: dict[Path, tuple[int, ...]] = {}
        self._valid_size_cache: dict[Path, list["ValidSizePattern"] | None] = {}

    def run(self, **kwargs) -> dict:
        """Run StarDist ONNX for nuclear segmentation.

        Parameters
        ----------
        **kwargs
            task : str
                Must be "nuclear" for this model.
            layer : napari.layers.Image
                Single-channel image layer (YX or ZYX).
            settings : dict
                Model settings keyed by ``details.json``.

        Returns
        -------
        dict
            Dictionary with:
            - ``masks``: instance label image
            - ``prob``: probability map
            - ``dist``: distance/ray map
            - ``info``: NMS metadata (points, prob, dist)
        """
        task = kwargs.get("task")
        if task != "nuclear":
            raise ValueError("StarDist ONNX only supports nuclear segmentation.")

        layer = kwargs.get("layer")
        settings = kwargs.get("settings", {})
        image = self._extract_layer_data(layer, required=True)
        original_shape = image.shape

        if image.ndim != 2:
            raise ValueError("StarDist ONNX 2D expects a 2D (YX) image.")

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

        input_layout = "NHWC"
        prob_layout = "NHWC"
        dist_layout = "NYXR"

        grid = self._infer_grid(
            image,
            session,
            input_name,
            output_names,
            input_layout,
            prob_layout,
            model_path=model_path,
        )

        tile_shape, overlap = self._infer_tiling(
            image, model_path, session, input_name, output_names, input_layout
        )
        div_by = self._div_by_cache.get(model_path, grid)

        try:
            prob, dist = predict_tiled(
                image,
                session,
                input_name=input_name,
                output_names=output_names,
                grid=grid,
                input_layout=input_layout,
                prob_layout=prob_layout,
                dist_layout=dist_layout,
                tile_shape=tile_shape,
                overlap=overlap,
                div_by=div_by,
            )
        except Exception:
            if "CoreMLExecutionProvider" not in session.get_providers():
                raise
            session = self._get_session(
                image.ndim, providers_override=["CPUExecutionProvider"]
            )
            prob, dist = predict_tiled(
                image,
                session,
                input_name=input_name,
                output_names=output_names,
                grid=grid,
                input_layout=input_layout,
                prob_layout=prob_layout,
                dist_layout=dist_layout,
                tile_shape=tile_shape,
                overlap=overlap,
                div_by=div_by,
            )

        prob_thresh = float(settings.get("prob_thresh", 0.5))
        nms_thresh = float(settings.get("nms_thresh", 0.4))

        self._ensure_stardist_lib_stubs()
        from senoquant.tabs.segmentation.stardist_onnx_utils.onnx_framework import (
            instances_from_prediction_2d,
        )

        if not self._has_stardist_2d_lib:
            raise RuntimeError(
                "StarDist 2D compiled ops are missing. Build the "
                "extensions in stardist_onnx_utils/_stardist/lib."
            )
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

    def _scale_input(
        self, image: np.ndarray, settings: dict
    ) -> tuple[np.ndarray, dict[str, float] | None]:
        """Scale the input image to match training object sizes.

        Parameters
        ----------
        image : numpy.ndarray
            Input 2D image in YX order.
        settings : dict
            Model settings containing the ``object_diameter_px`` entry.

        Returns
        -------
        numpy.ndarray
            Scaled image. If no scaling is requested, returns the input image.
        dict[str, float] or None
            Scale factors keyed by axis (``"Y"``, ``"X"``) for rescaling
            predictions back to the original image space.
        """
        diameter_px = float(settings.get("object_diameter_px", 30.0))
        if diameter_px <= 0:
            raise ValueError("Object diameter (px) must be positive.")
        scale_factor = 17.44 / diameter_px
        if np.isclose(scale_factor, 1.0):
            return image, None

        scale = (scale_factor, scale_factor)
        scaled = ndi.zoom(image, scale, order=1)
        if min(scaled.shape) < 1:
            raise ValueError(
                "Scaling factor produced an empty image; adjust object diameter."
            )
        return scaled.astype(np.float32, copy=False), {"Y": scale_factor, "X": scale_factor}

    @staticmethod
    def _scale_intensity(image: np.ndarray) -> np.ndarray:
        """Scale image intensities into [0, 1] using min/max."""
        imin = float(np.nanmin(image))
        imax = float(np.nanmax(image))
        if not np.isfinite(imin) or not np.isfinite(imax):
            return image
        if imax <= imin:
            return image
        return ((image - imin) / (imax - imin)).astype(np.float32, copy=False)

    def _extract_layer_data(self, layer, required: bool) -> np.ndarray:
        """Return numpy data for a napari layer.

        Parameters
        ----------
        layer : object or None
            Napari layer to convert.
        required : bool
            Whether a missing layer should raise an error.

        Returns
        -------
        numpy.ndarray
            Layer data as an array.
        """
        if layer is None:
            if required:
                raise ValueError("Layer is required for StarDist ONNX.")
            return None
        return layer_data_asarray(layer)

    def _get_session(
        self, ndim: int, *, providers_override: list[str] | None = None
    ) -> ort.InferenceSession:
        """Return (and cache) an ONNX Runtime session for 2D or 3D models."""
        model_path = self._resolve_model_path(ndim)
        session = self._sessions.get(model_path)
        if session is None or providers_override is not None:
            providers = providers_override or self._preferred_providers()
            session = ort.InferenceSession(
                str(model_path),
                providers=providers,
            )
            self._sessions[model_path] = session
        return session

    @staticmethod
    def _preferred_providers() -> list[str]:
        """Return a provider list that prefers GPU providers when available."""
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

    def _infer_tiling(
        self,
        image: np.ndarray,
        model_path: Path,
        session: ort.InferenceSession,
        input_name: str,
        output_names: list[str],
        input_layout: str,
    ) -> tuple[tuple[int, ...], tuple[int, ...]]:
        """Infer tiling shape and overlap for ONNX tiled prediction.

        This method uses the ONNX inspection utilities to derive:
        - the per-axis divisibility requirement (``div_by``), and
        - a recommended overlap based on the empirical receptive field.

        The inferred values are cached per ONNX model path so the expensive
        inspection (graph parsing / RF probing) only happens once per model.
        If inspection fails for any reason, safe fallbacks are used:
        ``div_by = (1, ... )`` and ``overlap = (0, ... )``.

        Parameters
        ----------
        image : numpy.ndarray
            Input image used to determine spatial dimensionality and to
            clamp tile shape/overlap to valid ranges.
        model_path : pathlib.Path
            Path to the ONNX model, used as a cache key for inferred values.

        Returns
        -------
        tuple[tuple[int, ...], tuple[int, ...]]
            A tuple ``(tile_shape, overlap)``, each a per-axis tuple with
            the same length as ``image.ndim``. ``tile_shape`` is rounded
            down to the nearest multiple of ``div_by`` (never exceeding the
            input size), and ``overlap`` is clamped to ``[0, tile_size - 1]``.
            Tile sizes are additionally capped at 1024 pixels per axis to
            avoid feeding overly large tiles to the ONNX model.
        """
        ndim = image.ndim
        div_by = self._div_by_cache.get(model_path)
        if div_by is None:
            div_by = (16,) * ndim
            self._div_by_cache[model_path] = div_by

        overlap = self._overlap_cache.get(model_path)
        if overlap is None:
            try:
                from senoquant.tabs.segmentation.stardist_onnx_utils.onnx_framework.inspect.receptive_field import (
                    recommend_tile_overlap,
                )
            except Exception:
                overlap = (0,) * ndim
            else:
                try:
                    overlap = recommend_tile_overlap(model_path, ndim=ndim)
                except Exception:
                    overlap = (0,) * ndim
            self._overlap_cache[model_path] = overlap

        max_tile = 1024
        capped_shape = tuple(min(size, max_tile) for size in image.shape)

        tile_shape = tuple(
            max(div, (size // div) * div) if div > 0 else size
            for size, div in zip(capped_shape, div_by)
        )

        patterns = self._valid_size_cache.get(model_path)
        if patterns is None:
            try:
                from senoquant.tabs.segmentation.stardist_onnx_utils.onnx_framework.inspect.valid_sizes import (
                    infer_valid_size_patterns_from_path,
                )
            except Exception:
                patterns = None
            else:
                try:
                    patterns = infer_valid_size_patterns_from_path(
                        model_path,
                        input_layout,
                        ndim,
                    )
                except Exception:
                    patterns = None
            self._valid_size_cache[model_path] = patterns

        if patterns:
            from senoquant.tabs.segmentation.stardist_onnx_utils.onnx_framework.inspect.valid_sizes import (
                snap_shape,
            )

            tile_shape = snap_shape(tile_shape, patterns)
        tile_shape = tuple(
            max(16, (ts // 16) * 16)
            for ts in tile_shape
        )
        overlap = tuple(
            max(0, min(int(ov), max(0, ts - 1)))
            for ov, ts in zip(overlap, tile_shape)
        )
        return tile_shape, overlap

    def _resolve_model_path(self, ndim: int) -> Path:
        """Resolve the ONNX model file for 2D or 3D inference.

        Parameters
        ----------
        ndim : int
            Spatial dimensionality (2 or 3).

        Returns
        -------
        pathlib.Path
            Path to the ONNX model file.

        Raises
        ------
        FileNotFoundError
            If no ONNX model file is found.
        ValueError
            If multiple candidates are found without a default name.
        """
        if ndim != 2:
            raise ValueError("StarDist ONNX 2D expects a 2D model.")
        default_filename = "default_2d.onnx"
        candidates = [
            self.model_dir / "onnx_models" / default_filename,
            self.model_dir / default_filename,
            self.model_dir / "onnx_models" / "stardist_mod_2d.onnx",
            self.model_dir / "onnx_models" / "stardist2d_2D_versatile_fluo.onnx",
            self.model_dir / "stardist_mod_2d.onnx",
            self.model_dir / "stardist2d_2D_versatile_fluo.onnx",
            self.model_dir / "stardist2d.onnx",
        ]

        for path in candidates:
            if path.exists():
                return path

        try:
            downloaded = ensure_hf_model(
                default_filename,
                self.model_dir / "onnx_models",
                repo_id=DEFAULT_REPO_ID,
            )
        except RuntimeError:
            downloaded = None
        if downloaded is not None and downloaded.exists():
            return downloaded

        matches = []
        for folder in (self.model_dir / "onnx_models", self.model_dir):
            if folder.exists():
                matches.extend(sorted(folder.glob("*.onnx")))

        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise ValueError(
                "Multiple ONNX files found; keep one or use default file names."
            )
        raise FileNotFoundError(
            "No ONNX model found. Place the exported model in the model folder "
            "or allow SenoQuant to download it from the model repository."
        )

    def _resolve_io_names(self, session: ort.InferenceSession) -> tuple[str, list[str]]:
        """Resolve input and output tensor names for prob/dist inference."""
        inputs = session.get_inputs()
        outputs = session.get_outputs()
        if not inputs:
            raise RuntimeError("ONNX model has no inputs.")
        if len(outputs) < 2:
            raise RuntimeError("ONNX model must have prob and dist outputs.")

        input_name = inputs[0].name

        prob = None
        dist = None
        for output in outputs:
            name = output.name.lower()
            if "prob" in name and prob is None:
                prob = output
            elif "dist" in name and dist is None:
                dist = output

        if prob is None or dist is None:
            for output in outputs:
                shape = output.shape or []
                channel = shape[-1] if shape else None
                if channel == 1 and prob is None:
                    prob = output
                elif channel not in (None, 1) and dist is None:
                    dist = output

        if prob is None or dist is None:
            prob, dist = outputs[0], outputs[1]

        return input_name, [prob.name, dist.name]

    def _ensure_stardist_lib_stubs(self) -> None:
        """Ensure StarDist modules import without compiled extensions.

        This registers minimal stubs for compiled modules when shared
        libraries are absent, allowing Python utilities to import.
        """
        utils_root = self._get_utils_root()
        csbdeep_root = utils_root / "_csbdeep"
        if csbdeep_root.exists():
            csbdeep_path = str(csbdeep_root)
            if csbdeep_path not in sys.path:
                sys.path.insert(0, csbdeep_path)

        stardist_pkg = (
            "senoquant.tabs.segmentation.stardist_onnx_utils._stardist"
        )
        if stardist_pkg not in sys.modules:
            pkg = types.ModuleType(stardist_pkg)
            pkg.__path__ = [str(utils_root / "_stardist")]
            sys.modules[stardist_pkg] = pkg

        base_pkg = f"{stardist_pkg}.lib"
        lib_dirs = [utils_root / "_stardist" / "lib"]
        for entry in list(sys.path):
            if not entry:
                continue
            try:
                candidate = (
                    Path(entry)
                    / "senoquant"
                    / "tabs"
                    / "segmentation"
                    / "stardist_onnx_utils"
                    / "_stardist"
                    / "lib"
                )
            except Exception:
                continue
            if candidate.exists():
                lib_dirs.append(candidate)

        if base_pkg in sys.modules:
            pkg = sys.modules[base_pkg]
            pkg.__path__ = [str(p) for p in lib_dirs]
        else:
            pkg = types.ModuleType(base_pkg)
            pkg.__path__ = [str(p) for p in lib_dirs]
            sys.modules[base_pkg] = pkg

        def _stub(*_args, **_kwargs):
            raise RuntimeError("StarDist compiled ops are unavailable.")

        has_2d = False
        has_3d = False
        for lib_dir in lib_dirs:
            has_2d = has_2d or any(lib_dir.glob("stardist2d*.so")) or any(
                lib_dir.glob("stardist2d*.pyd")
            )
            has_3d = has_3d or any(lib_dir.glob("stardist3d*.so")) or any(
                lib_dir.glob("stardist3d*.pyd")
            )
        self._has_stardist_2d_lib = has_2d
        self._has_stardist_3d_lib = has_3d

        mod2d = f"{base_pkg}.stardist2d"
        if has_2d and mod2d in sys.modules:
            if getattr(sys.modules[mod2d], "__file__", None) is None:
                del sys.modules[mod2d]
        if not has_2d and mod2d not in sys.modules:
            module = types.ModuleType(mod2d)
            module.c_star_dist = _stub
            module.c_non_max_suppression_inds_old = _stub
            module.c_non_max_suppression_inds = _stub
            sys.modules[mod2d] = module

        mod3d = f"{base_pkg}.stardist3d"
        if has_3d and mod3d in sys.modules:
            if getattr(sys.modules[mod3d], "__file__", None) is None:
                del sys.modules[mod3d]
        if not has_3d and mod3d not in sys.modules:
            module = types.ModuleType(mod3d)
            module.c_star_dist3d = _stub
            module.c_polyhedron_to_label = _stub
            module.c_non_max_suppression_inds = _stub
            sys.modules[mod3d] = module

    def _get_rays_class(self):
        """Load and cache the StarDist Rays_GoldenSpiral class."""
        if self._rays_class is not None:
            return self._rays_class

        utils_root = self._get_utils_root()
        rays_path = utils_root / "_stardist" / "rays3d.py"
        if not rays_path.exists():
            raise FileNotFoundError("Could not locate StarDist rays3d.py.")

        module_name = "senoquant_stardist_rays3d"
        spec = importlib.util.spec_from_file_location(module_name, rays_path)
        if spec is None or spec.loader is None:
            raise ImportError("Failed to load StarDist rays3d module.")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self._rays_class = module.Rays_GoldenSpiral
        return self._rays_class

    def _get_utils_root(self) -> Path:
        """Return the stardist_onnx_utils package root."""
        return Path(__file__).resolve().parents[2] / "stardist_onnx_utils"

    def _infer_grid(
        self,
        image: np.ndarray,
        session: ort.InferenceSession,
        input_name: str,
        output_names: list[str],
        input_layout: str,
        prob_layout: str,
        *,
        model_path: Path | None = None,
    ) -> tuple[int, ...]:
        """Infer model grid/stride by running a probe tile.

        Parameters
        ----------
        image : numpy.ndarray
            Input image.
        session : onnxruntime.InferenceSession
            ONNX Runtime session.
        input_name : str
            ONNX input tensor name.
        output_names : list[str]
            ONNX output tensor names (prob, dist).
        input_layout : str
            Input layout string (e.g., "NHWC", "NDHWC").
        prob_layout : str
            Probability output layout string.

        Returns
        -------
        tuple[int, ...]
            Estimated grid/stride per axis.
        """
        probe = self._make_probe_image(
            image, model_path=model_path, input_layout=input_layout
        )
        if input_layout in ("NHWC", "NDHWC"):
            input_tensor = probe[np.newaxis, ..., np.newaxis]
        else:
            input_tensor = probe[np.newaxis, np.newaxis, ...]

        prob = session.run(output_names, {input_name: input_tensor})[0]
        if prob_layout in ("NHWC", "NDHWC"):
            out_shape = prob.shape[1:-1]
        elif prob_layout in ("NCHW", "NCDHW"):
            out_shape = prob.shape[2:]
        else:
            raise ValueError(f"Unsupported prob layout {prob_layout}.")

        grid = []
        for dim_in, dim_out in zip(probe.shape, out_shape):
            if dim_out in (0, None):
                grid.append(1)
                continue
            ratio = dim_in / dim_out
            grid.append(max(1, int(round(ratio))))
        return tuple(grid)

    def _make_probe_image(
        self,
        image: np.ndarray,
        *,
        model_path: Path | None = None,
        input_layout: str | None = None,
    ) -> np.ndarray:
        """Create a small probe image for grid inference."""
        return make_probe_image(
            image,
            model_path=model_path,
            input_layout=input_layout,
            div_by_cache=self._div_by_cache,
            valid_size_cache=self._valid_size_cache,
        )
