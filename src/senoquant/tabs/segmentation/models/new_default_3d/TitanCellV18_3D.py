from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np
import tifffile
from scipy.ndimage import (
    binary_dilation,
    binary_propagation,
    find_objects,
    generate_binary_structure,
    gaussian_filter,
    gaussian_filter1d,
    label as scipy_label,
    maximum_filter,
)
from scipy.spatial.distance import pdist
from skimage.measure import regionprops
from skimage.segmentation import watershed

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.amp import autocast

# ---------------------------------------------------------------------------
# Optional speedups
# ---------------------------------------------------------------------------
try:
    import cc3d
    _HAS_CC3D = True
except Exception:
    _HAS_CC3D = False

try:
    import cv2
    _HAS_CV2 = True
except Exception:
    _HAS_CV2 = False

_DEFAULT_MODEL_PATH = str(Path(__file__).parent / "best_model_v18.pth")
_UNSET = object()
_STRUCT6 = generate_binary_structure(3, 1)


# =============================================================================
# CONFIG
# =============================================================================

@dataclass
class PipelineConfig:
    model_path: str = _DEFAULT_MODEL_PATH
    device: str = "cuda:0"

    patch_size: Tuple[int, int, int] = (64, 176, 176)
    overlap: Tuple[int, int, int] = (24, 24, 24)
    inference_batch_size: int = 4
    use_torch_compile: bool = False

    cell_diameter_px: Optional[float] = 100.0

    mask_threshold: float = 0.55
    mask_interior_mix: float = 0.02

    center_smooth_sigma: float = _UNSET
    center_peak_threshold: float = _UNSET
    seed_min_dist_vox: float = _UNSET
    min_island_vox_fallback: int = _UNSET

    height_center_weight: float = 2.0
    height_div_weight: float = _UNSET
    watershed_compactness: float = 0.0
    boundary_shell_depth: float = _UNSET

    watershed_downsample_xy: int = _UNSET

    shell_merge_depth: float = _UNSET
    shell_merge_max_dist_px: float = _UNSET

    high_mask_threshold: float = _UNSET
    min_high_mask_fraction: float = _UNSET

    min_cell_volume_vox: int = _UNSET
    sdf_interior_recovery: float = _UNSET
    sdf_sigma_px: float = _UNSET
    sdf_max_dist_px: float = _UNSET

    anisotropy: Tuple[float, float, float] = (1.8895, 1.0000, 1.0000)
    verbose: bool = True
    save_intermediates: bool = False
    return_cell_info: bool = False

    _DEFAULTS: Dict[str, Any] = field(
        init=False,
        default_factory=lambda: dict(
            center_smooth_sigma=12.0,
            center_peak_threshold=0.013,
            seed_min_dist_vox=21.0,
            min_island_vox_fallback=1256,
            height_div_weight=0.53,
            boundary_shell_depth=2.0,
            watershed_downsample_xy=2,
            shell_merge_depth=5.0,
            shell_merge_max_dist_px=20.0,
            high_mask_threshold=0.92,
            min_high_mask_fraction=0.08,
            min_cell_volume_vox=4188,
            sdf_interior_recovery=-2.0,
            sdf_sigma_px=1.5,
            sdf_max_dist_px=10.0,
        ),
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
            "sdf_interior_recovery",
            "sdf_sigma_px",
            "sdf_max_dist_px",
        ),
    )

    _auto_tuned_fields: Set[str] = field(init=False, default_factory=set)

    def __post_init__(self) -> None:
        self._auto_tuned_fields = {
            name for name in self._AUTO_FIELDS
            if getattr(self, name) is _UNSET
        }

        if self.cell_diameter_px is not None:
            self._derive_from_diameter(self.cell_diameter_px, force_auto=True)

        for name, default in self._DEFAULTS.items():
            if getattr(self, name) is _UNSET:
                setattr(self, name, default)

    def _is_unset(self, name: str) -> bool:
        return getattr(self, name) is _UNSET

    def _set_auto_or_unset(self, name: str, value: Any, force_auto: bool = False) -> None:
        if self._is_unset(name):
            setattr(self, name, value)
            return
        if force_auto and name in self._auto_tuned_fields:
            setattr(self, name, value)

    def _derive_from_diameter(self, d: float, force_auto: bool = False) -> None:
        d = float(d)
        r = d / 2.0

        min_cell_volume_vox = max(
            200,
            int((4.0 / 3.0) * math.pi * max(5.0, r * 0.20) ** 3),
        )

        self._set_auto_or_unset("center_smooth_sigma", min(12.0, max(5.0, r / 3.0)), force_auto)
        self._set_auto_or_unset("seed_min_dist_vox", min(21.0, max(5.0, r * 0.55)), force_auto)
        self._set_auto_or_unset(
            "center_peak_threshold",
            float(np.clip(0.004 + 0.00020 * r, 0.003, 0.015)),
            force_auto,
        )
        self._set_auto_or_unset(
            "height_div_weight",
            float(np.clip(0.20 + 0.007 * r, 0.18, 0.900)),
            force_auto,
        )
        self._set_auto_or_unset(
            "boundary_shell_depth",
            float(np.clip(r * 0.04, 1.5, 4.0)),
            force_auto,
        )
        self._set_auto_or_unset("shell_merge_depth", float(np.clip(r * 0.10, 3.0, 12.0)), force_auto)
        self._set_auto_or_unset("shell_merge_max_dist_px", float(r * 0.40), force_auto)
        self._set_auto_or_unset("min_cell_volume_vox", int(min_cell_volume_vox), force_auto)
        self._set_auto_or_unset("sdf_max_dist_px", float(max(5.0, d * 0.10)), force_auto)
        self._set_auto_or_unset("sdf_sigma_px", float(max(0.5, d * 0.015)), force_auto)
        self._set_auto_or_unset("sdf_interior_recovery", float(-max(1.0, r * 0.04)), force_auto)
        self._set_auto_or_unset(
            "min_island_vox_fallback",
            int(max(200, int(min_cell_volume_vox * 0.30))),
            force_auto,
        )
        self._set_auto_or_unset("high_mask_threshold", 0.92, force_auto)
        self._set_auto_or_unset("min_high_mask_fraction", 0.08, force_auto)
        self._set_auto_or_unset("watershed_downsample_xy", 2, force_auto)

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
                f"high_mask={self.high_mask_threshold:.2f}>{self.min_high_mask_fraction:.0%} | "
                f"ws_ds={self.watershed_downsample_xy}x",
                flush=True,
            )

    @staticmethod
    def derive_defaults(cell_diameter_px: float) -> Dict[str, Any]:
        d = float(cell_diameter_px)
        r = d / 2.0
        min_cell_volume_vox = max(200, int((4.0 / 3.0) * math.pi * max(5.0, r * 0.20) ** 3))
        return {
            "cell_diameter_px": d,
            "center_smooth_sigma": min(12.0, max(5.0, r / 3.0)),
            "center_peak_threshold": float(np.clip(0.004 + 0.00020 * r, 0.003, 0.015)),
            "seed_min_dist_vox": min(21.0, max(5.0, r * 0.55)),
            "min_island_vox_fallback": max(200, int(min_cell_volume_vox * 0.30)),
            "height_div_weight": float(np.clip(0.2 + 0.007 * r, 0.2, 0.900)),
            "boundary_shell_depth": float(np.clip(r * 0.04, 1.5, 4.0)),
            "watershed_downsample_xy": 2,
            "shell_merge_depth": float(np.clip(r * 0.10, 3.0, 12.0)),
            "shell_merge_max_dist_px": float(r * 0.40),
            "high_mask_threshold": 0.92,
            "min_high_mask_fraction": 0.08,
            "min_cell_volume_vox": min_cell_volume_vox,
            "sdf_interior_recovery": -max(1.0, r * 0.04),
            "sdf_sigma_px": max(0.5, d * 0.015),
            "sdf_max_dist_px": max(5.0, d * 0.10),
        }


