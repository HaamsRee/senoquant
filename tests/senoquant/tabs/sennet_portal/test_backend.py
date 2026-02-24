"""Tests for SenNet Portal backend discovery and download flow."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

import pytest

from senoquant.tabs.sennet_portal.backend import SenNetDataset, SenNetPortalBackend


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
                            "dataset_type": "PhenoCycler",
                            "status": "Published",
                            "data_access_level": "consortium",
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
    assert datasets[0].compatible_paths == ["/raw/image_a.ome.tif"]
    assert datasets[0].compatible_extensions == [".ome.tif"]


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
            return subprocess.CompletedProcess(args, 0, stdout="ok", stderr="")
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
            )
        ],
        destination,
    )

    assert len(calls) == 2
    assert calls[1][:2] == ["sennet-clt", "transfer"]
    assert "SNT1 /raw/image_a.ome.tif" in manifest_text["value"]
    assert result["dataset_count"] == 1
    assert result["file_count"] == 1


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
