from __future__ import annotations

import time
from typing import Any, Dict, Optional, Tuple

import numpy as np
from scipy.ndimage import (
    binary_dilation,
    binary_propagation,
    find_objects,
    gaussian_filter,
    gaussian_filter1d,
    generate_binary_structure,
    label as scipy_label,
    maximum_filter,
)
from scipy.spatial.distance import pdist
from skimage.measure import regionprops
from skimage.segmentation import watershed

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

from senoquant.tabs.segmentation.models.new_default_3d.config import PipelineConfig

_STRUCT6 = generate_binary_structure(3, 1)


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

    vz, vy, vx = vectors[0], vectors[1], vectors[2]
    div = np.zeros(vz.shape, np.float32)
    div[1:-1, :, :] += (vz[2:, :, :] - vz[:-2, :, :]) * inv_2az
    div[:, 1:-1, :] += (vy[:, 2:, :] - vy[:, :-2, :]) * inv_2ay
    div[:, :, 1:-1] += (vx[:, :, 2:] - vx[:, :, :-2]) * inv_2ax

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


def _label3d(arr: np.ndarray):
    """Connected components. Uses cc3d if available, else scipy."""
    if _HAS_CC3D:
        labels = cc3d.connected_components(arr.astype(np.uint32, copy=False), connectivity=6)
        return labels, int(labels.max())
    return scipy_label(arr, _STRUCT6)


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
    # OpenCV BORDER_REFLECT_101 matches scipy 'reflect' (edge not repeated)
    border = cv2.BORDER_REFLECT_101

    if sy > 0 and sx > 0:
        for z in range(out.shape[0]):
            # GaussianBlur is much faster than scipy FIR for large sigma
            out[z] = cv2.GaussianBlur(out[z], (0, 0), sigmaX=sx, sigmaY=sy, borderType=border)

    if sz > 0:
        out = gaussian_filter1d(out, sigma=sz, axis=0, truncate=truncate)
    return out


def _fill_enclosed_instance_holes(instances: np.ndarray) -> Tuple[np.ndarray, int, int]:
    max_lbl = int(instances.max())
    if max_lbl <= 0:
        return instances.astype(np.uint32, copy=False), 0, 0

    bg = instances == 0
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

    hole_id, n_holes = _label3d(holes)
    sl_list = find_objects(hole_id)

    out = instances.copy()
    n_filled_vox = 0
    n_filled_holes = 0
    shape = instances.shape

    for hid, sl in enumerate(sl_list, start=1):
        if sl is None:
            continue
        slp = _expand_slice(sl, shape, pad=1)
        crop_h = hole_id[slp] == hid
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
                f"(sdf<0 dilatedÃ—2 to sdf<1.5, mask>{noise_floor:.2f})"
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
            labeled_bg, n_islands = _label3d(interior)
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
            # OPTIMIZED: avoid .astype(np.int64) copy -- bincount accepts uint32
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
                compactness=float(self.cfg.watershed_compactness),
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
            compactness=float(self.cfg.watershed_compactness),
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


__all__ = ["InstanceEngine"]