def make_config(cell_diameter_px: float = 100.0) -> PipelineConfig:
    return PipelineConfig(cell_diameter_px=cell_diameter_px)


def make_config_skin() -> PipelineConfig:
    return PipelineConfig(cell_diameter_px=60)


def make_config_lung() -> PipelineConfig:
    return PipelineConfig(cell_diameter_px=80)


def make_config_pancreas() -> PipelineConfig:
    return PipelineConfig(cell_diameter_px=100)


def make_config_liver() -> PipelineConfig:
    return PipelineConfig(cell_diameter_px=120)


def make_config_kidney() -> PipelineConfig:
    return PipelineConfig(cell_diameter_px=90)


def make_config_strict() -> PipelineConfig:
    cfg = PipelineConfig(cell_diameter_px=100)
    cfg.min_high_mask_fraction = 0.10
    cfg.high_mask_threshold = 0.97
    cfg.watershed_downsample_xy = 1
    cfg.verbose = True
    cfg._auto_tuned_fields.discard("min_high_mask_fraction")
    cfg._auto_tuned_fields.discard("high_mask_threshold")
    cfg._auto_tuned_fields.discard("watershed_downsample_xy")
    return cfg


TISSUE_PRESETS = {
    "skin": dict(cell_diameter_px=60),
    "lung": dict(cell_diameter_px=80),
    "pancreas": dict(cell_diameter_px=100),
    "liver": dict(cell_diameter_px=120),
    "kidney": dict(cell_diameter_px=90),
}


# =============================================================================
# MODEL
# =============================================================================

def _safe_num_groups(dim: int, preferred: int = 8) -> int:
    for g in range(preferred, 0, -1):
        if dim % g == 0:
            return g
    return 1


class SeparableConvNeXtBlock3D(nn.Module):
    def __init__(self, dim: int, kz: int = 3, kxy: int = 7):
        super().__init__()
        pz, pxy = kz // 2, kxy // 2
        self.dwconv_z = nn.Conv3d(dim, dim, (kz, 1, 1), padding=(pz, 0, 0), groups=dim)
        self.dwconv_xy = nn.Conv3d(dim, dim, (1, kxy, kxy), padding=(0, pxy, pxy), groups=dim)
        self.norm = nn.GroupNorm(_safe_num_groups(dim), dim)
        self.pwconv1 = nn.Conv3d(dim, 4 * dim, 1)
        self.act = nn.GELU()
        self.pwconv2 = nn.Conv3d(4 * dim, dim, 1)

    def forward(self, x):
        h = self.dwconv_xy(self.dwconv_z(x))
        return x + self.pwconv2(self.act(self.pwconv1(self.norm(h))))


class AttentionGate3D(nn.Module):
    def __init__(self, Fg: int, Fl: int, Fint: int):
        super().__init__()
        self.Wg = nn.Sequential(nn.Conv3d(Fg, Fint, 1), nn.GroupNorm(_safe_num_groups(Fint), Fint))
        self.Wx = nn.Sequential(nn.Conv3d(Fl, Fint, 1), nn.GroupNorm(_safe_num_groups(Fint), Fint))
        self.psi = nn.Sequential(nn.Conv3d(Fint, 1, 1), nn.GroupNorm(1, 1), nn.Sigmoid())
        self.relu = nn.ReLU(inplace=True)

    def forward(self, g, x):
        g1 = F.interpolate(self.Wg(g), size=x.shape[2:], mode="trilinear", align_corners=False)
        return x * self.psi(self.relu(g1 + self.Wx(x)))


