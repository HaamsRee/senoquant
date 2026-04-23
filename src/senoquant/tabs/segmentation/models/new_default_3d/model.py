"""TitanCell 3D segmentation model implementation."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import numpy as np

from senoquant.utils import layer_data_asarray
from ..base import SenoQuantSegmentationModel
from .TitanCellV18_3D import PipelineConfig, InferenceEngine, InstanceEngine


class TitanCellModel(SenoQuantSegmentationModel):
    """TitanCell 3D segmentation model wrapper.

    Dynamic auto-derivation flow:
      1. UI starts with manifest defaults (cell_diameter_px=100, sigma=12.0, etc.)
      2. User changes diameter to e.g. 60
      3. _build_config() compares each auto-derived field against its manifest
         default — if it matches, the user hasn't changed it, so we use the
         diameter-derived value instead.  If it differs, the user explicitly
         changed it, so we keep the user's value.
      4. Result: changing diameter dynamically updates all params, and user
         overrides are preserved.
    """

    _SUPPORTED_TASKS = {"nuclear"}

    def __init__(self, models_root=None) -> None:
        super().__init__("new_default_3d", models_root=models_root)

        model_path = Path(__file__).parent / "best_model_v18.pth"
        if not model_path.exists():
            raise FileNotFoundError(
                f"TitanCell model weights not found at {model_path}. "
                "Place best_model_v18.pth in the same directory as this file."
            )

        self._model_path = str(model_path)
        self._inference: InferenceEngine | None = None
        self._instance: InstanceEngine | None = None

    def supports_task(self, task: str) -> bool:
        return task in self._SUPPORTED_TASKS

    def display_order(self) -> float | None:
        return 10.0

    # ──────────────────────────────────────────────────────────────────────────
    # Run entry point
    # ──────────────────────────────────────────────────────────────────────────

    def run(self, **kwargs) -> dict[str, Any]:
        layer = kwargs.get("layer")
        settings = kwargs.get("settings", {})

        image = self._extract_layer_data(layer)
        config = self._build_config(settings)
        self._ensure_loaded(config)

        raw_outputs = self._inference.predict(image)
        seg_result = self._instance.process(raw_outputs)

        return {
            "masks": seg_result["instances"],
            "instances": seg_result["instances"],
            "mask": seg_result["mask"],
            "cell_info": seg_result["cell_info"],
            "statistics": seg_result["statistics"],
            "outputs": raw_outputs,
            "quality_map": seg_result.get("quality_map"),
            "intermediates": seg_result.get("intermediates", {}),
        }

    # ──────────────────────────────────────────────────────────────────────────
    # UI callback: auto-populate derived params when diameter changes
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def get_derived_params(cell_diameter_px: float) -> dict[str, Any]:
        """Compute all auto-derived parameters for a given cell diameter.

        Called by the UI when the user changes cell_diameter_px.
        Returns a dict of field_name -> value that the UI should use to
        auto-populate the corresponding input fields.

        The user can then tweak any field before hitting Run.

        Example UI integration (pseudo-code):
            def on_diameter_changed(new_diameter):
                derived = model.get_derived_params(new_diameter)
                for field, value in derived.items():
                    ui_field[field].set_value(value)

        Args:
            cell_diameter_px: Cell diameter in XY pixels (e.g. 60, 80, 100, 120).

        Returns:
            Dict mapping auto-derivable field names to their computed values.
            Also includes cell_diameter_px itself for convenience.
        """
        return PipelineConfig.derive_defaults(cell_diameter_px)

    # ──────────────────────────────────────────────────────────────────────────
    # Data extraction
    # ──────────────────────────────────────────────────────────────────────────

    def _extract_layer_data(self, layer) -> np.ndarray:
        if layer is None:
            raise ValueError("A valid image layer is required for TitanCell.")

        data = layer_data_asarray(layer)
        if data.ndim == 2:
            data = data[np.newaxis]
        if data.ndim != 3:
            raise ValueError(f"TitanCell expects a 3-D volume, got shape {data.shape}.")

        return data.astype(np.float32)

    # ──────────────────────────────────────────────────────────────────────────
    # Config builder: dynamic auto-derivation with manifest-default comparison
    # ──────────────────────────────────────────────────────────────────────────

    # Fields that are auto-derived from cell_diameter_px.
    _AUTO_DERIVED_FIELDS = frozenset({
        "center_smooth_sigma",
        "center_peak_threshold",
        "seed_min_dist_vox",
        "min_island_vox_fallback",
        "height_div_weight",
        "boundary_shell_depth",
        "watershed_downsample_xy",
        "shell_merge_depth",
        "shell_merge_max_dist_px",
        "high_mask_threshold",
        "min_high_mask_fraction",
        "min_cell_volume_vox",
        "sdf_interior_recovery",
        "sdf_sigma_px",
        "sdf_max_dist_px",
    })

    # Manifest default values — the values the UI starts with.
    # These come from manifest.json and represent d=100 derived values.
    # When an auto-derived field's UI value matches the manifest default,
    # we treat it as "user hasn't changed this" and use the derived value
    # for the current diameter instead.  When it differs, the user has
    # explicitly overridden it, so we keep the user's value.
    _MANIFEST_DEFAULTS: dict[str, Any] = {
        "cell_diameter_px":      100.0,
        "mask_threshold":        0.55,
        "mask_interior_mix":     0.02,
        "sdf_interior_recovery": -2.0,
        "center_smooth_sigma":   12.0,
        "center_peak_threshold": 0.014,
        "seed_min_dist_vox":     21.0,
        "min_island_vox_fallback": 1256,
        "height_center_weight":  2.0,
        "height_div_weight":     0.53,
        "boundary_shell_depth":  2.0,
        "watershed_downsample_xy": 2,
        "shell_merge_depth":     5.0,
        "shell_merge_max_dist_px": 20.0,
        "high_mask_threshold":   0.96,
        "min_high_mask_fraction": 0.05,
        "min_cell_volume_vox":   4188,
        "sdf_sigma_px":          1.5,
        "sdf_max_dist_px":       10.0,
    }

    # All scalar fields the UI may send (matches manifest.json settings keys)
    _SCALAR_FIELDS = (
        # Device / inference
        "device",
        "inference_batch_size",
        "use_torch_compile",
        # Master cell size
        "cell_diameter_px",
        # Binary mask (NOT auto-derived)
        "mask_threshold",
        "mask_interior_mix",
        # Seeding (auto-derived from cell_diameter_px)
        "center_smooth_sigma",
        "center_peak_threshold",
        "seed_min_dist_vox",
        "min_island_vox_fallback",
        # Watershed height map
        "height_center_weight",
        "height_div_weight",
        "watershed_compactness",
        "boundary_shell_depth",
        # Watershed speed
        "watershed_downsample_xy",
        # Shell merging
        "shell_merge_depth",
        "shell_merge_max_dist_px",
        # Post-filter quality gates
        "high_mask_threshold",
        "min_high_mask_fraction",
        # Misc
        "min_cell_volume_vox",
        "sdf_interior_recovery",
        "sdf_sigma_px",
        "sdf_max_dist_px",
        # Flags
        "verbose",
        "save_intermediates",
        "return_cell_info",
    )

    _TUPLE_FIELDS = (
        "patch_size",
        "overlap",
        "anisotropy",
    )

    @staticmethod
    def _values_match(a: Any, b: Any, tol: float = 1e-6) -> bool:
        """Check if two values are effectively equal (with float tolerance)."""
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return abs(float(a) - float(b)) < tol
        return a == b

    def _build_config(self, settings: dict) -> PipelineConfig:
        """Build PipelineConfig from UI settings with dynamic auto-derivation.

        PROBLEM: SenoQuant UI always passes ALL manifest default values in
        the ``settings`` dict, even for auto-derived fields.  If we blindly
        pass them through, the _UNSET sentinel is never triggered and
        _derive_from_diameter() skips every field — so changing the diameter
        has NO effect.

        SOLUTION — manifest-default comparison:
          For each auto-derived field, compare the incoming UI value against
          the manifest default (from manifest.json).  If they match, the user
          hasn't changed this field, so we SKIP it — it arrives as _UNSET in
          PipelineConfig and _derive_from_diameter() fills it with the correct
          diameter-dependent value.  If they differ, the user explicitly
          changed it, so we pass it through as an override.

        This makes the diameter parameter truly dynamic:
          - User changes diameter 100 → 60 → all params auto-update
          - User also changes sigma to 10.0 → sigma stays at 10.0 (override)
          - User changes sigma back to 12.0 → matches manifest default →
            sigma re-derives from the current diameter

        For standalone/script usage (no UI), PipelineConfig supports the
        _UNSET / _derive_from_diameter() mechanism directly:
            PipelineConfig(cell_diameter_px=70)              # auto-derives
            PipelineConfig(cell_diameter_px=70, hmf=0.10)   # auto-derives, hmf locked
        """
        kwargs: dict = {"model_path": self._model_path}

        diameter = settings.get("cell_diameter_px", 100.0)
        auto_derive = diameter is not None and diameter > 0

        for f in self._SCALAR_FIELDS:
            if f not in settings:
                continue

            if auto_derive and f in self._AUTO_DERIVED_FIELDS:
                # Compare against manifest default.
                # If it matches → user hasn't changed it → skip (let _UNSET
                # trigger, so _derive_from_diameter fills the correct value).
                # If it differs → user explicitly changed it → pass as override.
                manifest_val = self._MANIFEST_DEFAULTS.get(f)
                if manifest_val is not None and self._values_match(settings[f], manifest_val):
                    continue  # User hasn't changed this → use derived value

            kwargs[f] = settings[f]

        for f in self._TUPLE_FIELDS:
            if f in settings:
                kwargs[f] = tuple(settings[f])

        # Manual mode: cell_diameter_px=0 or None → no auto-derivation
        if not auto_derive:
            kwargs["cell_diameter_px"] = None

        return PipelineConfig(**kwargs)

    def _ensure_loaded(self, config: PipelineConfig) -> None:
        if self._inference is None:
            self._inference = InferenceEngine(config)
        else:
            self._inference.cfg = config

        self._instance = InstanceEngine(config)
