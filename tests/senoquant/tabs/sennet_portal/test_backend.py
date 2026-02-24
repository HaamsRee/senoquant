"""Tests for SenNet Portal backend discovery and download flow."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import pytest

from senoquant.tabs.sennet_portal.backend import SenNetDataset, SenNetPortalBackend


@pytest.fixture(autouse=True)
def _stable_supported_extensions(monkeypatch: pytest.MonkeyPatch) -> None:
    """Use deterministic reader extensions for SenNet backend tests.

    Notes
    -----
    The real reader extension set is environment-dependent and may include
    non-image suffixes through installed plugins. Pinning here keeps test
    expectations stable across developer/CI environments.
    """
    monkeypatch.setattr(
        "senoquant.tabs.sennet_portal.backend.supported_image_extensions",
        lambda: (".ome.tif", ".ome.tiff", ".qptiff", ".czi"),
    )


@pytest.fixture(autouse=True)
def _stable_entity_fetch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avoid network dependency for Entity API in backend tests."""
    monkeypatch.setattr(
        SenNetPortalBackend,
        "_fetch_dataset_entity",
        lambda self, dataset_id, token=None: {
            "sennet_id": dataset_id,
            "entity_type": "Dataset",
            "uuid": f"entity-{dataset_id}",
        },
    )


def test_search_datasets_filters_antibody_and_supported_paths() -> None:
    """Return only antibody datasets with compatible file extensions."""
    backend = SenNetPortalBackend()

    def fake_post(url: str, *, payload, token=None):
        assert url == backend.SEARCH_API_URL
        assert payload["query"]["bool"]["must"][0]["term"]["entity_type.keyword"] == "Dataset"
        return {
            "hits": {
                "hits": [
                    {
                        "_source": {
                            "sennet_id": "SNT1",
                            "uuid": "uuid-snt1",
                            "dataset_type": "PhenoCycler",
                            "status": "Published",
                            "data_access_level": "consortium",
                            "sources": [{"source_type": "Human"}],
                            "origin_samples": [{"organ": "UBERON:0001264"}],
                            "dataset_type_hierarchy": {
                                "first_level": ["Antibody-based imaging"]
                            },
                            "files": [
                                {"rel_path": "/raw/image_a.ome.tif"},
                                {"rel_path": "/notes/readme.txt"},
                            ],
                        }
                    },
                    {
                        "_source": {
                            "sennet_id": "SNT3",
                            "dataset_type": "CODEX",
                            "status": "Published",
                            "data_access_level": "public",
                            "dataset_type_hierarchy": {
                                "first_level": ["Antibody-based imaging"]
                            },
                            "files": [
                                {"rel_path": "/tables/summary.csv"},
                            ],
                        }
                    },
                ]
            }
        }

    def fake_fetch_json(url: str, *, params=None, token=None):
        if url == backend.ORGANS_API_URL:
            assert params == {"application_context": "SENNET"}
            return [{"organ_uberon": "UBERON:0001264", "term": "Pancreas"}]
        assert url == backend.PARAM_SEARCH_FILES_URL
        assert params == {"dataset_sennet_id": "SNT1"}
        return [
            {"rel_path": "/raw/image_a.ome.tif"},
            {"rel_path": "/notes/readme.txt"},
        ]

    backend._post_json = fake_post  # type: ignore[method-assign]
    backend._fetch_json = fake_fetch_json  # type: ignore[method-assign]

    datasets = backend.search_datasets(
        dataset_types=["PhenoCycler"],
        max_results=10,
        status="Published",
    )

    assert len(datasets) == 1
    assert datasets[0].sennet_id == "SNT1"
    assert datasets[0].dataset_uuid == "uuid-snt1"
    assert datasets[0].source_type == "Human"
    assert datasets[0].organ == "Pancreas"
    assert datasets[0].compatible_paths == ["/raw/image_a.ome.tif"]
    assert datasets[0].compatible_extensions == [".ome.tif"]
    assert datasets[0].entity_payload["sennet_id"] == "SNT1"