class TitanCellV18_3D(nn.Module):
    DIMS = (64, 128, 256, 512)

    def __init__(self, anisotropy=(1.0, 1.0, 1.0)):
        super().__init__()
        D = self.DIMS
        self.stem = nn.Sequential(
            nn.Conv3d(4, D[0], 3, padding=1),
            nn.GroupNorm(_safe_num_groups(D[0]), D[0]),
            nn.GELU(),
        )
        self.enc1 = SeparableConvNeXtBlock3D(D[0])
        self.dwn1 = nn.Conv3d(D[0], D[1], 2, stride=2)
        self.enc2 = SeparableConvNeXtBlock3D(D[1])
        self.dwn2 = nn.Conv3d(D[1], D[2], 2, stride=2)
        self.enc3 = SeparableConvNeXtBlock3D(D[2])
        self.dwn3 = nn.Conv3d(D[2], D[3], 2, stride=2)
        self.brdg = nn.Sequential(SeparableConvNeXtBlock3D(D[3]), SeparableConvNeXtBlock3D(D[3]))
        self.up3 = nn.ConvTranspose3d(D[3], D[2], 2, stride=2)
        self.ag3 = AttentionGate3D(D[2], D[2], D[2] // 2)
        self.dec3 = SeparableConvNeXtBlock3D(D[2])
        self.up2 = nn.ConvTranspose3d(D[2], D[1], 2, stride=2)
        self.ag2 = AttentionGate3D(D[1], D[1], D[1] // 2)
        self.dec2 = SeparableConvNeXtBlock3D(D[1])
        self.up1 = nn.ConvTranspose3d(D[1], D[0], 2, stride=2)
        self.ag1 = AttentionGate3D(D[0], D[0], D[0] // 2)
        self.dec1 = SeparableConvNeXtBlock3D(D[0])

        self.head_mask = nn.Conv3d(D[0], 1, 1)
        self.head_center = nn.Sequential(
            nn.Conv3d(D[0], 32, 3, padding=1),
            nn.GroupNorm(_safe_num_groups(32), 32),
            nn.GELU(),
            nn.Conv3d(32, 1, 1),
        )
        self.head_vector = nn.Conv3d(D[0], 3, 1)
        self.head_sdf = nn.Conv3d(D[0], 1, 1)
        self.ds1_head = nn.Conv3d(D[0], 1, 1)
        self.ds2_head = nn.Conv3d(D[1], 1, 1)

        self._coord_cache: Dict[
            Tuple[int, int, int, torch.device, torch.dtype],
            Tuple[torch.Tensor, torch.Tensor, torch.Tensor],
        ] = {}

    @staticmethod
    def _match(x, t):
        dz = max(0, t.shape[2] - x.shape[2])
        dy = max(0, t.shape[3] - x.shape[3])
        dx = max(0, t.shape[4] - x.shape[4])
        if dz or dy or dx:
            x = F.pad(x, (0, dx, 0, dy, 0, dz))
        return x[..., :t.shape[2], :t.shape[3], :t.shape[4]]

    def _coords(self, shape: Tuple[int, int, int], device: torch.device, dtype: torch.dtype):
        key = (shape[0], shape[1], shape[2], device, dtype)
        cached = self._coord_cache.get(key)
        if cached is None:
            Z, Y, X = shape
            zc = torch.linspace(-1, 1, Z, device=device, dtype=dtype).view(1, 1, Z, 1, 1)
            yc = torch.linspace(-1, 1, Y, device=device, dtype=dtype).view(1, 1, 1, Y, 1)
            xc = torch.linspace(-1, 1, X, device=device, dtype=dtype).view(1, 1, 1, 1, X)
            cached = (zc, yc, xc)
            self._coord_cache[key] = cached
        return cached

    def _add_coords(self, x):
        B, _, Z, Y, X = x.shape
        zc, yc, xc = self._coords((Z, Y, X), x.device, x.dtype)
        return torch.cat(
            [
                x,
                zc.expand(B, 1, Z, Y, X),
                yc.expand(B, 1, Z, Y, X),
                xc.expand(B, 1, Z, Y, X),
            ],
            dim=1,
        )

    def forward(self, x):
        x = self._add_coords(x)
        s1 = self.enc1(self.stem(x))
        s2 = self.enc2(self.dwn1(s1))
        s3 = self.enc3(self.dwn2(s2))
        b = self.brdg(self.dwn3(s3))

        u3 = self._match(self.up3(b), s3)
        d3 = self.dec3(u3 + self.ag3(u3, s3))
        u2 = self._match(self.up2(d3), s2)
        d2 = self.dec2(u2 + self.ag2(u2, s2))
        u1 = self._match(self.up1(d2), s1)
        d1 = self.dec1(u1 + self.ag1(u1, s1))

        mask_logit = self.head_mask(d1)
        mask_gate = torch.sigmoid(mask_logit).detach()
        sdf_pred = self.head_sdf(d1) * (mask_gate + 0.1).clamp(max=1.0)

        return (
            mask_logit,
            torch.sigmoid(self.head_center(d1)),
            self.head_vector(d1),
            sdf_pred,
        ), (self.ds1_head(d1), self.ds2_head(d2))


# =============================================================================
# INFERENCE
# =============================================================================

class InferenceEngine:
    def __init__(self, cfg: PipelineConfig):
        self.cfg = cfg
        self.device = torch.device(cfg.device if torch.cuda.is_available() else "cpu")
        self.use_amp = self.device.type == "cuda"
        if self.device.type == "cuda":
            torch.backends.cudnn.benchmark = True

        self.model = None
        self._blend_cache: Dict[Tuple[int, int, int], np.ndarray] = {}
        self._patch_meta_cache: Dict[
            Tuple[int, int, int],
            List[
                Tuple[
                    int, int, int, int, int, int,
                    Tuple[int, int, int],
                    Tuple[Tuple[int, int], Tuple[int, int], Tuple[int, int]]
                ]
            ],
        ] = {}

        self._load_model()

    def _log(self, x: str):
        if self.cfg.verbose:
            print(x, flush=True)

    def _load_model(self):
        self._log(f"   Loading model from {self.cfg.model_path}")
        ckpt = torch.load(self.cfg.model_path, map_location="cpu", weights_only=False)

        if "anisotropy" in ckpt:
            self.cfg.anisotropy = tuple(ckpt["anisotropy"])

        model_sdf_sigma_px = None
        model_sdf_max_dist_px = None

        if "sdf_config" in ckpt:
            sc = ckpt["sdf_config"]
            pxy = float(self.cfg.anisotropy[2])

            if "sigma_px" in sc:
                model_sdf_sigma_px = float(sc["sigma_px"])
            elif "sigma_um" in sc:
                model_sdf_sigma_px = float(sc["sigma_um"]) / pxy

            if "max_dist_px" in sc:
                model_sdf_max_dist_px = float(sc["max_dist_px"])
            elif "max_dist_um" in sc:
                model_sdf_max_dist_px = float(sc["max_dist_um"]) / pxy

        if self.cfg.cell_diameter_px is not None:
            self.cfg._derive_from_diameter(self.cfg.cell_diameter_px, force_auto=True)
        else:
            if model_sdf_sigma_px is not None and "sdf_sigma_px" in self.cfg._auto_tuned_fields:
                self.cfg.sdf_sigma_px = model_sdf_sigma_px
            if model_sdf_max_dist_px is not None and "sdf_max_dist_px" in self.cfg._auto_tuned_fields:
                self.cfg.sdf_max_dist_px = model_sdf_max_dist_px

        self.model = TitanCellV18_3D(self.cfg.anisotropy)

        if "model_state_dict" in ckpt:
            sd = ckpt["model_state_dict"]
            if any(k.startswith("shadow.") for k in sd):
                sd = {k.replace("shadow.", ""): v for k, v in sd.items() if k.startswith("shadow.")}
            self.model.load_state_dict(sd, strict=False)

        self.model = self.model.to(self.device).eval()

        if self.cfg.use_torch_compile and self.device.type == "cuda" and hasattr(torch, "compile"):
            try:
                self._log("   Compiling model...")
                self.model = torch.compile(self.model, mode="max-autotune")
            except Exception:
                self._log("   torch.compile unavailable, continuing.")

        with torch.inference_mode():
            dummy = torch.zeros(1, 1, 32, 64, 64, device=self.device)
            with autocast("cuda", dtype=torch.float16, enabled=self.use_amp):
                _ = self.model(dummy)

        self._log("   Model loaded")

    @staticmethod
    def _normalize(vol: np.ndarray) -> np.ndarray:
        vol = np.asarray(vol, dtype=np.float32, order="C")
        vmin = np.percentile(vol, 1.0)
        vmax = np.percentile(vol, 99.8)
        return np.clip((vol - vmin) / (vmax - vmin + 1e-20), 0, 1).astype(np.float32, copy=False)

    def _predict_tensor(self, x: torch.Tensor) -> Dict[str, np.ndarray]:
        with torch.inference_mode():
            with autocast("cuda", dtype=torch.float16, enabled=self.use_amp):
                (mask_l, center, vectors, sdf_raw), _ = self.model(x)
        return {
            "mask": torch.sigmoid(mask_l.float()).cpu().numpy()[:, 0],
            "center": center.float().cpu().numpy()[:, 0],
            "vectors": vectors.float().cpu().numpy(),
            "sdf": (
                torch.tanh(sdf_raw.float() / self.cfg.sdf_max_dist_px) * self.cfg.sdf_max_dist_px
            ).cpu().numpy()[:, 0],
        }

    def predict(self, volume: np.ndarray) -> Dict[str, np.ndarray]:
        vol = self._normalize(volume)
        if all(vol.shape[i] <= self.cfg.patch_size[i] for i in range(3)):
            return self._predict_single(vol)
        return self._predict_tiled(vol)

    def _predict_single(self, vol: np.ndarray) -> Dict[str, np.ndarray]:
        orig = vol.shape
        min_size = (32, 64, 64)
        pad = [
            (
                max(0, min_size[i] - orig[i]) // 2,
                max(0, min_size[i] - orig[i]) - max(0, min_size[i] - orig[i]) // 2,
            )
            for i in range(3)
        ]
        if any(p[0] or p[1] for p in pad):
            vol = np.pad(vol, pad, mode="reflect")

        x = torch.from_numpy(vol[None, None]).to(self.device, non_blocking=True)
        out = self._predict_tensor(x)

        sl = tuple(slice(pad[i][0], pad[i][0] + orig[i]) for i in range(3))
        result = {
            "mask": out["mask"][0][sl].astype(np.float32, copy=False),
            "center": out["center"][0][sl].astype(np.float32, copy=False),
            "vectors": out["vectors"][0][(slice(None),) + sl].astype(np.float32, copy=False),
            "sdf": out["sdf"][0][sl].astype(np.float32, copy=False),
        }
        result["boundary"] = np.exp(-np.abs(result["sdf"]) / self.cfg.sdf_sigma_px).astype(np.float32)
        return result

    def _make_coords(self, shape: Tuple[int, int, int]) -> List[Tuple[int, int, int]]:
        ps, ov = self.cfg.patch_size, self.cfg.overlap
        strides = tuple(max(1, ps[i] - ov[i]) for i in range(3))
        coords_dim: List[List[int]] = []

        for i in range(3):
            if shape[i] <= ps[i]:
                coords_dim.append([0])
                continue
            c = list(range(0, shape[i] - ps[i] + 1, strides[i]))
            if c[-1] != shape[i] - ps[i]:
                c.append(shape[i] - ps[i])
            coords_dim.append(c)

        return [(z, y, x) for z in coords_dim[0] for y in coords_dim[1] for x in coords_dim[2]]

    def _blend_weight(self, shape: Tuple[int, int, int]) -> np.ndarray:
        cached = self._blend_cache.get(shape)
        if cached is not None:
            return cached

        ov = self.cfg.overlap
        w = np.ones(shape, np.float32)
        for dim in range(3):
            od = ov[dim]
            if od <= 0 or shape[dim] <= od:
                continue
            ramp = 0.5 - 0.5 * np.cos(np.pi * np.linspace(0, 1, od, dtype=np.float32))
            line = np.ones(shape[dim], np.float32)
            line[:od] = ramp
            line[-od:] = ramp[::-1]
            if dim == 0:
                w *= line[:, None, None]
            elif dim == 1:
                w *= line[None, :, None]
            else:
                w *= line[None, None, :]

        self._blend_cache[shape] = w
        return w

    def _patch_meta(self, shape: Tuple[int, int, int]):
        cached = self._patch_meta_cache.get(shape)
        if cached is not None:
            return cached

        ps = self.cfg.patch_size
        metas = []
        for sz, sy, sx in self._make_coords(shape):
            ez, ey, ex = min(sz + ps[0], shape[0]), min(sy + ps[1], shape[1]), min(sx + ps[2], shape[2])
            orig_shape = (ez - sz, ey - sy, ex - sx)
            pad = tuple(
                (
                    max(0, ps[i] - orig_shape[i]) // 2,
                    max(0, ps[i] - orig_shape[i]) - max(0, ps[i] - orig_shape[i]) // 2,
                )
                for i in range(3)
            )
            metas.append((sz, sy, sx, ez, ey, ex, orig_shape, pad))

        self._patch_meta_cache[shape] = metas
        return metas

    def _predict_tiled(self, vol: np.ndarray) -> Dict[str, np.ndarray]:
        shape = vol.shape
        ps = self.cfg.patch_size
        metas = self._patch_meta(shape)
        total = len(metas)
        bs = max(1, int(self.cfg.inference_batch_size))
        self._log(f"   Patch inference: {shape} -> {total} patches, batch={bs}")

        acc = {k: np.zeros(shape, np.float32) for k in ("mask", "center", "sdf")}
        acc_vectors = np.zeros((3,) + shape, np.float32)
        acc_weight = np.zeros(shape, np.float32)
        batch_np = np.empty((bs, 1, ps[0], ps[1], ps[2]), np.float32)

        t0 = time.time()
        report_every = max(1, total // 10)

        for start in range(0, total, bs):
            batch_metas = metas[start:start + bs]
            n_batch = len(batch_metas)

            for b, (sz, sy, sx, ez, ey, ex, orig_shape, pad) in enumerate(batch_metas):
                patch = vol[sz:ez, sy:ey, sx:ex]
                if any(p[0] or p[1] for p in pad):
                    patch = np.pad(patch, pad, mode="reflect")
                batch_np[b, 0] = patch

            x = torch.from_numpy(batch_np[:n_batch]).to(self.device, non_blocking=True)
            out = self._predict_tensor(x)

            for b, (sz, sy, sx, ez, ey, ex, orig_shape, pad) in enumerate(batch_metas):
                sl = tuple(slice(pad[i][0], pad[i][0] + orig_shape[i]) for i in range(3))
                wf = self._blend_weight(orig_shape)
                for k in ("mask", "center", "sdf"):
                    acc[k][sz:ez, sy:ey, sx:ex] += out[k][b][sl] * wf
                acc_vectors[:, sz:ez, sy:ey, sx:ex] += out["vectors"][b][(slice(None),) + sl] * wf
                acc_weight[sz:ez, sy:ey, sx:ex] += wf

            done = min(start + bs, total)
            if self.cfg.verbose and (done % report_every == 0 or done == total):
                dt = time.time() - t0
                eta = dt / max(1, done) * (total - done)
                self._log(f"   Progress: {done}/{total}, ETA: {eta:.0f}s")

        valid = acc_weight > 0
        inv_w = np.zeros_like(acc_weight, dtype=np.float32)
        inv_w[valid] = 1.0 / acc_weight[valid]

        for k in ("mask", "center", "sdf"):
            acc[k] *= inv_w
        acc_vectors *= inv_w[None, ...]

        result = {k: acc[k].astype(np.float32, copy=False) for k in ("mask", "center", "sdf")}
        result["vectors"] = acc_vectors.astype(np.float32, copy=False)
        result["boundary"] = np.exp(-np.abs(result["sdf"]) / self.cfg.sdf_sigma_px).astype(np.float32)

        self._log(f"   Inference: {time.time() - t0:.1f}s")
        return result


# =============================================================================
# UTILITIES  —  optimized helpers
# =============================================================================

def _build_seed_vol(coords: np.ndarray, shape: Tuple[int, ...]) -> Tuple[np.ndarray, int]:
    seed_vol = np.zeros(shape, dtype=np.int32)
    n = len(coords)
    if n > 0:
        seed_vol[coords[:, 0], coords[:, 1], coords[:, 2]] = np.arange(1, n + 1, dtype=np.int32)
    return seed_vol, n


def _flow_divergence(vectors: np.ndarray, anisotropy: Tuple[float, float, float]) -> np.ndarray:
    inv_2az = 0.5 / anisotropy[0]
    inv_2ay = 0.5 / anisotropy[1]
    inv_2ax = 0.5 / anisotropy[2]

    Vz, Vy, Vx = vectors[0], vectors[1], vectors[2]
    div = np.zeros(Vz.shape, np.float32)
    div[1:-1, :, :] += (Vz[2:, :, :] - Vz[:-2, :, :]) * inv_2az
    div[:, 1:-1, :] += (Vy[:, 2:, :] - Vy[:, :-2, :]) * inv_2ay
    div[:, :, 1:-1] += (Vx[:, :, 2:] - Vx[:, :, :-2]) * inv_2ax

    d_min = float(div.min())
    d_max = float(div.max())
    d_range = d_max - d_min
    if d_range > 1e-8:
        div = (div - d_min) / d_range * 2.0 - 1.0
    return div


def _fast_bbox(mask: np.ndarray) -> Tuple[int, int, int, int, int, int]:
    z_any = np.any(mask, axis=(1, 2))
    y_any = np.any(mask, axis=(0, 2))
    x_any = np.any(mask, axis=(0, 1))
    z0 = int(np.argmax(z_any))
    z1 = len(z_any) - int(np.argmax(z_any[::-1]))
    y0 = int(np.argmax(y_any))
    y1 = len(y_any) - int(np.argmax(y_any[::-1]))
    x0 = int(np.argmax(x_any))
    x1 = len(x_any) - int(np.argmax(x_any[::-1]))
    return z0, y0, x0, z1, y1, x1


def _compact_relabel(instances: np.ndarray) -> np.ndarray:
    max_lbl = int(instances.max())
    if max_lbl <= 0:
        return instances.astype(np.uint32, copy=False)

    counts = np.bincount(instances.ravel(), minlength=max_lbl + 1)
    active = np.flatnonzero(counts)
    if len(active) <= 1:
        return instances.astype(np.uint32, copy=False)

    cmap = np.zeros(max_lbl + 1, dtype=np.uint32)
    cmap[active] = np.arange(len(active), dtype=np.uint32)
    return cmap[instances]


def _expand_slice(sl, shape, pad=1):
    return tuple(
        slice(max(0, s.start - pad), min(shape[i], s.stop + pad))
        for i, s in enumerate(sl)
    )


# ---------------------------------------------------------------------------
# FAST 3D LABELING  (cc3d >> scipy)
# ---------------------------------------------------------------------------
def _label3d(arr: np.ndarray):
    """Connected components. Uses cc3d if available, else scipy."""
    if _HAS_CC3D:
        # cc3d expects uint32/uint64/bool input
        labels = cc3d.connected_components(arr.astype(np.uint32, copy=False), connectivity=6)
        return labels, int(labels.max())
    return scipy_label(arr, _STRUCT6)


# ---------------------------------------------------------------------------
# FAST 3D GAUSSIAN  (OpenCV IIR for XY, scipy for Z)
# ---------------------------------------------------------------------------
def _gaussian_smooth_3d(vol: np.ndarray, sigma: Tuple[float, float, float], truncate: float = 3.0):
    """
    Optimized separable Gaussian.
    For large XY sigma, uses OpenCV's O(1) IIR Gaussian per Z-slice.
    Falls back to scipy.gaussian_filter if OpenCV unavailable.
    """
    sz, sy, sx = sigma
    if not _HAS_CV2 or (sy <= 2.0 and sx <= 2.0):
        # Small sigma: scipy FIR is fine
        return gaussian_filter(vol, sigma=sigma, truncate=truncate)

    # OpenCV path: fast XY smoothing slice-by-slice, then scipy for Z
    out = vol.copy()
    ksize = 0  # auto from sigma
    # OpenCV BORDER_REFLECT_101 matches scipy 'reflect' (edge not repeated)
    border = cv2.BORDER_REFLECT_101

    if sy > 0 and sx > 0:
        for z in range(out.shape[0]):
            # GaussianBlur is ~10× faster than scipy FIR for sigma > 4
            out[z] = cv2.GaussianBlur(out[z], (ksize, ksize), sigmaX=sx, sigmaY=sy, borderType=border)

    if sz > 0:
        out = gaussian_filter1d(out, sigma=sz, axis=0, truncate=truncate)
    return out


# ---------------------------------------------------------------------------
# VECTORIZED HOLE FILL  (avoids 600+ binary_dilation calls)
# ---------------------------------------------------------------------------
def _fill_enclosed_instance_holes(instances: np.ndarray) -> Tuple[np.ndarray, int, int]:
    max_lbl = int(instances.max())
    if max_lbl <= 0:
        return instances.astype(np.uint32, copy=False), 0, 0

    bg = (instances == 0)
    if not np.any(bg):
        return instances.astype(np.uint32, copy=False), 0, 0

    border = np.zeros_like(bg, dtype=bool)
    border[0, :, :] = bg[0, :, :]
    border[-1, :, :] = bg[-1, :, :]
    border[:, 0, :] = bg[:, 0, :]
    border[:, -1, :] = bg[:, -1, :]
    border[:, :, 0] = bg[:, :, 0]
    border[:, :, -1] = bg[:, :, -1]

    exterior = binary_propagation(border, structure=_STRUCT6, mask=bg)
    holes = bg & ~exterior
    if not np.any(holes):
        return instances.astype(np.uint32, copy=False), 0, 0

    hole_id, n_holes = _label3d(holes)   # keeps cc3d if available
    sl_list = find_objects(hole_id)

    out = instances.copy()
    n_filled_vox = 0
    n_filled_holes = 0
    shape = instances.shape

    for hid, sl in enumerate(sl_list, start=1):
        if sl is None:
            continue
        slp = _expand_slice(sl, shape, pad=1)
        crop_h = (hole_id[slp] == hid)
        if not np.any(crop_h):
            continue
        ring = binary_dilation(crop_h, structure=_STRUCT6) & (~crop_h)
        adj = out[slp][ring]
        adj = adj[adj > 0]
        if adj.size == 0:
            continue
        lbl = int(adj[0])
        if np.all(adj == lbl):
            out_view = out[slp]
            out_view[crop_h] = lbl
            n_filled_vox += int(crop_h.sum())
            n_filled_holes += 1

    return out.astype(np.uint32, copy=False), n_filled_vox, n_filled_holes


# =============================================================================
# INSTANCE ENGINE
# =============================================================================

class InstanceEngine:
    def __init__(self, cfg: PipelineConfig):
        self.cfg = cfg

    def _log(self, x: str):
        if self.cfg.verbose:
            print(x, flush=True)

    @staticmethod
    def _odd(n: int) -> int:
        return n if n % 2 == 1 else n + 1

    def _aniso_nms_footprint(self) -> Tuple[int, int, int]:
        az, ay, ax = self.cfg.anisotropy
        d = self.cfg.seed_min_dist_vox
        return (
            self._odd(max(3, int(round(d / az)))),
            self._odd(max(3, int(round(d / ay)))),
            self._odd(max(3, int(round(d / ax)))),
        )

    def _make_binary(self, mask_prob: np.ndarray, sdf: Optional[np.ndarray]) -> np.ndarray:
        if sdf is not None:
            noise_floor = 0.15
            binary = (sdf < 0) & (mask_prob > noise_floor)
            dilated = binary_dilation(binary, structure=_STRUCT6, iterations=2)
            binary = dilated & (sdf < 1.5) & (mask_prob > noise_floor)
            self._log(
                f"   SDF-guided binary: {int(binary.sum()):,} fg voxels "
                f"(sdf<0 dilated×2 to sdf<1.5, mask>{noise_floor:.2f})"
            )
        else:
            binary = mask_prob > self.cfg.mask_threshold
        return binary

    def _merge_shell_artefacts(
        self,
        tier1_coords: np.ndarray,
        center_sm: np.ndarray,
        sdf: np.ndarray,
        binary: np.ndarray,
    ) -> np.ndarray:
        keep_mask = np.ones(len(tier1_coords), dtype=bool)
        if len(tier1_coords) == 0:
            return keep_mask

        interior_zone = (sdf < -self.cfg.shell_merge_depth) & binary
        labeled_int, n_int = _label3d(interior_zone)
        if n_int == 0:
            return keep_mask

        tc = tier1_coords
        comp_ids = labeled_int[tc[:, 0], tc[:, 1], tc[:, 2]]
        interior_idx = np.flatnonzero(comp_ids > 0)
        if len(interior_idx) == 0:
            return keep_mask

        scores = center_sm[tc[:, 0], tc[:, 1], tc[:, 2]]
        scale = np.asarray(self.cfg.anisotropy, dtype=np.float32)
        coords_phys = tc.astype(np.float32) * scale[None, :]

        order = np.argsort(comp_ids[interior_idx], kind="mergesort")
        idx_sorted = interior_idx[order]
        comp_sorted = comp_ids[idx_sorted]

        starts = np.flatnonzero(np.r_[True, comp_sorted[1:] != comp_sorted[:-1]])
        ends = np.r_[starts[1:], len(comp_sorted)]

        max_dist_thresh = float(self.cfg.shell_merge_max_dist_px)
        thresh2 = max_dist_thresh * max_dist_thresh

        auto_merge_diag = 0.70 * max_dist_thresh
        auto_reject_diag = 1.15 * max_dist_thresh
        auto_merge_diag2 = auto_merge_diag * auto_merge_diag
        auto_reject_diag2 = auto_reject_diag * auto_reject_diag

        for s, e in zip(starts, ends):
            grp = idx_sorted[s:e]
            if len(grp) <= 1:
                continue

            pts = coords_phys[grp]
            mins = pts.min(axis=0)
            maxs = pts.max(axis=0)
            span = maxs - mins

            if float(span.max()) > 2.0 * max_dist_thresh:
                continue

            diag2 = float(np.dot(span, span))

            if diag2 <= auto_merge_diag2:
                best = grp[np.argmax(scores[grp])]
                keep_mask[grp] = False
                keep_mask[best] = True
                continue

            if diag2 > auto_reject_diag2:
                continue

            n_pts = len(grp)
            if n_pts <= 10:
                diffs = pts[:, None, :] - pts[None, :, :]
                max_dist2 = float(np.sum(diffs * diffs, axis=-1).max())
            else:
                max_dist2 = float(pdist(pts, metric="sqeuclidean").max())

            if max_dist2 > thresh2:
                continue

            best = grp[np.argmax(scores[grp])]
            keep_mask[grp] = False
            keep_mask[best] = True

        return keep_mask

    def _find_center_seeds(
        self,
        center: np.ndarray,
        sdf: Optional[np.ndarray],
        binary: np.ndarray,
        mask_prob: Optional[np.ndarray] = None,
    ) -> Tuple[np.ndarray, int, np.ndarray]:
        az, ay, ax = self.cfg.anisotropy

        # OPTIMIZED: OpenCV IIR Gaussian for large XY sigma
        center_sm = _gaussian_smooth_3d(
            center.astype(np.float32, copy=False),
            sigma=(
                self.cfg.center_smooth_sigma / az,
                self.cfg.center_smooth_sigma / ay,
                self.cfg.center_smooth_sigma / ax,
            ),
            truncate=3.0,
        )

        fz, fy, fx = self._aniso_nms_footprint()
        self._log(
            f"   NMS footprint: ({fz},{fy},{fx}) vox <- {self.cfg.seed_min_dist_vox:.1f}px / "
            f"aniso({az:.2f},{ay:.2f},{ax:.2f})"
        )

        local_max = maximum_filter(center_sm, size=(fz, fy, fx))
        tier1_peak_mask = (center_sm == local_max) & (center_sm >= self.cfg.center_peak_threshold) & binary
        tier1_coords = np.argwhere(tier1_peak_mask)

        fg_vals = center_sm[binary]
        fg_min = float(fg_vals.min()) if fg_vals.size else 0.0
        fg_max = float(fg_vals.max()) if fg_vals.size else 0.0
        self._log(f"   Tier-1 seeds: {len(tier1_coords)} | center fg range: [{fg_min:.3f}, {fg_max:.3f}]")

        if sdf is not None and len(tier1_coords) > 0:
            keep_mask = self._merge_shell_artefacts(tier1_coords, center_sm, sdf, binary)
            n_removed = int((~keep_mask).sum())
            if n_removed > 0:
                tier1_coords = tier1_coords[keep_mask]
                self._log(f"   Shell merging: {n_removed} artefact peaks removed -> {len(tier1_coords)} Tier-1 seeds")

        seed_vol, seed_count = _build_seed_vol(tier1_coords, binary.shape)

        # FAST TIER-2: loop over candidates only (already optimal structure)
        if sdf is not None and seed_count > 0:
            interior = (sdf < -0.5) & binary
            labeled_bg, n_islands = _label3d(interior)  # cc3d: 5-10× faster
            self._log(f"   Tier-2 gap-fill: {n_islands} sdf<-0.5 islands")

            if n_islands > 0:
                comp_size = np.bincount(labeled_bg.ravel(), minlength=n_islands + 1)

                seeded = np.zeros(n_islands + 1, dtype=bool)
                if len(tier1_coords) > 0:
                    ids_at_seeds = labeled_bg[tier1_coords[:, 0], tier1_coords[:, 1], tier1_coords[:, 2]]
                    seeded_ids = np.unique(ids_at_seeds[ids_at_seeds > 0])
                    seeded[seeded_ids] = True

                candidate_mask = (comp_size >= self.cfg.min_island_vox_fallback) & (~seeded)
                candidate_mask[0] = False
                candidate_ids = np.flatnonzero(candidate_mask)

                n_center_rejected = 0
                n_mask_rejected = 0
                accepted_coords = []

                if len(candidate_ids) > 0:
                    center_min_for_tier2 = self.cfg.center_peak_threshold * 0.5
                    tier2_hmf = self.cfg.min_high_mask_fraction * 0.4 if mask_prob is not None else 0.0
                    hmt = self.cfg.high_mask_threshold
                    sl_all = find_objects(labeled_bg)

                    for cid in candidate_ids.tolist():
                        sl = sl_all[cid - 1]
                        if sl is None:
                            continue

                        comp = (labeled_bg[sl] == cid)
                        if not np.any(comp):
                            continue

                        if float(center_sm[sl][comp].max()) < center_min_for_tier2:
                            n_center_rejected += 1
                            continue

                        if mask_prob is not None:
                            frac = float((mask_prob[sl][comp] > hmt).sum()) / int(comp.sum())
                            if frac < tier2_hmf:
                                n_mask_rejected += 1
                                continue

                        sdf_vals = sdf[sl][comp]
                        min_idx = int(np.argmin(sdf_vals))
                        comp_idx = np.flatnonzero(comp.ravel())
                        flat_min = comp_idx[min_idx]
                        lz, ly, lx = np.unravel_index(flat_min, comp.shape)
                        accepted_coords.append((
                            int(lz + sl[0].start),
                            int(ly + sl[1].start),
                            int(lx + sl[2].start),
                        ))

                n_gap = len(accepted_coords)
                if n_gap > 0:
                    gap_coords = np.asarray(accepted_coords, dtype=np.int32)
                    new_ids = np.arange(seed_count + 1, seed_count + 1 + n_gap, dtype=np.int32)
                    seed_vol[gap_coords[:, 0], gap_coords[:, 1], gap_coords[:, 2]] = new_ids
                    seed_count += n_gap

                reject_parts = []
                if n_center_rejected:
                    reject_parts.append(f"{n_center_rejected} rejected (low center)")
                if n_mask_rejected:
                    reject_parts.append(f"{n_mask_rejected} rejected (low mask)")
                reject_msg = f" | {' | '.join(reject_parts)}" if reject_parts else ""

                self._log(
                    f"   Tier-2 gap-fill seeds: {n_gap} "
                    f"(from {len(candidate_ids)} candidate islands{reject_msg})"
                )

        self._log(f"   Total seeds: {seed_count}")
        return seed_vol, seed_count, center_sm

    def _merge_enclosed_fragments(self, instances: np.ndarray) -> Tuple[np.ndarray, int]:
        max_lbl = int(instances.max())
        if max_lbl <= 1:
            return instances.astype(np.uint32, copy=False), 0

        max_enclosed_vol = max(200, self.cfg.min_cell_volume_vox // 4)
        vols = np.bincount(instances.ravel(), minlength=max_lbl + 1)
        small_labels = np.flatnonzero((vols > 0) & (vols <= max_enclosed_vol))
        small_labels = small_labels[small_labels > 0]
        if len(small_labels) == 0:
            return instances.astype(np.uint32, copy=False), 0

        sl_list = find_objects(instances)
        n_merged = 0
        out = instances.copy()

        for lbl in small_labels.tolist():
            sl = sl_list[lbl - 1] if lbl - 1 < len(sl_list) else None
            if sl is None:
                continue

            crop = out[sl]
            mask = crop == lbl
            if not mask.any():
                continue

            dilated = binary_dilation(mask, structure=_STRUCT6)
            adjacent = crop[(crop > 0) & dilated & ~mask]
            if adjacent.size == 0:
                continue

            unique_adj = np.unique(adjacent)
            if len(unique_adj) == 1:
                crop[mask] = int(unique_adj[0])
                n_merged += 1

        return out.astype(np.uint32, copy=False), n_merged

    def _filter_instances_crop(
        self,
        instances: np.ndarray,
        center_sm: Optional[np.ndarray] = None,
        mask_prob: Optional[np.ndarray] = None,
    ) -> np.ndarray:
        if int(instances.max()) == 0:
            return instances.astype(np.uint32, copy=False)

        max_lbl = int(instances.max())
        vols = np.bincount(instances.ravel(), minlength=max_lbl + 1)

        bad = np.zeros(max_lbl + 1, dtype=bool)
        bad[0] = True
        bad |= vols < self.cfg.min_cell_volume_vox

        n_vol_removed = int(bad[1:].sum())
        if n_vol_removed > 0:
            self._log(f"   Volume filter: {n_vol_removed} instances removed (< {self.cfg.min_cell_volume_vox} vox)")

        fg = instances > 0
        if fg.any():
            # OPTIMIZED: avoid .astype(np.int64) copy — bincount accepts uint32
            fg_labels = instances[fg]

            if center_sm is not None:
                min_center_signal = self.cfg.center_peak_threshold * 0.3
                max_center_per_label = np.zeros(max_lbl + 1, dtype=np.float32)
                np.maximum.at(max_center_per_label, fg_labels, center_sm[fg])
                center_bad = (max_center_per_label > 0) & (max_center_per_label < min_center_signal)
                center_bad[0] = False
                new_center_bad = center_bad & ~bad
                n_ctr_bad = int(new_center_bad.sum())
                if n_ctr_bad > 0:
                    self._log(
                        f"   Center quality filter: {n_ctr_bad} instances removed "
                        f"(max center < {min_center_signal:.4f})"
                    )
                    bad |= center_bad

            if mask_prob is not None and self.cfg.min_high_mask_fraction > 0:
                mask_flat = mask_prob[fg]
                cnt_total = vols.astype(np.float64, copy=False)
                cnt_high = np.bincount(
                    fg_labels,
                    weights=(mask_flat > self.cfg.high_mask_threshold).astype(np.float64),
                    minlength=max_lbl + 1,
                )

                hmf = np.zeros(max_lbl + 1, dtype=np.float32)
                valid = cnt_total > 0
                hmf[valid] = (cnt_high[valid] / cnt_total[valid]).astype(np.float32)

                hmf_bad = (hmf < self.cfg.min_high_mask_fraction) & valid
                hmf_bad[0] = False
                new_hmf_bad = hmf_bad & ~bad
                n_hmf_bad = int(new_hmf_bad.sum())
                if n_hmf_bad > 0:
                    rej_vals = hmf[new_hmf_bad]
                    kept_mask = valid & ~bad & ~hmf_bad
                    kept_vals = hmf[kept_mask]
                    rej_range = (
                        f", rejected frac range: {float(rej_vals.min()):.3f}-{float(rej_vals.max()):.3f}"
                        if rej_vals.size else ""
                    )
                    kept_range = (
                        f", kept frac range: {float(kept_vals.min()):.3f}-{float(kept_vals.max()):.3f}"
                        if kept_vals.size else ""
                    )
                    self._log(
                        f"   High-mask fraction filter: {n_hmf_bad} instances removed "
                        f"(frac >{self.cfg.high_mask_threshold:.2f} < {self.cfg.min_high_mask_fraction:.0%}"
                        f"{rej_range}{kept_range})"
                    )
                    bad |= hmf_bad

        qmap = np.arange(max_lbl + 1, dtype=np.uint32)
        qmap[bad] = 0
        out = qmap[instances]

        out, n_enclosed_merged = self._merge_enclosed_fragments(out)
        if n_enclosed_merged > 0:
            self._log(
                f"   Enclosed-instance merge: {n_enclosed_merged} fragments merged "
                f"(vol<={max(200, self.cfg.min_cell_volume_vox // 4)} vox)"
            )

        # VECTORIZED hole fill (single-pass, no per-hole binary_dilation)
        out, n_hole_fill, n_holes = _fill_enclosed_instance_holes(out)
        if n_hole_fill > 0:
            self._log(f"   Enclosed-hole fill: {n_hole_fill:,} voxels across {n_holes} holes")

        out = _compact_relabel(out)
        return out.astype(np.uint32, copy=False)

    def _repeat_upsample_xy(self, labels_ds: np.ndarray, crop_y: int, crop_x: int, ds: int) -> np.ndarray:
        if ds <= 1:
            return labels_ds.astype(np.uint32, copy=False)
        up = np.repeat(np.repeat(labels_ds, ds, axis=1), ds, axis=2)
        return up[:, :crop_y, :crop_x].astype(np.uint32, copy=False)

    def _downsample_watershed(
        self,
        height_i32: np.ndarray,
        seed_vol: np.ndarray,
        binary: np.ndarray,
        z0: int,
        y0: int,
        x0: int,
        z1: int,
        y1: int,
        x1: int,
    ) -> np.ndarray:
        ds = int(self.cfg.watershed_downsample_xy)
        crop_z, crop_y, crop_x = z1 - z0, y1 - y0, x1 - x0

        height_crop_i32 = height_i32[z0:z1, y0:y1, x0:x1]
        seed_crop = seed_vol[z0:z1, y0:y1, x0:x1]
        mask_crop = binary[z0:z1, y0:y1, x0:x1]

        if ds <= 1 or crop_y < 32 or crop_x < 32:
            return watershed(
                image=height_crop_i32,
                markers=seed_crop,
                mask=mask_crop,
                compactness=0.0,
                watershed_line=False,
            ).astype(np.uint32)

        ds_y = (crop_y + ds - 1) // ds
        ds_x = (crop_x + ds - 1) // ds

        height_crop = height_crop_i32.astype(np.float32, copy=False)
        height_smooth = gaussian_filter(height_crop, sigma=[0, ds * 0.4, ds * 0.4], truncate=3.0)
        height_ds = height_smooth[:, ::ds, ::ds][:, :ds_y, :ds_x].astype(np.int32)

        pad_y = (ds - crop_y % ds) % ds
        pad_x = (ds - crop_x % ds) % ds
        padded_y = crop_y + pad_y
        padded_x = crop_x + pad_x

        if pad_y or pad_x:
            mask_padded = np.pad(mask_crop, ((0, 0), (0, pad_y), (0, pad_x)), mode="constant")
        else:
            mask_padded = mask_crop

        mask_ds = mask_padded.reshape(crop_z, padded_y // ds, ds, padded_x // ds, ds).max(axis=(2, 4))[:, :ds_y, :ds_x]

        markers_ds = np.zeros((crop_z, ds_y, ds_x), dtype=np.int32)
        nz = np.nonzero(seed_crop)
        if len(nz[0]) > 0:
            markers_ds[nz[0], nz[1] // ds, nz[2] // ds] = seed_crop[nz]

        n_seeds_ds = int((markers_ds > 0).sum())
        self._log(
            f"   Watershed downsample: {ds}x XY | {crop_z}x{crop_y}x{crop_x} -> "
            f"{crop_z}x{ds_y}x{ds_x} | seeds: {n_seeds_ds}"
        )

        instances_ds = watershed(
            image=height_ds,
            markers=markers_ds,
            mask=mask_ds,
            compactness=0.0,
            watershed_line=False,
        ).astype(np.uint32)

        if ds_y == 1 and ds_x == 1:
            instances_crop = np.broadcast_to(instances_ds[:, None, None], (crop_z, crop_y, crop_x)).copy().astype(np.uint32)
        else:
            instances_crop = self._repeat_upsample_xy(instances_ds, crop_y, crop_x, ds)

        instances_crop[~mask_crop] = 0
        return instances_crop

    def _stats(self, instances: np.ndarray) -> Dict[str, Any]:
        if int(instances.max()) == 0:
            return {"n_instances": 0}

        counts = np.bincount(instances.ravel().astype(np.int64))
        vols_vox = counts[1:][counts[1:] > 0].astype(np.float32)
        if vols_vox.size == 0:
            return {"n_instances": 0}

        vox_um3 = float(np.prod(self.cfg.anisotropy))
        vols = vols_vox * vox_um3
        return {
            "n_instances": int(vols.size),
            "median_volume_um3": float(np.median(vols)),
            "mean_volume_um3": float(np.mean(vols)),
            "min_volume_um3": float(np.min(vols)),
            "max_volume_um3": float(np.max(vols)),
        }

    def _empty(self, shape: Tuple[int, int, int]) -> Dict[str, Any]:
        return {
            "instances": np.zeros(shape, np.uint32),
            "mask": np.zeros(shape, dtype=bool),
            "quality_map": np.zeros(shape, np.float32),
            "statistics": {"n_instances": 0},
            "intermediates": {},
            "cell_info": {},
        }

    def process(self, outputs: Dict[str, np.ndarray]) -> Dict[str, Any]:
        t_total = time.time()

        mask_prob = outputs["mask"]
        sdf = outputs.get("sdf", None)
        boundary = outputs.get("boundary", None)
        center = outputs.get("center", None)
        vectors = outputs.get("vectors", None)

        self._log("\n" + "=" * 72)
        self._log("TITANCELL v42.13 ADAPTIVE + VECTORIZED")
        self._log("=" * 72)

        t = time.time()
        binary = self._make_binary(mask_prob, sdf)
        self._log(f"[1/3] Binary mask: {int(binary.sum()):,} fg voxels ({time.time() - t:.2f}s)")
        if not binary.any():
            return self._empty(mask_prob.shape)

        t = time.time()
        center_arr = center if center is not None else np.zeros_like(mask_prob)
        seed_vol, n_seeds, center_sm = self._find_center_seeds(center_arr, sdf, binary, mask_prob)
        self._log(f"[2/3] Seeding: {n_seeds} seeds ({time.time() - t:.2f}s)")
        if n_seeds == 0:
            return self._empty(mask_prob.shape)

        t = time.time()
        if boundary is not None:
            if sdf is not None:
                shell_mask = (sdf > -self.cfg.boundary_shell_depth).astype(np.float32)
                boundary_surf = boundary * shell_mask
                n_zeroed = int((binary & (shell_mask == 0)).sum())
                self._log(
                    f"   Shell mask: depth={self.cfg.boundary_shell_depth:.2f}px | "
                    f"{n_zeroed:,} interior fg voxels zeroed"
                )
                sdf_norm = np.clip(sdf / self.cfg.sdf_max_dist_px, -1.0, 0.0)
            else:
                boundary_surf = boundary
                sdf_norm = np.zeros_like(boundary, dtype=np.float32)

            fg_vals = center_sm[binary]
            c_max = float(fg_vals.max()) if fg_vals.size else 1.0
            center_norm = center_sm / (c_max + 1e-8)

            if vectors is not None and self.cfg.height_div_weight > 0.0:
                div_norm = _flow_divergence(vectors, self.cfg.anisotropy)
                div_vals = div_norm[binary]
                div_min = float(div_vals.min()) if div_vals.size else 0.0
                div_max = float(div_vals.max()) if div_vals.size else 0.0
                self._log(f"   Flow div: fg range [{div_min:.3f}, {div_max:.3f}] | weight={self.cfg.height_div_weight:.3f}")
            else:
                div_norm = np.zeros_like(boundary_surf)

            height_f = (
                boundary_surf
                - self.cfg.height_center_weight * center_norm
                - self.cfg.height_div_weight * (-div_norm)
                + 0.4 * sdf_norm
            )
            hf_vals = height_f[binary]
            hf_min = float(hf_vals.min()) if hf_vals.size else 0.0
            hf_max = float(hf_vals.max()) if hf_vals.size else 0.0
            self._log(f"   Height fg range: [{hf_min:.3f}, {hf_max:.3f}]")
        else:
            height_f = -mask_prob.astype(np.float32)

        t_height = time.time() - t

        h_min = float(height_f.min())
        h_max = float(height_f.max())
        h_range = h_max - h_min
        if h_range > 1e-8:
            height_i32 = ((height_f - h_min) / (h_range + 1e-8) * 1_073_741_824).astype(np.int32)
        else:
            height_i32 = np.zeros_like(height_f, dtype=np.int32)

        z0, y0, x0, z1, y1, x1 = _fast_bbox(binary)
        self._log(f"   Watershed bbox: [{z0}:{z1}, {y0}:{y1}, {x0}:{x1}]")

        t1 = time.time()
        instances_crop = self._downsample_watershed(height_i32, seed_vol, binary, z0, y0, x0, z1, y1, x1)
        t_watershed = time.time() - t1

        crop_sl = (slice(z0, z1), slice(y0, y1), slice(x0, x1))
        t2 = time.time()
        filtered_crop = self._filter_instances_crop(
            instances_crop,
            center_sm=center_sm[crop_sl],
            mask_prob=mask_prob[crop_sl],
        )
        t_filter = time.time() - t2

        instances = np.zeros(mask_prob.shape, dtype=np.uint32)
        instances[crop_sl] = filtered_crop
        n_cells = int(filtered_crop.max())

        t_total_step3 = time.time() - t
        self._log(
            f"[3/3] Watershed + filter: {n_cells} cells ({t_total_step3:.2f}s "
            f"[height={t_height:.1f}s | ws={t_watershed:.1f}s | filter={t_filter:.1f}s])"
        )

        quality_map = (
            0.40 * np.clip(center_sm, 0, 1)
            + 0.35 * np.clip(mask_prob, 0, 1)
            + 0.25 * binary.astype(np.float32)
        ).astype(np.float32) * binary.astype(np.float32)

        stats = self._stats(instances)
        self._log(f"Total: {time.time() - t_total:.1f}s")
        self._log("=" * 72)

        cell_info = {}
        if self.cfg.return_cell_info and n_cells > 0:
            for p in regionprops(instances):
                cell_info[p.label] = {
                    "volume_vox": int(p.area),
                    "bbox": tuple(int(v) for v in p.bbox),
                }

        intermediates = {"binary": binary.astype(np.uint8)}
        if self.cfg.save_intermediates:
            intermediates.update({
                "center_sm": center_sm.astype(np.float32),
                "sdf": sdf.astype(np.float32, copy=False) if sdf is not None else np.zeros_like(mask_prob, np.float32),
                "boundary": boundary.astype(np.float32, copy=False) if boundary is not None else np.zeros_like(mask_prob, np.float32),
                "mask_prob": mask_prob.astype(np.float32),
            })

        return {
            "instances": instances.astype(np.uint32, copy=False),
            "mask": binary.astype(bool, copy=False),
            "quality_map": quality_map.astype(np.float32, copy=False),
            "statistics": stats,
            "intermediates": intermediates,
            "cell_info": cell_info,
        }


# =============================================================================
# PIPELINE
# =============================================================================

class TitanCellPipeline:
    def __init__(self, model_path: str, device: str = "cuda:0", config: Optional[PipelineConfig] = None):
        self.config = config or make_config()
        self.config.model_path = model_path
        self.config.device = device

        self._inference: Optional[InferenceEngine] = None
        self._instance: Optional[InstanceEngine] = None

        if self.config.verbose:
            print("TitanCell v42.13 adaptive+vectorized initialized", flush=True)

    def _ensure_loaded(self):
        if self._inference is None:
            self._inference = InferenceEngine(self.config)
        if self._instance is None:
            self._instance = InstanceEngine(self.config)

    def predict(self, volume: np.ndarray) -> Dict[str, np.ndarray]:
        self._ensure_loaded()
        return self._inference.predict(volume)

    def segment(self, outputs: Dict[str, np.ndarray]) -> Dict[str, Any]:
        self._ensure_loaded()
        return self._instance.process(outputs)

    def save(self, outputs: Dict[str, np.ndarray], result: Dict[str, Any], output_dir: str, base: str, save_all: bool = False):
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        tifffile.imwrite(str(out / f"{base}_instances.tif"), result["instances"].astype(np.uint32))
        tifffile.imwrite(str(out / f"{base}_mask.tif"), result["mask"].astype(np.uint8))
        tifffile.imwrite(str(out / f"{base}_quality_map.tif"), result["quality_map"].astype(np.float32))

        if save_all:
            for name in ("mask", "center", "sdf", "boundary"):
                if name in outputs:
                    tifffile.imwrite(str(out / f"{base}_{name}.tif"), outputs[name].astype(np.float32))
            for name, arr in result.get("intermediates", {}).items():
                if isinstance(arr, np.ndarray):
                    tifffile.imwrite(str(out / f"{base}_{name}.tif"), arr)

    def run(self, input_path: str, output_dir: str, save_all: bool = False) -> Dict[str, Any]:
        t0 = time.time()

        image = tifffile.imread(input_path)
        if image.ndim == 2:
            image = image[np.newaxis]
        image = image.astype(np.float32)

        print("\n" + "=" * 72, flush=True)
        print(f"PROCESSING: {Path(input_path).name}  shape={image.shape}", flush=True)
        print("=" * 72, flush=True)

        outputs = self.predict(image)
        result = self.segment(outputs)
        self.save(outputs, result, output_dir, Path(input_path).stem, save_all=save_all)

        n_cells = result["statistics"]["n_instances"]
        print(f"DONE in {time.time() - t0:.1f}s — {n_cells} cells", flush=True)
        return {"outputs": outputs, "result": result}
