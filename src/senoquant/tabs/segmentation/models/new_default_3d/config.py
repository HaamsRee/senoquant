from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Set, Tuple

import numpy as np

_DEFAULT_MODEL_PATH = str(Path(__file__).parent / "best_model_v18.pth")
DEFAULT_CELL_DIAMETER_PX = 100.0


def _derive_defaults_for_diameter(cell_diameter_px: float) -> Dict[str, Any]:
    d = float(cell_diameter_px)
    r = d / 2.0
    min_cell_volume_vox = max(
        200,
        int((4.0 / 3.0) * math.pi * max(5.0, r * 0.20) ** 3),
    )
    return {
        "cell_diameter_px": d,
        "center_smooth_sigma": min(12.0, max(5.0, r / 3.0)),
        "center_peak_threshold": float(np.clip(0.004 + 0.00020 * r, 0.003, 0.015)),
        "seed_min_dist_vox": min(21.0, max(5.0, r * 0.55)),
        "min_island_vox_fallback": max(200, int(min_cell_volume_vox * 0.30)),
        "height_div_weight": float(np.clip(0.20 + 0.007 * r, 0.18, 0.900)),
        "boundary_shell_depth": float(np.clip(r * 0.04, 1.5, 4.0)),
        "watershed_downsample_xy": 2,
        "shell_merge_depth": float(np.clip(r * 0.10, 3.0, 12.0)),
        "shell_merge_max_dist_px": float(r * 0.40),
        "high_mask_threshold": 0.92,
        "min_high_mask_fraction": 0.08,
        "min_cell_volume_vox": min_cell_volume_vox,
        "sdf_sigma_px": max(0.5, d * 0.015),
        "sdf_max_dist_px": max(5.0, d * 0.10),
    }


@dataclass
class PipelineConfig:
    model_path: str = _DEFAULT_MODEL_PATH
    device: str = "cuda:0"

    patch_size: Tuple[int, int, int] = (64, 176, 176)
    overlap: Tuple[int, int, int] = (24, 24, 24)
    inference_batch_size: int = 4
    use_torch_compile: bool = False

    cell_diameter_px: Optional[float] = DEFAULT_CELL_DIAMETER_PX

    mask_threshold: float = 0.55

    center_smooth_sigma: Optional[float] = None
    center_peak_threshold: Optional[float] = None
    seed_min_dist_vox: Optional[float] = None
    min_island_vox_fallback: Optional[int] = None

    height_center_weight: float = 2.0
    height_div_weight: Optional[float] = None
    watershed_compactness: float = 0.0
    boundary_shell_depth: Optional[float] = None

    watershed_downsample_xy: Optional[int] = None

    shell_merge_depth: Optional[float] = None
    shell_merge_max_dist_px: Optional[float] = None

    high_mask_threshold: Optional[float] = None
    min_high_mask_fraction: Optional[float] = None

    min_cell_volume_vox: Optional[int] = None
    sdf_sigma_px: Optional[float] = None
    sdf_max_dist_px: Optional[float] = None

    anisotropy: Tuple[float, float, float] = (1.8895, 1.0000, 1.0000)
    verbose: bool = True
    save_intermediates: bool = False
    return_cell_info: bool = False

    _DEFAULTS: Dict[str, Any] = field(
        init=False,
        default_factory=lambda: {
            k: v
            for k, v in _derive_defaults_for_diameter(DEFAULT_CELL_DIAMETER_PX).items()
            if k != "cell_diameter_px"
        },
    )

    _AUTO_FIELDS: Tuple[str, ...] = field(
        init=False,
        default=(
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
            "sdf_sigma_px",
            "sdf_max_dist_px",
        ),
    )

    _auto_tuned_fields: Set[str] = field(init=False, default_factory=set)

    def __post_init__(self) -> None:
        self._auto_tuned_fields = {
            name for name in self._AUTO_FIELDS if getattr(self, name) is None
        }

        if self.cell_diameter_px is not None:
            self._derive_from_diameter(self.cell_diameter_px, force_auto=True)

        for name, default in self._DEFAULTS.items():
            if getattr(self, name) is None:
                setattr(self, name, default)

    def _is_unset(self, name: str) -> bool:
        return getattr(self, name) is None

    def _set_auto_or_unset(
        self, name: str, value: Any, force_auto: bool = False
    ) -> None:
        if self._is_unset(name):
            setattr(self, name, value)
            return
        if force_auto and name in self._auto_tuned_fields:
            setattr(self, name, value)

    def _derive_from_diameter(self, d: float, force_auto: bool = False) -> None:
        derived = _derive_defaults_for_diameter(d)
        d = float(derived["cell_diameter_px"])

        for name in self._AUTO_FIELDS:
            self._set_auto_or_unset(name, derived[name], force_auto)

        if self.verbose:
            print(
                f"   [cell_diameter={d:.1f}px] "
                f"sigma={self.center_smooth_sigma:.1f}px | "
                f"nms={self.seed_min_dist_vox:.1f}px | "
                f"peak_thr={self.center_peak_threshold:.4f} | "
                f"div_w={self.height_div_weight:.3f} | "
                f"center_w={self.height_center_weight:.1f} | "
                f"shell={self.boundary_shell_depth:.2f}px | "
                f"merge_dist={self.shell_merge_max_dist_px:.1f}px | "
                f"min_vol={self.min_cell_volume_vox}vox | "
                f"sdf_max={self.sdf_max_dist_px:.1f}px | "
                f"sdf_sigma={self.sdf_sigma_px:.2f}px | "
                f"high_mask={self.high_mask_threshold:.2f}>"
                f"{self.min_high_mask_fraction:.0%} | "
                f"ws_ds={self.watershed_downsample_xy}x",
                flush=True,
            )

    @staticmethod
    def derive_defaults(cell_diameter_px: float) -> Dict[str, Any]:
        return _derive_defaults_for_diameter(cell_diameter_px)


__all__ = ["PipelineConfig"]