def test_download_datasets_builds_manifest_and_runs_clt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Create manifest lines and call ``sennet-clt transfer <manifest>``."""
    backend = SenNetPortalBackend()
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/sennet-clt")
    monkeypatch.setattr(backend, "_home_dir", lambda: home)

    manifest_text: dict[str, str] = {"value": ""}
    calls: list[list[str]] = []

    def fake_run(args: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        if args[:2] == ["sennet-clt", "whoami"]:
            return subprocess.CompletedProcess(args, 0, stdout="tester", stderr="")
        if args[:2] == ["sennet-clt", "transfer"]:
            manifest_path = Path(args[2])
            manifest_text["value"] = manifest_path.read_text(encoding="utf-8")
            destination = args[args.index("--destination") + 1]
            transfer_root = home / destination
            transfer_root.mkdir(parents=True, exist_ok=True)
            (transfer_root / "SNT1").mkdir(exist_ok=True)
            (transfer_root / "SNT1" / "image_a.ome.tif").write_text(
                "fake-data", encoding="utf-8"
            )
            return subprocess.CompletedProcess(
                args,
                0,
                stdout=(
                    "Message: The transfer has been accepted and a task has been created "
                    "and queued for execution\n"
                    "Task ID: 5724a523-11aa-11f1-a049-0e5b09a3151b\n"
                ),
                stderr="",
            )
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="unexpected")

    monkeypatch.setattr(backend, "_run_command", fake_run)

    destination = home / "downloads"
    result = backend.download_datasets(
        [
            SenNetDataset(
                sennet_id="SNT1",
                dataset_type="PhenoCycler",
                status="Published",
                access_level="consortium",
                title="Dataset 1",
                compatible_paths=["/raw/image_a.ome.tif"],
                compatible_extensions=[".ome.tif"],
                entity_payload={
                    "sennet_id": "SNT1",
                    "entity_type": "Dataset",
                    "cedar_mapped_metadata": {"Source Type": "Mouse"},
                },
            )
        ],
        destination,
    )

    assert len(calls) == 2
    assert calls[1][:2] == ["sennet-clt", "transfer"]
    assert "SNT1 /raw/image_a.ome.tif" in manifest_text["value"]
    metadata_path = destination / "SNT1" / "sennet_dataset_metadata.json"
    assert metadata_path.is_file()
    metadata_payload = metadata_path.read_text(encoding="utf-8")
    assert '"sennet_entity_payload"' in metadata_payload
    assert '"cedar_mapped_metadata"' in metadata_payload
    assert result["dataset_count"] == 1
    assert result["file_count"] == 1
    assert result["task_ids"] == ["5724a523-11aa-11f1-a049-0e5b09a3151b"]


def test_extract_task_ids_parses_globus_stdout() -> None:
    """Extract task IDs from globus transfer output text."""
    backend = SenNetPortalBackend()
    task_ids = backend._extract_task_ids(
        "Task ID: 11111111-2222-3333-4444-555555555555\n"
        "Task ID: 11111111-2222-3333-4444-555555555555\n"
        "Task ID: aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee\n",
        None,
    )
    assert task_ids == [
        "11111111-2222-3333-4444-555555555555",
        "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    ]


def test_download_tasks_status_aggregates_progress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Aggregate per-task status payloads from globus task show output."""
    backend = SenNetPortalBackend()
    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/globus")

    payloads = {
        "task-a": {
            "task_id": "task-a",
            "status": "ACTIVE",
            "files": 10,
            "subtasks_total": 20,
            "subtasks_pending": 10,
            "subtasks_retrying": 0,
            "subtasks_succeeded": 10,
            "subtasks_failed": 0,
            "effective_bytes_per_second": 5_000_000,
            "bytes_transferred": 123,
        },
        "task-b": {
            "task_id": "task-b",
            "status": "SUCCEEDED",
            "files": 5,
            "subtasks_total": 10,
            "subtasks_pending": 0,
            "subtasks_retrying": 0,
            "subtasks_succeeded": 10,
            "subtasks_failed": 0,
            "effective_bytes_per_second": 0,
            "bytes_transferred": 456,
        },
    }

    def fake_run(args: list[str]) -> subprocess.CompletedProcess[str]:
        task_id = args[3]
        return subprocess.CompletedProcess(args, 0, stdout=json.dumps(payloads[task_id]), stderr="")

    monkeypatch.setattr(backend, "_run_command", fake_run)
    status = backend.download_tasks_status(["task-a", "task-b"])
    assert status["task_count"] == 2
    assert status["overall_status"] == "ACTIVE"
    assert status["all_complete"] is False
    assert status["progress_percent"] == 67
    assert status["speed_bps"] == 5_000_000


