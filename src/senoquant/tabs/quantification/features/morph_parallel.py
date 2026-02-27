"""Shared parallel helpers for morphology regionprops extraction.

Provides label-id chunked extraction with backend selection and fallback.
"""

from __future__ import annotations

import math
import multiprocessing as mp
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from typing import Sequence
import warnings

import numpy as np
from scipy import ndimage as ndi
from skimage.measure import regionprops_table

try:
    from joblib import Parallel, delayed
except Exception:  # pragma: no cover - exercised in environments without joblib.
    Parallel = None
    delayed = None

DEFAULT_MIN_LABELS_FOR_PARALLEL = 4_096
MIN_CHUNK_SIZE = 32
MAX_CHUNK_SIZE = 2_048
TARGET_TASKS_PER_WORKER = 32
ENV_MORPH_BACKEND = "SENOQUANT_MORPH_BACKEND"
BACKEND_AUTO = "auto"
BACKEND_PROCESSPOOL = "processpool"
BACKEND_JOBLIB = "joblib"
VALID_BACKENDS = frozenset((BACKEND_AUTO, BACKEND_PROCESSPOOL, BACKEND_JOBLIB))

# Worker globals populated by pool initializer.
_WORKER_LABELS = None
_WORKER_BBOXES = None
_WORKER_PROPERTIES: tuple[str, ...] = ()
_WORKER_NDIM = 0


def regionprops_table_for_labels(
    labels: np.ndarray,
    label_ids: np.ndarray,
    properties: Sequence[str],
    *,
    use_parallel: bool = True,
    min_labels_for_parallel: int = DEFAULT_MIN_LABELS_FOR_PARALLEL,
    workers: int | None = None,
    chunk_size: int | None = None,
    backend: str | None = None,
) -> dict[str, np.ndarray]:
    """Return regionprops aligned to ``label_ids``.

    Parameters
    ----------
    labels : numpy.ndarray
        Integer label image.
    label_ids : numpy.ndarray
        Label ids to return in output order.
    properties : sequence of str
        Regionprops property names (excluding ``"label"``).
    use_parallel : bool, optional
        Whether to try parallel extraction.
    min_labels_for_parallel : int, optional
        Minimum number of labels required before parallel mode is used.
    workers : int or None, optional
        Process count override. ``None`` uses a bounded CPU-based default.
    chunk_size : int or None, optional
        Label ids per task. ``None`` picks an adaptive value.
    backend : str or None, optional
        Parallel backend selection: ``"auto"``, ``"processpool"``, or
        ``"joblib"``. ``None`` uses ``SENOQUANT_MORPH_BACKEND`` and defaults
        to ``"auto"``.

    Returns
    -------
    dict of str to numpy.ndarray
        Dictionary containing ``"label"`` and requested properties, aligned to
        ``label_ids`` order.

    Notes
    -----
    Parallel execution is only attempted for 2D labels and when label count
    exceeds ``min_labels_for_parallel``. For parallel runs, the function:

    1. Builds per-label bounding boxes.
    2. Splits label ids into coarse chunks.
    3. Executes chunk workers using backend order selected by policy.
    4. Reassembles outputs to preserve caller-provided ``label_ids`` order.

    Backend policy precedence is:

    1. Explicit ``backend`` argument.
    2. ``SENOQUANT_MORPH_BACKEND`` environment variable.
    3. ``"auto"`` default.

    If all parallel backends fail, execution falls back to serial
    ``regionprops_table`` with a warning.
    """
    ids = np.asarray(label_ids, dtype=int)
    prop_names = tuple(str(name) for name in properties)
    if ids.size == 0:
        return {"label": ids.copy()}
    if not prop_names:
        return {"label": ids.copy()}

    if (
        not use_parallel
        or labels.ndim != 2
        or ids.size < int(min_labels_for_parallel)
    ):
        return _serial_regionprops(labels, ids, prop_names)

    worker_count = _resolve_workers(workers)
    if worker_count <= 1:
        return _serial_regionprops(labels, ids, prop_names)

    chunk = _choose_chunk_size(
        n_labels=ids.size,
        workers=worker_count,
        requested=chunk_size,
    )
    selected_backend = _resolve_backend(backend)
    start_method = _preferred_start_method()
    backend_order = _backend_execution_order(selected_backend, start_method)
    bboxes = _label_bboxes(labels)
    tasks = _chunk_label_ids(ids, chunk)
    if not tasks:
        return _serial_regionprops(labels, ids, prop_names)

    failures: list[tuple[str, Exception]] = []
    for backend_name in backend_order:
        try:
            results = _run_parallel_backend(
                backend_name=backend_name,
                labels=labels,
                bboxes=bboxes,
                tasks=tasks,
                properties=prop_names,
                workers=worker_count,
                start_method=start_method,
            )
            return _merge_parallel_results(ids, prop_names, results)
        except Exception as exc:
            failures.append((backend_name, exc))
            warnings.warn(
                (
                    f"Parallel morphology backend '{backend_name}' failed; "
                    "trying next backend."
                ),
                RuntimeWarning,
                stacklevel=2,
            )

    if failures:
        details = ", ".join(
            f"{name}: {exc}" for name, exc in failures
        )
        warnings.warn(
            "Parallel morphology fallback to serial path "
            f"after backend failures ({details})",
            RuntimeWarning,
            stacklevel=2,
        )
    return _serial_regionprops(labels, ids, prop_names)


