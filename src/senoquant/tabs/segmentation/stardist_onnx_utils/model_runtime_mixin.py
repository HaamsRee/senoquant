"""Shared helper mixin for StarDist ONNX runtime models.

This mixin holds ONNX graph inspection, model-path resolution, tensor-name
discovery, and StarDist support utilities. It is designed to be used by a
host class that provides variant configuration and caches.
"""

from __future__ import annotations

from pathlib import Path
import importlib.util

import numpy as np
import onnxruntime as ort

from senoquant.tabs.segmentation.models.hf import DEFAULT_REPO_ID, ensure_hf_model
from senoquant.tabs.segmentation.stardist_onnx_utils.onnx_framework.inspect import (
    make_probe_image,
)
from senoquant.tabs.segmentation.stardist_onnx_utils.onnx_framework.stardist_libs import (
    ensure_stardist_libs,
)


class StarDistOnnxRuntimeMixin:
    """Mixin providing ONNX/StarDist helper methods.

    Notes
    -----
    Host classes are expected to provide:

    - ``self._variant`` : ``StarDistOnnxVariantConfig``-compatible object.
    - ``self.model_dir`` : pathlib path to model assets.
    - ``self._div_by_cache`` : dict cache keyed by ONNX model path.
    - ``self._overlap_cache`` : dict cache keyed by ONNX model path.
    - ``self._valid_size_cache`` : dict cache keyed by ONNX model path.
    - ``self._rays_class`` : lazy-loaded StarDist rays class cache.
    """

    def _infer_tiling(
        self,
        image: np.ndarray,
        model_path: Path,
        session: ort.InferenceSession,
        input_name: str,
        output_names: list[str],
        input_layout: str,
    ) -> tuple[tuple[int, ...], tuple[int, ...]]:
        """Infer tile shape and overlap from ONNX inspection utilities.

        Parameters
        ----------
        image : numpy.ndarray
            Input image used to derive dimensionality and clamp tile bounds.
        model_path : pathlib.Path
            ONNX model path used as cache key for inferred values.
        session : onnxruntime.InferenceSession
            Unused in this implementation; accepted for API consistency.
        input_name : str
            Unused in this implementation; accepted for API consistency.
        output_names : list of str
            Unused in this implementation; accepted for API consistency.
        input_layout : str
            ONNX input layout string used by valid-size inspection.

        Returns
        -------
        tuple of tuple of int
            ``(tile_shape, overlap)`` with one value per spatial axis.

        Notes
        -----
        If ONNX inspection helpers fail, fallback divisibility and overlap
        values are used from variant configuration.
        """
        del session, input_name, output_names

        ndim = image.ndim
        div_by = self._div_by_cache.get(model_path)
        if div_by is None:
            try:
                from senoquant.tabs.segmentation.stardist_onnx_utils.onnx_framework.inspect import (
                    infer_div_by,
                )
            except Exception:
                div_by = (self._variant.div_by_fallback,) * ndim
            else:
                try:
                    div_by = infer_div_by(model_path, ndim=ndim)
                except Exception:
                    div_by = (self._variant.div_by_fallback,) * ndim
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
        if self._variant.cap_xy_only and image.ndim == 3:
            capped_shape = (
                image.shape[0],
                min(image.shape[1], max_tile),
                min(image.shape[2], max_tile),
            )
        else:
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

            tile_shape = snap_shape(
                tile_shape,
                patterns,
                skip_axes=self._variant.snap_skip_axes,
            )

        if self._variant.enforce_post_snap_divisibility:
            tile_shape = tuple(
                max(int(div), (int(ts) // int(div)) * int(div))
                if int(div) > 0 else int(ts)
                for ts, div in zip(tile_shape, div_by)
            )

        overlap = tuple(
            max(0, min(int(ov), max(0, int(ts) - 1)))
            for ov, ts in zip(overlap, tile_shape)
        )
        return tile_shape, overlap

    def _resolve_model_path(self, ndim: int) -> Path:
        """Resolve the ONNX file path for the active variant.

        Parameters
        ----------
        ndim : int
            Spatial dimensionality requested by the caller.

        Returns
        -------
        pathlib.Path
            Resolved ONNX file path.

        Raises
        ------
        ValueError
            If ``ndim`` does not match the variant.
            If multiple ONNX candidates are found without a canonical default.
        FileNotFoundError
            If no ONNX model can be located or downloaded.
        """
        if ndim != self._variant.expected_ndim:
            raise ValueError(
                f"StarDist ONNX {self._variant.expected_ndim}D expects a "
                f"{self._variant.expected_ndim}D model."
            )

        for relative in self._variant.model_relative_candidates:
            path = self.model_dir / relative
            if path.exists():
                return path

        try:
            downloaded = ensure_hf_model(
                self._variant.default_onnx_filename,
                self.model_dir / "onnx_models",
                repo_id=DEFAULT_REPO_ID,
            )
        except RuntimeError:
            downloaded = None
        if downloaded is not None and downloaded.exists():
            return downloaded

        matches: list[Path] = []
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

    def _resolve_io_names(
        self, session: ort.InferenceSession
    ) -> tuple[str, list[str]]:
        """Resolve ONNX input and probability/distance output tensor names.

        Parameters
        ----------
        session : onnxruntime.InferenceSession
            ONNX Runtime session from which to inspect model I/O metadata.

        Returns
        -------
        tuple
            ``(input_name, [prob_output_name, dist_output_name])``.

        Raises
        ------
        RuntimeError
            If required inputs/outputs are missing from the ONNX graph.
        """
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
            lower_name = output.name.lower()
            if "prob" in lower_name and prob is None:
                prob = output
            elif "dist" in lower_name and dist is None:
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
        """Ensure StarDist Python modules can import without compiled ops.

        Notes
        -----
        This method updates ``self._has_stardist_2d_lib`` and
        ``self._has_stardist_3d_lib`` to indicate whether compiled shared
        libraries were discovered.
        """
        utils_root = self._get_utils_root()
        stardist_pkg = "senoquant.tabs.segmentation.stardist_onnx_utils._stardist"
        has_2d, has_3d = ensure_stardist_libs(utils_root, stardist_pkg)
        self._has_stardist_2d_lib = has_2d
        self._has_stardist_3d_lib = has_3d

    def _get_rays_class(self):
        """Load and cache ``Rays_GoldenSpiral`` from StarDist vendored code.

        Returns
        -------
        type
            StarDist rays class used by 3D postprocessing.

        Raises
        ------
        FileNotFoundError
            If ``rays3d.py`` cannot be located.
        ImportError
            If the rays module cannot be loaded.
        """
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
        """Return the root directory of the ``stardist_onnx_utils`` package.

        Returns
        -------
        pathlib.Path
            Filesystem root containing vendored StarDist helpers.
        """
        return Path(__file__).resolve().parent

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
        """Infer StarDist grid/stride by probing ONNX output shape.

        Parameters
        ----------
        image : numpy.ndarray
            Input image used to construct a probe tile.
        session : onnxruntime.InferenceSession
            Session used to run the probe forward pass.
        input_name : str
            ONNX input tensor name.
        output_names : list of str
            ONNX output tensor names in probability/distance order.
        input_layout : str
            ONNX input layout string (for example ``"NHWC"``, ``"NDHWC"``).
        prob_layout : str
            Probability output layout string.
        model_path : pathlib.Path or None, optional
            Model path hint used by probe-image helper logic.

        Returns
        -------
        tuple of int
            Estimated per-axis stride/grid values.

        Raises
        ------
        ValueError
            If ``prob_layout`` is unsupported.
        """
        probe = self._make_probe_image(
            image,
            model_path=model_path,
            input_layout=input_layout,
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

        grid: list[int] = []
        for dim_in, dim_out in zip(probe.shape, out_shape):
            if dim_out in (0, None):
                grid.append(1)
                continue
            grid.append(max(1, int(round(dim_in / dim_out))))
        return tuple(grid)

    def _make_probe_image(
        self,
        image: np.ndarray,
        *,
        model_path: Path | None = None,
        input_layout: str | None = None,
    ) -> np.ndarray:
        """Build a probe image used for ONNX grid inference.

        Parameters
        ----------
        image : numpy.ndarray
            Reference input image.
        model_path : pathlib.Path or None, optional
            Optional model path hint used by inspection utilities.
        input_layout : str or None, optional
            Optional layout hint used when selecting probe shape.

        Returns
        -------
        numpy.ndarray
            Probe image with spatial shape compatible with the ONNX model.
        """
        return make_probe_image(
            image,
            model_path=model_path,
            input_layout=input_layout,
            div_by_cache=self._div_by_cache,
            valid_size_cache=self._valid_size_cache,
        )