def test_cancel_download_tasks_runs_globus_cancel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cancel each active task through globus CLI."""
    backend = SenNetPortalBackend()
    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/globus")
    calls: list[list[str]] = []

    def fake_run(args: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(backend, "_run_command", fake_run)
    backend.cancel_download_tasks(["task-a", "task-b"])
    assert calls == [
        ["globus", "task", "cancel", "task-a"],
        ["globus", "task", "cancel", "task-b"],
    ]


def test_sample_age_normalization_uses_mouse_months_and_human_years() -> None:
    """Normalize mapped age to mouse months and human years."""
    backend = SenNetPortalBackend()
    source_payload = {
        "sources": [
            {
                "mapped_metadata": {
                    "age": {
                        "unit": "years",
                        "value": [2.5],
                    }
                }
            }
        ]
    }

    mouse_text, mouse_value, mouse_unit = backend._sample_age_from_payload(
        summary_payload={},
        entity_payload=source_payload,
        source_type="Mouse",
    )
    human_text, human_value, human_unit = backend._sample_age_from_payload(
        summary_payload={},
        entity_payload=source_payload,
        source_type="Human",
    )

    assert mouse_text == "30 months"
    assert mouse_value == pytest.approx(30.0)
    assert mouse_unit == "months"
    assert human_text == "2.5 years"
    assert human_value == pytest.approx(2.5)
    assert human_unit == "years"


def test_sample_age_normalization_uses_local_lifespan_data_fallback() -> None:
    """Estimate age from local lifespan text when mapped age is missing."""
    backend = SenNetPortalBackend()
    entity_payload = {"sources": [{"metadata": {"local_lifespan_data": "25.5 month"}}]}

    text, value, unit = backend._sample_age_from_payload(
        summary_payload={},
        entity_payload=entity_payload,
        source_type="Human",
    )

    assert text == "2.1 years"
    assert value == pytest.approx(2.125)
    assert unit == "years"


def test_available_antibody_dataset_types_uses_aggregation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Discover dynamic dataset types from Search API aggregation buckets."""
    backend = SenNetPortalBackend()

    def fake_post(url: str, *, payload, token=None):
        assert url == backend.SEARCH_API_URL
        assert payload["size"] == 0
        assert payload["aggs"]["dataset_types"]["terms"]["field"] == "dataset_type.keyword"
        return {
            "aggregations": {
                "dataset_types": {
                    "buckets": [
                        {"key": "MIBI"},
                        {"key": "PhenoCycler"},
                    ]
                }
            }
        }

    monkeypatch.setattr(backend, "_post_json", fake_post)
    dataset_types = backend.available_antibody_dataset_types()
    assert dataset_types == ["MIBI", "PhenoCycler"]


def test_available_antibody_dataset_types_falls_back_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Return fallback static list when aggregation query fails."""
    backend = SenNetPortalBackend()

    def fake_post(url: str, *, payload, token=None):
        raise RuntimeError("network failure")

    monkeypatch.setattr(backend, "_post_json", fake_post)
    dataset_types = backend.available_antibody_dataset_types()
    assert dataset_types == list(backend.ANTIBODY_DATASET_TYPES)


def test_search_datasets_uses_param_search_files_when_indexed_files_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Include datasets when param-search/files reveals supported files."""
    backend = SenNetPortalBackend()

    def fake_post(url: str, *, payload, token=None):
        assert url == backend.SEARCH_API_URL
        return {
            "hits": {
                "hits": [
                    {
                        "_source": {
                            "sennet_id": "SNT1",
                            "dataset_type": "PhenoCycler",
                            "status": "Published",
                            "data_access_level": "public",
                            "dataset_type_hierarchy": {
                                "first_level": ["Antibody-based imaging"]
                            },
                        }
                    }
                ]
            }
        }

    def fake_fetch_json(url: str, *, params=None, token=None):
        if url == backend.ORGANS_API_URL:
            assert params == {"application_context": "SENNET"}
            return []
        assert url == backend.PARAM_SEARCH_FILES_URL
        assert params == {"dataset_sennet_id": "SNT1"}
        return [
            {"rel_path": "panel/image.qptiff", "file_extension": ".qptiff"},
            {"rel_path": "panel/readme.txt", "file_extension": ".txt"},
        ]

    monkeypatch.setattr(backend, "_post_json", fake_post)
    monkeypatch.setattr(backend, "_fetch_json", fake_fetch_json)

    datasets = backend.search_datasets(
        dataset_types=["PhenoCycler"],
        max_results=10,
        status="Published",
    )

    assert len(datasets) == 1
    assert datasets[0].sennet_id == "SNT1"
    assert datasets[0].compatible_paths == ["/panel/image.qptiff"]
    assert datasets[0].compatible_extensions == [".qptiff"]