def _serial_regionprops(
    labels: np.ndarray,
    label_ids: np.ndarray,
    properties: tuple[str, ...],
) -> dict[str, np.ndarray]:
    """Compute regionprops in one pass and align results to requested labels.

    Parameters
    ----------
    labels : numpy.ndarray
        Integer label image.
    label_ids : numpy.ndarray
        Target label ids and output order.
    properties : tuple of str
        Region property names to compute.

    Returns
    -------
    dict of str to numpy.ndarray
        Regionprops arrays keyed by property name and aligned to ``label_ids``.
    """
    props = regionprops_table(
        labels,
        properties=("label", *properties),
    )
    return _align_to_label_ids(props, label_ids, properties)


def _align_to_label_ids(
    props: dict[str, np.ndarray],
    label_ids: np.ndarray,
    properties: tuple[str, ...],
) -> dict[str, np.ndarray]:
    """Reindex regionprops output into ``label_ids`` order.

    Parameters
    ----------
    props : dict of str to numpy.ndarray
        Raw ``regionprops_table``-style output that includes ``"label"``.
    label_ids : numpy.ndarray
        Requested labels and ordering for the output vectors.
    properties : tuple of str
        Property keys to align from ``props``.

    Returns
    -------
    dict of str to numpy.ndarray
        New mapping with ``"label"`` plus aligned property vectors. Missing
        labels are represented with ``NaN`` for float-valued properties.
    """
    result: dict[str, np.ndarray] = {"label": label_ids.astype(int, copy=True)}
    source_labels = np.asarray(props.get("label", []), dtype=int)
    source_index = {int(label): idx for idx, label in enumerate(source_labels)}

    for name in properties:
        source_values = np.asarray(props.get(name, []), dtype=float)
        values = np.full(label_ids.shape, np.nan, dtype=float)
        for out_idx, label_id in enumerate(label_ids):
            src_idx = source_index.get(int(label_id))
            if src_idx is None or src_idx >= source_values.size:
                continue
            values[out_idx] = float(source_values[src_idx])
        result[name] = values

    return result


def _label_bboxes(labels: np.ndarray) -> np.ndarray:
    """Build per-label bounding boxes from a label image.

    Parameters
    ----------
    labels : numpy.ndarray
        Integer label image with background ``0``.

    Returns
    -------
    numpy.ndarray
        Array of shape ``(max_label + 1, labels.ndim * 2)`` containing
        ``[start_0, stop_0, ..., start_n, stop_n]`` bounds for each label id.
        Missing labels are filled with ``-1`` rows.
    """
    max_label = int(labels.max()) if labels.size else 0
    bboxes = np.full((max_label + 1, labels.ndim * 2), -1, dtype=np.int32)
    slices = ndi.find_objects(labels)
    for label_id, label_slice in enumerate(slices, start=1):
        if label_slice is None:
            continue
        values: list[int] = []
        for axis_slice in label_slice:
            values.extend((int(axis_slice.start), int(axis_slice.stop)))
        bboxes[label_id, :] = np.asarray(values, dtype=np.int32)
    return bboxes


