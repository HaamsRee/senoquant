from __future__ import annotations

from typing import Dict, Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F


def _safe_num_groups(dim: int, preferred: int = 8) -> int:
    for groups in range(preferred, 0, -1):
        if dim % groups == 0:
            return groups
    return 1


class SeparableConvNeXtBlock3D(nn.Module):
    def __init__(self, dim: int, kz: int = 3, kxy: int = 7):
        super().__init__()
        pz, pxy = kz // 2, kxy // 2
        self.dwconv_z = nn.Conv3d(
            dim, dim, (kz, 1, 1), padding=(pz, 0, 0), groups=dim
        )
        self.dwconv_xy = nn.Conv3d(
            dim, dim, (1, kxy, kxy), padding=(0, pxy, pxy), groups=dim
        )
        self.norm = nn.GroupNorm(_safe_num_groups(dim), dim)
        self.pwconv1 = nn.Conv3d(dim, 4 * dim, 1)
        self.act = nn.GELU()
        self.pwconv2 = nn.Conv3d(4 * dim, dim, 1)

    def forward(self, x):
        hidden = self.dwconv_xy(self.dwconv_z(x))
        return x + self.pwconv2(self.act(self.pwconv1(self.norm(hidden))))


class AttentionGate3D(nn.Module):
    def __init__(self, fg_dim: int, fl_dim: int, fint_dim: int):
        super().__init__()
        self.Wg = nn.Sequential(
            nn.Conv3d(fg_dim, fint_dim, 1),
            nn.GroupNorm(_safe_num_groups(fint_dim), fint_dim),
        )
        self.Wx = nn.Sequential(
            nn.Conv3d(fl_dim, fint_dim, 1),
            nn.GroupNorm(_safe_num_groups(fint_dim), fint_dim),
        )
        self.psi = nn.Sequential(
            nn.Conv3d(fint_dim, 1, 1),
            nn.GroupNorm(1, 1),
            nn.Sigmoid(),
        )
        self.relu = nn.ReLU(inplace=True)

    def forward(self, gating, skip):
        gate = F.interpolate(
            self.Wg(gating),
            size=skip.shape[2:],
            mode="trilinear",
            align_corners=False,
        )
        return skip * self.psi(self.relu(gate + self.Wx(skip)))


class TitanCellV18_3D(nn.Module):
    DIMS = (64, 128, 256, 512)

    def __init__(self):
        super().__init__()
        dims = self.DIMS
        self.stem = nn.Sequential(
            nn.Conv3d(4, dims[0], 3, padding=1),
            nn.GroupNorm(_safe_num_groups(dims[0]), dims[0]),
            nn.GELU(),
        )
        self.enc1 = SeparableConvNeXtBlock3D(dims[0])
        self.dwn1 = nn.Conv3d(dims[0], dims[1], 2, stride=2)
        self.enc2 = SeparableConvNeXtBlock3D(dims[1])
        self.dwn2 = nn.Conv3d(dims[1], dims[2], 2, stride=2)
        self.enc3 = SeparableConvNeXtBlock3D(dims[2])
        self.dwn3 = nn.Conv3d(dims[2], dims[3], 2, stride=2)
        self.brdg = nn.Sequential(
            SeparableConvNeXtBlock3D(dims[3]),
            SeparableConvNeXtBlock3D(dims[3]),
        )
        self.up3 = nn.ConvTranspose3d(dims[3], dims[2], 2, stride=2)
        self.ag3 = AttentionGate3D(dims[2], dims[2], dims[2] // 2)
        self.dec3 = SeparableConvNeXtBlock3D(dims[2])
        self.up2 = nn.ConvTranspose3d(dims[2], dims[1], 2, stride=2)
        self.ag2 = AttentionGate3D(dims[1], dims[1], dims[1] // 2)
        self.dec2 = SeparableConvNeXtBlock3D(dims[1])
        self.up1 = nn.ConvTranspose3d(dims[1], dims[0], 2, stride=2)
        self.ag1 = AttentionGate3D(dims[0], dims[0], dims[0] // 2)
        self.dec1 = SeparableConvNeXtBlock3D(dims[0])

        self.head_mask = nn.Conv3d(dims[0], 1, 1)
        self.head_center = nn.Sequential(
            nn.Conv3d(dims[0], 32, 3, padding=1),
            nn.GroupNorm(_safe_num_groups(32), 32),
            nn.GELU(),
            nn.Conv3d(32, 1, 1),
        )
        self.head_vector = nn.Conv3d(dims[0], 3, 1)
        self.head_sdf = nn.Conv3d(dims[0], 1, 1)
        self.ds1_head = nn.Conv3d(dims[0], 1, 1)
        self.ds2_head = nn.Conv3d(dims[1], 1, 1)

        self._coord_cache: Dict[
            Tuple[int, int, int, torch.device, torch.dtype],
            Tuple[torch.Tensor, torch.Tensor, torch.Tensor],
        ] = {}

    @staticmethod
    def _match(x, target):
        dz = max(0, target.shape[2] - x.shape[2])
        dy = max(0, target.shape[3] - x.shape[3])
        dx = max(0, target.shape[4] - x.shape[4])
        if dz or dy or dx:
            x = F.pad(x, (0, dx, 0, dy, 0, dz))
        return x[..., : target.shape[2], : target.shape[3], : target.shape[4]]

    def _coords(
        self, shape: Tuple[int, int, int], device: torch.device, dtype: torch.dtype
    ):
        key = (shape[0], shape[1], shape[2], device, dtype)
        cached = self._coord_cache.get(key)
        if cached is None:
            z_dim, y_dim, x_dim = shape
            zc = torch.linspace(-1, 1, z_dim, device=device, dtype=dtype).view(
                1, 1, z_dim, 1, 1
            )
            yc = torch.linspace(-1, 1, y_dim, device=device, dtype=dtype).view(
                1, 1, 1, y_dim, 1
            )
            xc = torch.linspace(-1, 1, x_dim, device=device, dtype=dtype).view(
                1, 1, 1, 1, x_dim
            )
            cached = (zc, yc, xc)
            self._coord_cache[key] = cached
        return cached

    def _add_coords(self, x):
        batch, _, z_dim, y_dim, x_dim = x.shape
        zc, yc, xc = self._coords((z_dim, y_dim, x_dim), x.device, x.dtype)
        return torch.cat(
            [
                x,
                zc.expand(batch, 1, z_dim, y_dim, x_dim),
                yc.expand(batch, 1, z_dim, y_dim, x_dim),
                xc.expand(batch, 1, z_dim, y_dim, x_dim),
            ],
            dim=1,
        )

    def forward(self, x):
        x = self._add_coords(x)
        s1 = self.enc1(self.stem(x))
        s2 = self.enc2(self.dwn1(s1))
        s3 = self.enc3(self.dwn2(s2))
        bridge = self.brdg(self.dwn3(s3))

        u3 = self._match(self.up3(bridge), s3)
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


__all__ = ["AttentionGate3D", "SeparableConvNeXtBlock3D", "TitanCellV18_3D"]
