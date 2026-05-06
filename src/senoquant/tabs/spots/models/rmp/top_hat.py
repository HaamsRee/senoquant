"""Top-hat computation helpers for the RMP detector."""

from __future__ import annotations

from contextlib import contextmanager
from functools import partial
from typing import Iterable

import numpy as np

from .config import Array2D, KernelShape, RMPSettings, RMP_TILE_CHUNK_SIZE
from .torch_ops import _rmp_opening

try:
    import dask.array as da
except ImportError:  # pragma: no cover - optional dependency
    da = None  # type: ignore[assignment]

try:  # pragma: no cover - optional dependency
    from dask.distributed import Client, LocalCluster
except ImportError:  # pragma: no cover - optional dependency
    Client = None  # type: ignore[assignment]
    LocalCluster = None  # type: ignore[assignment]


def _rmp_top_hat(
    input_image: Array2D,
    structuring_element: Array2D,
    rotation_angles: Iterable[int],
) -> Array2D:
    """Return the top-hat (background subtracted) image."""
    opened_image = _rmp_opening(input_image, structuring_element, rotation_angles)
    return input_image - opened_image


def _compute_top_hat(input_image: Array2D, config: RMPSettings) -> Array2D:
    """Compute the RMP top-hat response for a 2D image."""
    extraction_se: KernelShape = (1, config.extraction_se_length)
    rotation_angles = tuple(range(0, 180, config.angle_spacing))
    return _rmp_top_hat(input_image, extraction_se, rotation_angles)


def _ensure_dask_available() -> None:
    """Ensure dask is installed for tiled execution."""
    if da is None:  # pragma: no cover - import guard
        raise ImportError("dask is required for distributed spot detection.")


def _ensure_distributed_available() -> None:
    """Ensure dask.distributed is installed for distributed execution."""
    if Client is None or LocalCluster is None:  # pragma: no cover - import guard
        raise ImportError("dask.distributed is required for distributed execution.")


def _dask_available() -> bool:
    """Return True when dask is available."""
    return da is not None


def _distributed_available() -> bool:
    """Return True when dask.distributed is available."""
    return Client is not None and LocalCluster is not None and da is not None


def _recommended_overlap(config: RMPSettings) -> int:
    """Derive a suitable overlap from extraction structuring-element size."""
    return max(1, config.extraction_se_length * 2)


@contextmanager
def _cluster_client():
    """Yield a connected Dask client backed by a local cluster."""
    _ensure_distributed_available()
    with LocalCluster() as cluster:
        with Client(cluster) as client:
            yield client


def _rmp_top_hat_block(block: np.ndarray, config: RMPSettings) -> np.ndarray:
    """Return background-subtracted tile via the RMP top-hat pipeline."""
    extraction_se: KernelShape = (1, config.extraction_se_length)
    rotation_angles = tuple(range(0, 180, config.angle_spacing))
    top_hat = block - _rmp_opening(block, extraction_se, rotation_angles)
    return np.asarray(top_hat, dtype=np.float32)


def _rmp_top_hat_block_mapped(
    block: np.ndarray,
    *,
    config: RMPSettings,
    block_info=None,
) -> np.ndarray:
    """Top-level map_overlap callable for picklable tiled execution."""
    del block_info
    return _rmp_top_hat_block(block, config)


def _compute_top_hat_2d(
    image_2d: np.ndarray,
    config: RMPSettings,
    *,
    use_tiled: bool,
    distributed: bool,
    client: "Client | None" = None,
) -> np.ndarray:
    """Compute a top-hat image for one 2D plane."""
    if use_tiled:
        return _rmp_top_hat_tiled(
            image_2d,
            config=config,
            distributed=distributed,
            client=client,
        )
    return _compute_top_hat(image_2d, config)


def _compute_top_hat_nd(
    image: np.ndarray,
    config: RMPSettings,
    *,
    use_tiled: bool,
    use_distributed: bool,
) -> np.ndarray:
    """Compute top-hat for 2D images or slice-wise for 3D stacks."""
    if image.ndim == 2:
        return _compute_top_hat_2d(
            image,
            config,
            use_tiled=use_tiled,
            distributed=use_distributed,
        )

    top_hat_stack = np.zeros_like(image, dtype=np.float32)
    if use_tiled and use_distributed:
        with _cluster_client() as client:
            for z in range(image.shape[0]):
                top_hat_stack[z] = _compute_top_hat_2d(
                    image[z],
                    config,
                    use_tiled=True,
                    distributed=True,
                    client=client,
                )
        return top_hat_stack

    for z in range(image.shape[0]):
        top_hat_stack[z] = _compute_top_hat_2d(
            image[z],
            config,
            use_tiled=use_tiled,
            distributed=False,
        )
    return top_hat_stack


def _rmp_top_hat_tiled(
    image: np.ndarray,
    config: RMPSettings,
    chunk_size: tuple[int, int] = RMP_TILE_CHUNK_SIZE,
    overlap: int | None = None,
    distributed: bool = False,
    client: "Client | None" = None,
) -> np.ndarray:
    """Return the RMP top-hat image using tiled execution."""
    _ensure_dask_available()

    effective_overlap = _recommended_overlap(config) if overlap is None else overlap
    block_fn = partial(_rmp_top_hat_block_mapped, config=config)

    arr = da.from_array(image.astype(np.float32, copy=False), chunks=chunk_size)
    result = arr.map_overlap(
        block_fn,
        depth=(effective_overlap, effective_overlap),
        boundary="reflect",
        dtype=np.float32,
        trim=True,
    )

    if distributed:
        _ensure_distributed_available()
        if client is None:
            with _cluster_client() as temp_client:
                return temp_client.compute(result).result()
        return client.compute(result).result()

    return result.compute(scheduler="single-threaded")