def _resolve_workers(requested: int | None) -> int:
    """Resolve process count for parallel execution.

    Parameters
    ----------
    requested : int or None
        Explicit worker count from caller, or ``None`` for auto.

    Returns
    -------
    int
        Worker count clamped to at least ``1``. Auto mode is capped to ``8``
        to avoid oversubscription in export workloads.
    """
    if requested is not None:
        return max(1, int(requested))
    cpu_total = os.cpu_count() or 1
    return max(1, min(8, int(cpu_total)))


def _choose_chunk_size(n_labels: int, workers: int, requested: int | None) -> int:
    """Choose labels-per-task for coarse chunk scheduling.

    Parameters
    ----------
    n_labels : int
        Number of label ids to process.
    workers : int
        Worker process count.
    requested : int or None
        Optional user-provided chunk size.

    Returns
    -------
    int
        Chunk size in labels, constrained to ``[MIN_CHUNK_SIZE, MAX_CHUNK_SIZE]``.
    """
    if requested is not None:
        return max(MIN_CHUNK_SIZE, int(requested))
    target_tasks = max(workers * TARGET_TASKS_PER_WORKER, 1)
    auto = int(math.ceil(n_labels / target_tasks))
    return max(MIN_CHUNK_SIZE, min(MAX_CHUNK_SIZE, auto))


def _chunk_label_ids(label_ids: np.ndarray, chunk_size: int) -> list[list[int]]:
    """Split label ids into contiguous task chunks.

    Parameters
    ----------
    label_ids : numpy.ndarray
        Label ids in desired output order.
    chunk_size : int
        Number of labels per task.

    Returns
    -------
    list of list of int
        Chunked label ids ready for map-style parallel execution.
    """
    ids = label_ids.astype(int, copy=False).tolist()
    return [ids[idx : idx + chunk_size] for idx in range(0, len(ids), chunk_size)]


def _preferred_start_method() -> str:
    """Return preferred multiprocessing start method for this platform.

    Returns
    -------
    str
        ``"spawn"`` on macOS/Windows for safety and compatibility, otherwise
        ``"fork"`` on Linux.
    """
    if os.name == "nt" or sys.platform == "darwin":
        return "spawn"
    return "fork"


def _resolve_backend(requested: str | None) -> str:
    """Resolve the selected parallel backend.

    Parameters
    ----------
    requested : str or None
        Direct backend override from the caller.

    Returns
    -------
    str
        One of ``"auto"``, ``"processpool"``, or ``"joblib"``.

    Notes
    -----
    When ``requested`` is ``None``, this function consults
    ``SENOQUANT_MORPH_BACKEND`` and falls back to ``"auto"``.
    """
    if requested is None:
        raw = os.getenv(ENV_MORPH_BACKEND, BACKEND_AUTO)
    else:
        raw = requested
    value = str(raw).strip().lower()
    if value in VALID_BACKENDS:
        return value
    warnings.warn(
        (
            "Unknown morphology backend "
            f"'{raw}', defaulting to '{BACKEND_AUTO}'"
        ),
        RuntimeWarning,
        stacklevel=3,
    )
    return BACKEND_AUTO


def _backend_execution_order(
    selected_backend: str,
    start_method: str,
) -> tuple[str, ...]:
    """Return backend attempt order for a given policy and start method.

    Parameters
    ----------
    selected_backend : str
        Resolved backend policy.
    start_method : str
        Multiprocessing start method, typically ``"fork"`` or ``"spawn"``.

    Returns
    -------
    tuple of str
        Ordered backend names to try. The first entry is preferred; the second
        is the fallback backend.
    """
    if selected_backend == BACKEND_PROCESSPOOL:
        return (BACKEND_PROCESSPOOL, BACKEND_JOBLIB)
    if selected_backend == BACKEND_JOBLIB:
        return (BACKEND_JOBLIB, BACKEND_PROCESSPOOL)
    if start_method == "fork":
        return (BACKEND_PROCESSPOOL, BACKEND_JOBLIB)
    return (BACKEND_JOBLIB, BACKEND_PROCESSPOOL)


