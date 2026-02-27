"""Tests for shared morphology parallel helpers."""

from __future__ import annotations

import numpy as np
import pytest

from senoquant.tabs.quantification.features import morph_parallel
from senoquant.tabs.quantification.features.morph_parallel import (
    regionprops_table_for_labels,
)


def _sample_labels() -> np.ndarray:
    labels = np.zeros((16, 16), dtype=np.int32)
    labels[1:4, 1:4] = 1
    labels[6:10, 6:10] = 2
    labels[11:14, 2:6] = 3
    labels[2:6, 10:14] = 4
    return labels


def test_regionprops_table_for_labels_aligns_requested_order() -> None:
    """Serial helper output should follow the provided label-id order."""
    labels = _sample_labels()
    label_ids = np.array([4, 2, 1], dtype=int)
    props = regionprops_table_for_labels(
        labels,
        label_ids,
        properties=("area", "eccentricity"),
        use_parallel=False,
    )

    assert np.array_equal(props["label"], label_ids)
    assert props["area"].shape == (3,)
    assert props["eccentricity"].shape == (3,)
    # Areas should map to labels 4, 2, 1 respectively.
    assert np.allclose(props["area"], np.array([16.0, 16.0, 9.0]))


def test_regionprops_table_for_labels_parallel_matches_serial() -> None:
    """Parallel path should match serial values on the same label ids."""
    labels = _sample_labels()
    label_ids = np.array([1, 2, 3, 4], dtype=int)
    properties = ("area", "extent", "solidity")

    serial = regionprops_table_for_labels(
        labels,
        label_ids,
        properties=properties,
        use_parallel=False,
    )
    parallel = regionprops_table_for_labels(
        labels,
        label_ids,
        properties=properties,
        use_parallel=True,
        min_labels_for_parallel=1,
        workers=2,
        chunk_size=2,
        backend="processpool",
    )

    assert np.array_equal(parallel["label"], serial["label"])
    for prop_name in properties:
        assert np.allclose(parallel[prop_name], serial[prop_name], equal_nan=True)


def test_backend_auto_prefers_joblib_for_spawn() -> None:
    """Auto backend should favor joblib on spawn platforms."""
    assert morph_parallel._backend_execution_order("auto", "spawn") == (
        "joblib",
        "processpool",
    )
    assert morph_parallel._backend_execution_order("auto", "fork") == (
        "processpool",
        "joblib",
    )


def test_regionprops_falls_back_joblib_to_processpool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When joblib fails, fallback should continue with processpool."""
    labels = _sample_labels()
    label_ids = np.array([1, 2], dtype=int)
    call_order: list[str] = []

    def _fail_joblib(**_: object) -> list[tuple[np.ndarray, np.ndarray]]:
        call_order.append("joblib")
        raise RuntimeError("joblib failed")

    def _ok_processpool(**_: object) -> list[tuple[np.ndarray, np.ndarray]]:
        call_order.append("processpool")
        return [
            (
                np.array([1, 2], dtype=int),
                np.array([[9.0, 16.0]], dtype=float),
            )
        ]

    monkeypatch.setattr(morph_parallel, "_preferred_start_method", lambda: "spawn")
    monkeypatch.setattr(
        morph_parallel,
        "_run_parallel_joblib_memmap",
        _fail_joblib,
    )
    monkeypatch.setattr(
        morph_parallel,
        "_run_parallel_processpool",
        _ok_processpool,
    )

    with pytest.warns(RuntimeWarning, match="backend 'joblib' failed"):
        out = regionprops_table_for_labels(
            labels,
            label_ids,
            properties=("area",),
            use_parallel=True,
            min_labels_for_parallel=1,
            workers=2,
            chunk_size=2,
            backend="joblib",
        )

    assert call_order == ["joblib", "processpool"]
    assert np.array_equal(out["label"], label_ids)
    assert np.allclose(out["area"], np.array([9.0, 16.0]))


def test_regionprops_falls_back_to_serial_after_parallel_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When all parallel backends fail, helper should fallback to serial."""
    labels = _sample_labels()
    label_ids = np.array([1, 2], dtype=int)
    call_order: list[str] = []
    sentinel = {
        "label": label_ids.copy(),
        "area": np.array([9.0, 16.0], dtype=float),
    }

    def _fail_joblib(**_: object) -> list[tuple[np.ndarray, np.ndarray]]:
        call_order.append("joblib")
        raise RuntimeError("joblib failed")

    def _fail_processpool(**_: object) -> list[tuple[np.ndarray, np.ndarray]]:
        call_order.append("processpool")
        raise RuntimeError("processpool failed")

    def _serial(
        labels_: np.ndarray,
        label_ids_: np.ndarray,
        properties_: tuple[str, ...],
    ) -> dict[str, np.ndarray]:
        del labels_, label_ids_, properties_
        call_order.append("serial")
        return sentinel

    monkeypatch.setattr(morph_parallel, "_preferred_start_method", lambda: "spawn")
    monkeypatch.setattr(
        morph_parallel,
        "_run_parallel_joblib_memmap",
        _fail_joblib,
    )
    monkeypatch.setattr(
        morph_parallel,
        "_run_parallel_processpool",
        _fail_processpool,
    )
    monkeypatch.setattr(morph_parallel, "_serial_regionprops", _serial)

    with pytest.warns(RuntimeWarning, match="fallback to serial path"):
        out = regionprops_table_for_labels(
            labels,
            label_ids,
            properties=("area",),
            use_parallel=True,
            min_labels_for_parallel=1,
            workers=2,
            chunk_size=2,
            backend="joblib",
        )

    assert call_order == ["joblib", "processpool", "serial"]
    assert out is sentinel


def test_backend_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """Env var should override backend selection when argument is omitted."""
    monkeypatch.setenv("SENOQUANT_MORPH_BACKEND", "joblib")
    assert morph_parallel._resolve_backend(None) == "joblib"
