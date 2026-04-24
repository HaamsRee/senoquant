from __future__ import annotations

import time
from typing import Dict, List, Tuple

import numpy as np
import torch
from torch.amp import autocast

from senoquant.tabs.segmentation.models.new_default_3d.config import PipelineConfig
from senoquant.tabs.segmentation.models.new_default_3d.network import TitanCellV18_3D


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
                    int,
                    int,
                    int,
                    int,
                    int,
                    int,
                    Tuple[int, int, int],
                    Tuple[Tuple[int, int], Tuple[int, int], Tuple[int, int]],
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

        self.model = TitanCellV18_3D()

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


__all__ = ["InferenceEngine"]
