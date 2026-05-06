"""Torch-backed morphology primitives for RMP top-hat extraction."""

from __future__ import annotations

from typing import Iterable

import numpy as np

from .config import Array2D, KernelShape

try:
    import torch
    import torch.nn.functional as F
except ImportError:  # pragma: no cover - optional dependency
    torch = None  # type: ignore[assignment]
    F = None  # type: ignore[assignment]


def _ensure_torch_available() -> None:
    """Ensure torch is available for RMP processing."""
    if torch is None or F is None:  # pragma: no cover - import guard
        raise ImportError("torch is required for the RMP detector.")


def _torch_device() -> "torch.device":
    """Return the best available torch device (CUDA, MPS, then CPU)."""
    _ensure_torch_available()
    assert torch is not None
    if torch.cuda.is_available():
        return torch.device("cuda")
    mps_backend = getattr(torch.backends, "mps", None)
    if mps_backend is not None and mps_backend.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def _to_image_tensor(image: np.ndarray, *, device: "torch.device") -> "torch.Tensor":
    """Convert a 2D image array to a [1,1,H,W] torch tensor."""
    _ensure_torch_available()
    assert torch is not None
    tensor = torch.as_tensor(image, dtype=torch.float32, device=device)
    if tensor.ndim != 2:
        raise ValueError("Expected a 2D image for tensor conversion.")
    return tensor.unsqueeze(0).unsqueeze(0)


def _rotate_tensor(image: "torch.Tensor", angle: float) -> "torch.Tensor":
    """Rotate a [1,1,H,W] tensor with reflection padding."""
    _ensure_torch_available()
    assert torch is not None
    assert F is not None
    if image.ndim != 4:
        raise ValueError("Expected a [N,C,H,W] tensor for rotation.")

    height = float(image.shape[-2])
    width = float(image.shape[-1])
    hw_ratio = height / width if width > 0 else 1.0
    wh_ratio = width / height if height > 0 else 1.0

    radians = np.deg2rad(float(angle))
    cos_v = float(np.cos(radians))
    sin_v = float(np.sin(radians))
    # affine_grid operates in normalized coordinates; non-square images need
    # aspect-ratio correction on the off-diagonal terms.
    theta = torch.tensor(
        [[[cos_v, -sin_v * hw_ratio, 0.0], [sin_v * wh_ratio, cos_v, 0.0]]],
        dtype=image.dtype,
        device=image.device,
    )
    grid = F.affine_grid(theta, tuple(image.shape), align_corners=False)
    return F.grid_sample(
        image,
        grid,
        mode="bilinear",
        padding_mode="reflection",
        align_corners=False,
    )


def _grayscale_opening_tensor(
    image: "torch.Tensor",
    kernel_shape: KernelShape,
) -> "torch.Tensor":
    """Apply grayscale opening (erosion then dilation) with a rectangular kernel."""
    _ensure_torch_available()
    assert F is not None
    img_h = int(image.shape[-2])
    img_w = int(image.shape[-1])
    ky = min(max(1, int(kernel_shape[0])), max(1, img_h))
    kx = min(max(1, int(kernel_shape[1])), max(1, img_w))
    pad_y = ky // 2
    pad_x = kx // 2
    pad = (pad_x, pad_x, pad_y, pad_y)

    # Erosion via pooling uses the min-over-window identity:
    # min(x) == -max(-x). Missing the inner negation flips morphology behavior.
    eroded = -F.max_pool2d(
        F.pad(-image, pad, mode="reflect"),
        kernel_size=(ky, kx),
        stride=1,
    )
    opened = F.max_pool2d(
        F.pad(eroded, pad, mode="reflect"),
        kernel_size=(ky, kx),
        stride=1,
    )
    return opened


def _kernel_shape(footprint: KernelShape | np.ndarray) -> KernelShape:
    """Return kernel shape from either a tuple footprint or array."""
    if isinstance(footprint, tuple):
        return max(1, int(footprint[0])), max(1, int(footprint[1]))
    arr = np.asarray(footprint)
    if arr.ndim != 2:
        raise ValueError("Structuring element must be 2D.")
    return max(1, int(arr.shape[0])), max(1, int(arr.shape[1]))


def _pad_tensor_for_rotation(
    image: "torch.Tensor",
) -> tuple["torch.Tensor", tuple[int, int]]:
    """Pad a [1,1,H,W] tensor to preserve content after rotations."""
    nrows = int(image.shape[-2])
    ncols = int(image.shape[-1])
    diagonal = int(np.ceil(np.sqrt(nrows**2 + ncols**2)))
    rows_to_pad = int(np.ceil((diagonal - nrows) / 2))
    cols_to_pad = int(np.ceil((diagonal - ncols) / 2))
    assert F is not None
    padded = F.pad(
        image,
        (cols_to_pad, cols_to_pad, rows_to_pad, rows_to_pad),
        mode="reflect",
    )
    return padded, (rows_to_pad, cols_to_pad)


def _rmp_opening(
    input_image: Array2D,
    structuring_element: KernelShape | Array2D,
    rotation_angles: Iterable[int],
) -> Array2D:
    """Perform the RMP opening on an image."""
    device = _torch_device()
    tensor = _to_image_tensor(np.asarray(input_image, dtype=np.float32), device=device)
    padded, (newy, newx) = _pad_tensor_for_rotation(tensor)
    kernel_shape = _kernel_shape(structuring_element)

    rotated_images = [_rotate_tensor(padded, angle) for angle in rotation_angles]
    opened_images = [
        _grayscale_opening_tensor(image, kernel_shape) for image in rotated_images
    ]
    rotated_back = [
        _rotate_tensor(image, -angle)
        for image, angle in zip(opened_images, rotation_angles)
    ]
    assert torch is not None
    stacked = torch.stack(rotated_back, dim=0)
    union_image = stacked.max(dim=0).values
    cropped = union_image[
        ...,
        newy : newy + input_image.shape[0],
        newx : newx + input_image.shape[1],
    ]
    return cropped.squeeze(0).squeeze(0).detach().cpu().numpy().astype(
        np.float32,
        copy=False,
    )
