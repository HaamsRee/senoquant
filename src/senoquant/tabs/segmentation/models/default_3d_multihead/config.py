from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Tuple

import numpy as np

_DEFAULT_MODEL_PATH = str(Path(__file__).parent / "best_model_v18.pth")
DEFAULT_OBJECT_DIAMETER_PX = 100.0


def _derive_defaults_for_diameter(object_diameter_px: float) -> Dict[str, float | int]:
    d = float(object_diameter_px)
    r = d / 2.0
    min_cell_volume_vox = max(
        200,
        int((4.0 / 3.0) * math.pi * max(5.0, r * 0.20) ** 3),
    )
    return {
        "object_diameter_px": d,
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

    object_diameter_px: float = DEFAULT_OBJECT_DIAMETER_PX
    mask_threshold: float = 0.55
    high_mask_threshold: float = 0.92
    min_high_mask_fraction: float = 0.08

    height_center_weight: float = 2.0
    watershed_compactness: float = 0.0

    anisotropy: Tuple[float, float, float] = (1.8895, 1.0000, 1.0000)
    verbose: bool = True
    save_intermediates: bool = False
    return_cell_info: bool = False

    center_smooth_sigma: float = field(init=False)
    center_peak_threshold: float = field(init=False)
    seed_min_dist_vox: float = field(init=False)
    min_island_vox_fallback: int = field(init=False)
    height_div_weight: float = field(init=False)
    boundary_shell_depth: float = field(init=False)
    watershed_downsample_xy: int = field(init=False)
    shell_merge_depth: float = field(init=False)
    shell_merge_max_dist_px: float = field(init=False)
    min_cell_volume_vox: int = field(init=False)
    sdf_sigma_px: float = field(init=False)
    sdf_max_dist_px: float = field(init=False)

    def __post_init__(self) -> None:
        derived = _derive_defaults_for_diameter(self.object_diameter_px)
        self.center_smooth_sigma = float(derived["center_smooth_sigma"])
        self.center_peak_threshold = float(derived["center_peak_threshold"])
        self.seed_min_dist_vox = float(derived["seed_min_dist_vox"])
        self.min_island_vox_fallback = int(derived["min_island_vox_fallback"])
        self.height_div_weight = float(derived["height_div_weight"])
        self.boundary_shell_depth = float(derived["boundary_shell_depth"])
        self.watershed_downsample_xy = int(derived["watershed_downsample_xy"])
        self.shell_merge_depth = float(derived["shell_merge_depth"])
        self.shell_merge_max_dist_px = float(derived["shell_merge_max_dist_px"])
        self.min_cell_volume_vox = int(derived["min_cell_volume_vox"])
        self.sdf_sigma_px = float(derived["sdf_sigma_px"])
        self.sdf_max_dist_px = float(derived["sdf_max_dist_px"])

        if self.verbose:
            print(
                f"   [object_diameter={self.object_diameter_px:.1f}px] "
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
    def derive_defaults(object_diameter_px: float) -> Dict[str, float | int]:
        return _derive_defaults_for_diameter(object_diameter_px)


__all__ = ["PipelineConfig"]