def _init_worker_arrays(
    labels: np.ndarray,
    bboxes: np.ndarray,
    properties: tuple[str, ...],
    ndim: int,
) -> None:
    """Initialize worker globals with in-memory arrays.

    Parameters
    ----------
    labels : numpy.ndarray
        Full label image shared with worker processes.
    bboxes : numpy.ndarray
        Precomputed per-label bounding boxes.
    properties : tuple of str
        Region property names to compute per label.
    ndim : int
        Dimensionality of ``labels`` used to decode bbox coordinates.

    Returns
    -------
    None
        This function mutates module-level worker globals.
    """
    global _WORKER_LABELS, _WORKER_BBOXES, _WORKER_PROPERTIES, _WORKER_NDIM
    _WORKER_LABELS = labels
    _WORKER_BBOXES = bboxes
    _WORKER_PROPERTIES = properties
    _WORKER_NDIM = int(ndim)


def _init_worker_memmap(
    labels_path: str,
    bboxes_path: str,
    properties: tuple[str, ...],
    ndim: int,
) -> None:
    """Initialize worker globals from memory-mapped ``.npy`` files.

    Parameters
    ----------
    labels_path : str
        Path to saved label image.
    bboxes_path : str
        Path to saved label bounding-box array.
    properties : tuple of str
        Region property names to compute per label.
    ndim : int
        Dimensionality of the label image.

    Returns
    -------
    None
        This function mutates module-level worker globals.
    """
    global _WORKER_LABELS, _WORKER_BBOXES, _WORKER_PROPERTIES, _WORKER_NDIM
    _WORKER_LABELS = np.load(labels_path, mmap_mode="r")
    _WORKER_BBOXES = np.load(bboxes_path, mmap_mode="r")
    _WORKER_PROPERTIES = properties
    _WORKER_NDIM = int(ndim)