def test_search_datasets_does_not_require_globus_login(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Run search without requiring local Globus login state."""
    backend = SenNetPortalBackend()
    monkeypatch.setattr(shutil, "which", lambda _name: None)

    def fake_post(url: str, *, payload, token=None):
        assert url == backend.SEARCH_API_URL
        return {"hits": {"hits": []}}

    def fake_fetch_json(url: str, *, params=None, token=None):
        raise AssertionError("No file lookup expected when no dataset hits are returned")

    monkeypatch.setattr(backend, "_post_json", fake_post)
    monkeypatch.setattr(backend, "_fetch_json", fake_fetch_json)
    datasets = backend.search_datasets(
        dataset_types=["PhenoCycler"],
        max_results=5,
        status="Published",
    )
    assert datasets == []


def test_backend_uses_reader_supported_extensions(monkeypatch: pytest.MonkeyPatch) -> None:
    """Use reader-derived extensions when matching compatible paths."""
    monkeypatch.setattr(
        "senoquant.tabs.sennet_portal.backend.supported_image_extensions",
        lambda: (".abc", ".very.long.ext"),
    )
    backend = SenNetPortalBackend()
    assert backend._matching_supported_extension("/x/sample.VERY.LONG.EXT") == ".very.long.ext"
    assert backend._matching_supported_extension("/x/sample.abc") == ".abc"


def test_login_globus_runs_login_command(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run globus login command when CLI is installed."""
    backend = SenNetPortalBackend()
    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/globus")
    calls: list[list[str]] = []

    def fake_run(args: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, stdout="ok", stderr="")

    monkeypatch.setattr(backend, "_run_command", fake_run)
    backend.login_globus()
    assert calls == [["globus", "login"]]


def test_login_globus_requires_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    """Raise a helpful error when globus CLI is unavailable."""
    backend = SenNetPortalBackend()
    monkeypatch.setattr(shutil, "which", lambda _name: None)

    with pytest.raises(RuntimeError, match="Globus CLI"):
        backend.login_globus()


def test_logout_globus_runs_logout_command(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run globus logout command when CLI is installed."""
    backend = SenNetPortalBackend()
    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/globus")
    calls: list[list[str]] = []

    def fake_run(args: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, stdout="ok", stderr="")

    monkeypatch.setattr(backend, "_run_command", fake_run)
    backend.logout_globus()
    assert calls == [["globus", "logout", "--yes"]]


def test_globus_login_status_reports_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    """Return logged-in status and identity from globus whoami output."""
    backend = SenNetPortalBackend()
    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/globus")

    def fake_run(args: list[str]) -> subprocess.CompletedProcess[str]:
        assert args[:2] == ["globus", "whoami"]
        return subprocess.CompletedProcess(args, 0, stdout="user@example.org\n", stderr="")

    monkeypatch.setattr(backend, "_run_command", fake_run)
    logged_in, detail = backend.globus_login_status()
    assert logged_in is True
    assert detail == "user@example.org"


def test_globus_login_status_reports_not_logged_in(monkeypatch: pytest.MonkeyPatch) -> None:
    """Return not-logged-in status when globus whoami fails."""
    backend = SenNetPortalBackend()
    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/globus")

    def fake_run(args: list[str]) -> subprocess.CompletedProcess[str]:
        assert args[:2] == ["globus", "whoami"]
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="not logged in")

    monkeypatch.setattr(backend, "_run_command", fake_run)
    logged_in, detail = backend.globus_login_status()
    assert logged_in is False
    assert detail == "Not logged in"


def test_gcp_installation_status_reports_missing_cli(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Report unavailable status when Globus CLI is not installed."""
    backend = SenNetPortalBackend()
    monkeypatch.setattr(shutil, "which", lambda _name: None)

    available, detail = backend.gcp_installation_status()
    assert available is False
    assert detail == "Globus CLI not found"


def test_gcp_installation_status_reports_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Report available status and endpoint id when GCP is installed."""
    backend = SenNetPortalBackend()
    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/globus")

    def fake_run(args: list[str]) -> subprocess.CompletedProcess[str]:
        assert args == ["globus", "endpoint", "local-id"]
        return subprocess.CompletedProcess(args, 0, stdout="abc-endpoint-id\n", stderr="")

    monkeypatch.setattr(backend, "_run_command", fake_run)
    available, detail = backend.gcp_installation_status()
    assert available is True
    assert detail == "abc-endpoint-id"


def test_gcp_installation_status_reports_not_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Report not-installed status from standard Globus CLI error text."""
    backend = SenNetPortalBackend()
    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/globus")

    def fake_run(args: list[str]) -> subprocess.CompletedProcess[str]:
        assert args == ["globus", "endpoint", "local-id"]
        return subprocess.CompletedProcess(
            args,
            1,
            stdout="",
            stderr="No Globus Connect Personal installation found.",
        )

    monkeypatch.setattr(backend, "_run_command", fake_run)
    available, detail = backend.gcp_installation_status()
    assert available is False
    assert detail == "Globus Connect Personal not installed"


def test_download_datasets_requires_clt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Raise a helpful error when sennet-clt is unavailable."""
    backend = SenNetPortalBackend()
    monkeypatch.setattr(shutil, "which", lambda _name: None)

    with pytest.raises(RuntimeError, match="sennet-clt"):
        backend.download_datasets(
            [
                SenNetDataset(
                    sennet_id="SNT1",
                    dataset_type="PhenoCycler",
                    status="Published",
                    access_level="consortium",
                    title="Dataset 1",
                    compatible_paths=["/raw/image_a.ome.tif"],
                    compatible_extensions=[".ome.tif"],
                )
            ],
            tmp_path / "downloads",
        )