def _compute_chunk_values(
    label_chunk: list[int],
    labels: np.ndarray,
    bboxes: np.ndarray,
    properties: tuple[str, ...],
    ndim: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute regionprops for one label-id chunk.

    Parameters
    ----------
    label_chunk : list of int
        Label ids assigned to one task.
    labels : numpy.ndarray
        Label image.
    bboxes : numpy.ndarray
        Per-label bounding boxes in flattened ``start/stop`` format.
    properties : tuple of str
        Property names to compute for each label.
    ndim : int
        Dimensionality of ``labels``.

    Returns
    -------
    tuple of (numpy.ndarray, numpy.ndarray)
        First element is chunk label ids as an integer vector. Second element
        is a float matrix with shape ``(n_properties, n_chunk_labels)``.
    """
    values = np.full((len(properties), len(label_chunk)), np.nan, dtype=float)
    for col_idx, label_id in enumerate(label_chunk):
        lid = int(label_id)
        if lid <= 0 or lid >= bboxes.shape[0]:
            continue
        bounds = bboxes[lid]
        if bounds[0] < 0:
            continue
        slices = tuple(
            slice(int(bounds[axis * 2]), int(bounds[(axis * 2) + 1]))
            for axis in range(ndim)
        )
        local = (labels[slices] == lid).astype(np.uint8, copy=False)
        props = regionprops_table(local, properties=properties)
        for prop_idx, name in enumerate(properties):
            prop_values = props.get(name, ())
            if len(prop_values) > 0:
                values[prop_idx, col_idx] = float(prop_values[0])

    return np.asarray(label_chunk, dtype=int), values


def _worker_chunk(label_chunk: list[int]) -> tuple[np.ndarray, np.ndarray]:
    """Worker entrypoint using module-level arrays initialized by a pool.

    Parameters
    ----------
    label_chunk : list of int
        Label ids assigned to one worker task.

    Returns
    -------
    tuple of (numpy.ndarray, numpy.ndarray)
        Chunk label ids and property value matrix.
    """
    return _compute_chunk_values(
        label_chunk=label_chunk,
        labels=_WORKER_LABELS,
        bboxes=_WORKER_BBOXES,
        properties=_WORKER_PROPERTIES,
        ndim=_WORKER_NDIM,
    )


def _worker_chunk_arrays(
    label_chunk: list[int],
    labels: np.ndarray,
    bboxes: np.ndarray,
    properties: tuple[str, ...],
    ndim: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Worker entrypoint that receives arrays directly (joblib path).

    Parameters
    ----------
    label_chunk, labels, bboxes, properties, ndim
        Same semantics as :func:`_compute_chunk_values`.

    Returns
    -------
    tuple of (numpy.ndarray, numpy.ndarray)
        Chunk label ids and property value matrix.
    """
    return _compute_chunk_values(
        label_chunk=label_chunk,
        labels=labels,
        bboxes=bboxes,
        properties=properties,
        ndim=ndim,
    )


def _run_parallel_backend(
    backend_name: str,
    labels: np.ndarray,
    bboxes: np.ndarray,
    tasks: list[list[int]],
    properties: tuple[str, ...],
    workers: int,
    start_method: str,
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Dispatch chunk execution to the selected parallel backend.

    Parameters
    ----------
    backend_name : str
        Backend identifier.
    labels, bboxes, tasks, properties, workers, start_method
        Execution inputs shared across backend implementations.

    Returns
    -------
    list of tuple of (numpy.ndarray, numpy.ndarray)
        Per-task outputs from worker execution.

    Raises
    ------
    ValueError
        If ``backend_name`` is not supported.
    """
    if backend_name == BACKEND_PROCESSPOOL:
        return _run_parallel_processpool(
            labels=labels,
            bboxes=bboxes,
            tasks=tasks,
            properties=properties,
            workers=workers,
            start_method=start_method,
        )
    if backend_name == BACKEND_JOBLIB:
        return _run_parallel_joblib_memmap(
            labels=labels,
            bboxes=bboxes,
            tasks=tasks,
            properties=properties,
            workers=workers,
        )
    raise ValueError(f"Unknown parallel backend '{backend_name}'")


def _run_parallel_processpool(
    labels: np.ndarray,
    bboxes: np.ndarray,
    tasks: list[list[int]],
    properties: tuple[str, ...],
    workers: int,
    start_method: str,
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Run chunked extraction with :mod:`multiprocessing`.

    Parameters
    ----------
    labels, bboxes, tasks, properties, workers
        Shared parallel execution inputs.
    start_method : str
        Multiprocessing policy. ``"fork"`` routes to in-memory workers while
        ``"spawn"`` routes to memmap-backed workers.

    Returns
    -------
    list of tuple of (numpy.ndarray, numpy.ndarray)
        Per-task outputs from worker execution.
    """
    if start_method == "fork":
        return _run_parallel_fork(
            labels=labels,
            bboxes=bboxes,
            tasks=tasks,
            properties=properties,
            workers=workers,
        )
    return _run_parallel_spawn_memmap(
        labels=labels,
        bboxes=bboxes,
        tasks=tasks,
        properties=properties,
        workers=workers,
    )


def _run_parallel_fork(
    labels: np.ndarray,
    bboxes: np.ndarray,
    tasks: list[list[int]],
    properties: tuple[str, ...],
    workers: int,
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Run chunked extraction using forked worker processes.

    Parameters
    ----------
    labels, bboxes, tasks, properties, workers
        Shared parallel execution inputs.

    Returns
    -------
    list of tuple of (numpy.ndarray, numpy.ndarray)
        Per-task outputs from worker execution.
    """
    ctx = mp.get_context("fork")
    with ctx.Pool(
        processes=workers,
        initializer=_init_worker_arrays,
        initargs=(labels, bboxes, properties, labels.ndim),
    ) as pool:
        return pool.map(_worker_chunk, tasks, chunksize=1)


def _run_parallel_spawn_memmap(
    labels: np.ndarray,
    bboxes: np.ndarray,
    tasks: list[list[int]],
    properties: tuple[str, ...],
    workers: int,
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Run chunked extraction using spawn workers and memmapped arrays.

    Parameters
    ----------
    labels, bboxes, tasks, properties, workers
        Shared parallel execution inputs.

    Returns
    -------
    list of tuple of (numpy.ndarray, numpy.ndarray)
        Per-task outputs from worker execution.

    Notes
    -----
    Arrays are written to a temporary directory as ``.npy`` and re-opened in
    workers via memory mapping to minimize pickle overhead under spawn.
    """
    with TemporaryDirectory(prefix="senoquant_morph_") as tmpdir:
        temp_root = Path(tmpdir)
        labels_path = temp_root / "labels.npy"
        bboxes_path = temp_root / "bboxes.npy"
        np.save(labels_path, labels, allow_pickle=False)
        np.save(bboxes_path, bboxes, allow_pickle=False)

        ctx = mp.get_context("spawn")
        with ctx.Pool(
            processes=workers,
            initializer=_init_worker_memmap,
            initargs=(
                str(labels_path),
                str(bboxes_path),
                properties,
                labels.ndim,
            ),
        ) as pool:
            return pool.map(_worker_chunk, tasks, chunksize=1)


def _run_parallel_joblib_memmap(
    labels: np.ndarray,
    bboxes: np.ndarray,
    tasks: list[list[int]],
    properties: tuple[str, ...],
    workers: int,
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Run chunked extraction using joblib ``loky`` with memmapped arrays.

    Parameters
    ----------
    labels, bboxes, tasks, properties, workers
        Shared parallel execution inputs.

    Returns
    -------
    list of tuple of (numpy.ndarray, numpy.ndarray)
        Per-task outputs from worker execution.

    Raises
    ------
    RuntimeError
        If joblib is not importable in the current environment.
    """
    if Parallel is None or delayed is None:
        raise RuntimeError("joblib is not available")

    with TemporaryDirectory(prefix="senoquant_morph_") as tmpdir:
        temp_root = Path(tmpdir)
        labels_path = temp_root / "labels.npy"
        bboxes_path = temp_root / "bboxes.npy"
        np.save(labels_path, labels, allow_pickle=False)
        np.save(bboxes_path, bboxes, allow_pickle=False)

        labels_mm = np.load(labels_path, mmap_mode="r")
        bboxes_mm = np.load(bboxes_path, mmap_mode="r")
        with Parallel(
            n_jobs=workers,
            backend="loky",
            batch_size=1,
            max_nbytes=None,
            mmap_mode="r",
            temp_folder=str(temp_root),
        ) as parallel:
            return parallel(
                delayed(_worker_chunk_arrays)(
                    task,
                    labels_mm,
                    bboxes_mm,
                    properties,
                    labels.ndim,
                )
                for task in tasks
            )


def _merge_parallel_results(
    label_ids: np.ndarray,
    properties: tuple[str, ...],
    chunks: list[tuple[np.ndarray, np.ndarray]],
) -> dict[str, np.ndarray]:
    """Merge per-chunk outputs into one label-aligned property table.

    Parameters
    ----------
    label_ids : numpy.ndarray
        Global label-id order for the final output.
    properties : tuple of str
        Property names represented in ``chunks``.
    chunks : list of tuple of (numpy.ndarray, numpy.ndarray)
        Per-task outputs produced by worker functions.

    Returns
    -------
    dict of str to numpy.ndarray
        Final aligned result containing ``"label"`` and each requested
        property key.
    """
    result: dict[str, np.ndarray] = {"label": label_ids.astype(int, copy=True)}
    for name in properties:
        result[name] = np.full(label_ids.shape, np.nan, dtype=float)

    index_by_label = {int(label_id): idx for idx, label_id in enumerate(label_ids)}
    for chunk_labels, chunk_values in chunks:
        for col_idx, label_id in enumerate(chunk_labels):
            row_idx = index_by_label.get(int(label_id))
            if row_idx is None:
                continue
            for prop_idx, name in enumerate(properties):
                result[name][row_idx] = float(chunk_values[prop_idx, col_idx])

    return result
