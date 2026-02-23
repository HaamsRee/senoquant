"""Backend logic for SenNet dataset discovery and downloads."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any, Iterable, Sequence
from urllib.parse import quote, unquote, urlencode, urlparse
from urllib.request import Request, urlopen


@dataclass(slots=True)
class SenNetDataset:
    """Serializable SenNet dataset description for the portal UI.

    Parameters
    ----------
    sennet_id : str
        Primary SenNet identifier for the dataset (for example, ``SNT...``).
    dataset_type : str
        SenNet dataset type label used for filtering and display.
    status : str
        Publication or curation status returned by SenNet.
    access_level : str
        Access level label (for example, public or consortium).
    title : str
        Human-readable title, dataset name, or fallback identifier.
    compatible_paths : list of str
        Dataset-relative file paths that match SenoQuant-supported formats.
    compatible_extensions : list of str
        Unique supported file extensions detected in ``compatible_paths``.
    """

    sennet_id: str
    dataset_type: str
    status: str
    access_level: str
    title: str
    compatible_paths: list[str]
    compatible_extensions: list[str]


class SenNetPortalBackend:
    """Discover and download SenNet datasets that SenoQuant can ingest.

    Notes
    -----
    Discovery combines the SenNet Search API and Entity API:

    1. Search returns candidate dataset records.
    2. Entity payloads are inspected for richer metadata and file paths.
    3. Results are filtered to antibody-based imaging and supported file types.

    Downloads are executed through ``sennet-clt`` manifest transfers.
    """

    SEARCH_DATASETS_URL = "https://search.api.sennetconsortium.org/param-search/datasets"
    SEARCH_API_URL = "https://search.api.sennetconsortium.org/search"
    ENTITY_API_URL = "https://entity.api.sennetconsortium.org"
    INGEST_API_URL = "https://ingest.api.sennetconsortium.org"

    # Matches SenoQuant batch input defaults and reader expectations.
    SUPPORTED_IMAGE_EXTENSIONS = (
        ".ome.tiff",
        ".ome.tif",
        ".tiff",
        ".tif",
        ".png",
        ".jpg",
        ".jpeg",
        ".czi",
        ".nd2",
        ".lif",
        ".zarr",
        ".qptiff",
    )

    # SenNet dataset-type terms commonly used for antibody-based imaging.
    ANTIBODY_DATASET_TYPES = (
        "2D Imaging Mass Cytometry",
        "3D Imaging Mass Cytometry",
        "CODEX",
        "Confocal microscopy",
        "MIBI",
        "PhenoCycler",
        "Thick section Multiphoton MxIF",
    )
    ANTIBODY_FIRST_LEVEL = "Antibody-based imaging"

    _PATH_FIELD_NAMES = {
        "rel_path",
        "path",
        "file_path",
        "file_name",
        "filename",
        "name",
        "uri",
        "url",
    }

    def __init__(self, *, request_timeout: float = 30.0) -> None:
        """Initialize API and extension-matching settings.

        Parameters
        ----------
        request_timeout : float, optional
            Timeout in seconds for each HTTP request to SenNet APIs.

        Returns
        -------
        None
            This initializer stores configuration on the instance.
        """
        self._request_timeout = float(request_timeout)
        self._extension_check_order = tuple(
            sorted(self.SUPPORTED_IMAGE_EXTENSIONS, key=len, reverse=True)
        )
        self._globus_ls_ready_cache: bool | None = None

    def search_datasets(
        self,
        *,
        dataset_types: Sequence[str] | None = None,
        token: str | None = None,
        max_results: int = 40,
        status: str = "Published",
    ) -> list[SenNetDataset]:
        """Find antibody-imaging datasets with supported image files.

        Parameters
        ----------
        dataset_types : sequence of str or None, optional
            SenNet dataset-type labels to query. If ``None`` the backend uses
            ``ANTIBODY_DATASET_TYPES``.
        token : str or None, optional
            Optional bearer token for authenticated API access.
        max_results : int, optional
            Maximum number of compatible datasets to return.
        status : str, optional
            Dataset status filter sent to the Search API.

        Returns
        -------
        list of SenNetDataset
            Compatible dataset records ordered by discovery time.

        Notes
        -----
        A dataset is considered compatible when it passes all checks:

        - Matches antibody-focused dataset criteria.
        - Has at least one file path with a supported extension (from indexed
          Search API metadata or a Globus listing fallback).
        """
        requested_types = list(dataset_types or self.ANTIBODY_DATASET_TYPES)
        if not requested_types:
            return []
        limit = max(1, int(max_results))
        self._globus_ls_ready_cache = None

        seen_ids: set[str] = set()
        datasets: list[SenNetDataset] = []
        for dataset_type in requested_types:
            payload = self._post_json(
                self.SEARCH_API_URL,
                payload=self._dataset_search_body(
                    dataset_type=str(dataset_type).strip(),
                    status=str(status).strip(),
                    size=max(200, limit),
                ),
                token=token,
            )
            for record in self._iter_dataset_records(payload):
                dataset_id = self._dataset_id_from_payload(record)
                if not dataset_id or dataset_id in seen_ids:
                    continue
                seen_ids.add(dataset_id)

                # Filter order:
                # 1) Must be Antibody-based imaging by first-level hierarchy.
                # 2) Must match requested dataset type(s).
                if not self._is_antibody_based_imaging(record):
                    continue
                if not self._matches_requested_dataset_type(record, requested_types):
                    continue

                compatible_paths = self._extract_supported_paths(record)
                if not compatible_paths:
                    compatible_paths = self._extract_supported_paths_from_globus(
                        dataset_id,
                        token=token,
                    )
                if not compatible_paths:
                    continue

                extensions = sorted(
                    {
                        ext
                        for path in compatible_paths
                        for ext in [self._matching_supported_extension(path)]
                        if ext is not None
                    }
                )
                datasets.append(
                    SenNetDataset(
                        sennet_id=dataset_id,
                        dataset_type=self._text_value(
                            record.get("dataset_type"),
                            default="Unknown",
                        ),
                        status=self._text_value(
                            record.get("status"),
                            default="Unknown",
                        ),
                        access_level=self._text_value(
                            record.get("access_level"),
                            record.get("data_access_level"),
                            default="Unknown",
                        ),
                        title=self._dataset_title(record, record, dataset_id),
                        compatible_paths=compatible_paths,
                        compatible_extensions=extensions,
                    )
                )
                if len(datasets) >= limit:
                    return datasets

        return datasets

    def _dataset_search_body(self, *, dataset_type: str, status: str, size: int) -> dict[str, Any]:
        """Build Elasticsearch request body for dataset search.

        Parameters
        ----------
        dataset_type : str
            SenNet dataset type to include in results.
        status : str
            SenNet status to include in results.
        size : int
            Maximum number of hits to request.

        Returns
        -------
        dict of str to Any
            Search API request payload.
        """
        return {
            "size": max(1, int(size)),
            "query": {
                "bool": {
                    "must": [
                        {"term": {"entity_type.keyword": "Dataset"}},
                        {
                            "term": {
                                "dataset_type_hierarchy.first_level.keyword": self.ANTIBODY_FIRST_LEVEL
                            }
                        },
                        {"term": {"dataset_type.keyword": dataset_type}},
                        {"term": {"status.keyword": status}},
                    ]
                }
            },
        }

    def download_datasets(
        self,
        datasets: Sequence[SenNetDataset],
        destination: str | Path,
    ) -> dict[str, object]:
        """Download selected dataset file paths via ``sennet-clt`` manifest mode.

        Parameters
        ----------
        datasets : sequence of SenNetDataset
            Selected datasets whose compatible paths should be transferred.
        destination : str or pathlib.Path
            Local destination directory where downloaded files should end up.

        Returns
        -------
        dict of str to object
            Summary payload with ``dataset_count``, ``file_count``, and
            ``destination``.

        Raises
        ------
        ValueError
            If no valid datasets were provided.
        RuntimeError
            If the CLT is missing, authentication is unavailable, or transfer
            execution fails.
        """
        dataset_list = [item for item in datasets if isinstance(item, SenNetDataset)]
        if not dataset_list:
            raise ValueError("Select at least one dataset to download.")

        if shutil.which("sennet-clt") is None:
            raise RuntimeError(
                "sennet-clt was not found in PATH. Install it and run `sennet-clt auth login`."
            )

        manifest_lines = self._build_manifest_lines(dataset_list)
        if not manifest_lines:
            raise RuntimeError(
                "No compatible file paths were available for the selected datasets."
            )

        destination_path = Path(destination).expanduser().resolve()
        destination_path.mkdir(parents=True, exist_ok=True)
        clt_destination, staging_dir = self._resolve_clt_destination(destination_path)

        auth_check = self._run_command(["sennet-clt", "auth", "whoami"])
        if auth_check.returncode != 0:
            raise RuntimeError(
                "SenNet authentication not available. Run `sennet-clt auth login` first."
            )

        manifest_root = Path(tempfile.mkdtemp(prefix="senoquant-sennet-manifest-"))
        manifest_path = manifest_root / "manifest.tsv"
        manifest_path.write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")

        try:
            command = [
                "sennet-clt",
                "transfer",
                "manifest",
                str(manifest_path),
                "--destination",
                clt_destination,
            ]
            transfer = self._run_command(command)
            if transfer.returncode != 0:
                stderr = (transfer.stderr or "").strip()
                stdout = (transfer.stdout or "").strip()
                detail = stderr or stdout or "Unknown transfer error."
                raise RuntimeError(f"sennet-clt transfer failed: {detail}")

            if staging_dir is not None:
                self._merge_directory(staging_dir, destination_path)
        finally:
            shutil.rmtree(manifest_root, ignore_errors=True)
            if staging_dir is not None:
                shutil.rmtree(staging_dir, ignore_errors=True)

        return {
            "dataset_count": len(dataset_list),
            "file_count": len(manifest_lines),
            "destination": str(destination_path),
        }

    def _fetch_dataset_entity(self, dataset_id: str, *, token: str | None) -> dict[str, Any]:
        """Fetch full entity metadata for a single dataset identifier.

        Parameters
        ----------
        dataset_id : str
            SenNet dataset identifier to resolve through Entity API.
        token : str or None
            Optional bearer token for authenticated requests.

        Returns
        -------
        dict of str to Any
            Parsed entity payload. Empty when response shape is unexpected.
        """
        encoded = quote(dataset_id, safe="")
        url = f"{self.ENTITY_API_URL}/entities/{encoded}"
        payload = self._fetch_json(url, params=None, token=token)
        if isinstance(payload, dict):
            return payload
        return {}

    def _fetch_json(
        self,
        url: str,
        *,
        params: dict[str, str] | None,
        token: str | None,
    ) -> object:
        """Fetch JSON from a SenNet endpoint.

        Parameters
        ----------
        url : str
            Base endpoint URL.
        params : dict of str to str or None
            Optional query-string parameters.
        token : str or None
            Optional bearer token for authenticated requests.

        Returns
        -------
        object
            Parsed JSON payload (dict, list, or primitive).

        Raises
        ------
        RuntimeError
            If network access fails or response parsing is not JSON.
        """
        if params:
            query = urlencode(params)
            request_url = f"{url}?{query}"
        else:
            request_url = url

        headers = {"Accept": "application/json"}
        cleaned_token = (token or "").strip()
        if cleaned_token:
            headers["Authorization"] = f"Bearer {cleaned_token}"

        request = Request(request_url, headers=headers)
        try:
            with urlopen(request, timeout=self._request_timeout) as response:
                data = response.read()
        except Exception as exc:  # pragma: no cover - network/runtime dependent
            raise RuntimeError(f"Failed to query SenNet API: {exc}") from exc

        try:
            return json.loads(data.decode("utf-8"))
        except Exception as exc:  # pragma: no cover - malformed payload edge case
            raise RuntimeError("SenNet API returned non-JSON data.") from exc

    def _post_json(
        self,
        url: str,
        *,
        payload: dict[str, Any],
        token: str | None,
    ) -> object:
        """POST JSON payload to a SenNet endpoint and parse JSON response.

        Parameters
        ----------
        url : str
            Endpoint URL.
        payload : dict of str to Any
            JSON-serializable request body.
        token : str or None
            Optional bearer token for authenticated requests.

        Returns
        -------
        object
            Parsed JSON payload (dict, list, or primitive).

        Raises
        ------
        RuntimeError
            If network access fails or response parsing is not JSON.
        """
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        cleaned_token = (token or "").strip()
        if cleaned_token:
            headers["Authorization"] = f"Bearer {cleaned_token}"

        data = json.dumps(payload).encode("utf-8")
        request = Request(url, data=data, headers=headers, method="POST")
        try:
            with urlopen(request, timeout=self._request_timeout) as response:
                raw = response.read()
        except Exception as exc:  # pragma: no cover - network/runtime dependent
            raise RuntimeError(f"Failed to query SenNet API: {exc}") from exc

        try:
            return json.loads(raw.decode("utf-8"))
        except Exception as exc:  # pragma: no cover - malformed payload edge case
            raise RuntimeError("SenNet API returned non-JSON data.") from exc

    def _iter_dataset_records(self, payload: object) -> Iterable[dict[str, Any]]:
        """Yield normalized dataset-like records from SenNet payloads.

        Parameters
        ----------
        payload : object
            Raw response payload from SenNet endpoints.

        Yields
        ------
        dict of str to Any
            Dataset records normalized to the best-available dictionary shape.

        Notes
        -----
        This parser intentionally targets the observed SenNet response shapes:

        - ``param-search`` endpoints return a top-level list of records.
        - ``/search`` endpoint returns Elasticsearch-style
          ``{"hits": {"hits": [...]}}`` payloads.
        """
        if isinstance(payload, list):
            for item in payload:
                record = self._record_from_item(item)
                if record is not None:
                    yield record
            return

        if not isinstance(payload, dict):
            return

        hits_wrapper = payload.get("hits")
        if isinstance(hits_wrapper, list):
            for item in hits_wrapper:
                record = self._record_from_item(item)
                if record is not None:
                    yield record
            return

        if isinstance(hits_wrapper, dict):
            inner_hits = hits_wrapper.get("hits")
            if isinstance(inner_hits, list):
                for item in inner_hits:
                    record = self._record_from_item(item)
                    if record is not None:
                        yield record
                return

        record = self._record_from_item(payload)
        if record is not None:
            yield record

    def _extract_supported_paths_from_globus(
        self,
        dataset_id: str,
        *,
        token: str | None,
    ) -> list[str]:
        """Resolve supported dataset file paths via SenNet Ingest + Globus ls.

        Parameters
        ----------
        dataset_id : str
            SenNet dataset identifier to resolve.
        token : str or None
            Optional bearer token used when calling the Ingest endpoint.

        Returns
        -------
        list of str
            Normalized dataset-relative paths with supported extensions.

        Notes
        -----
        This fallback is used when Search API records do not include a usable
        file list (for example, some ``PhenoCycler`` datasets). It requires:

        - ``globus`` CLI to be installed and in ``PATH``.
        - Active Globus login (`globus whoami` succeeds).
        """
        if not self._can_list_globus_paths():
            return []

        target = self._fetch_globus_target_for_dataset(dataset_id, token=token)
        if target is None:
            return []

        endpoint_uuid, rel_path = target
        candidates = self._list_globus_paths(endpoint_uuid, rel_path)
        supported: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            normalized = self._normalize_manifest_path(candidate)
            if not normalized:
                continue
            if self._matching_supported_extension(normalized) is None:
                continue
            if normalized in seen:
                continue
            seen.add(normalized)
            supported.append(normalized)
        return supported

    def _fetch_globus_target_for_dataset(
        self,
        dataset_id: str,
        *,
        token: str | None,
    ) -> tuple[str, str] | None:
        """Fetch Globus endpoint UUID and dataset root path for a dataset.

        Parameters
        ----------
        dataset_id : str
            SenNet dataset identifier.
        token : str or None
            Optional bearer token for authenticated requests.

        Returns
        -------
        tuple of (str, str) or None
            ``(globus_endpoint_uuid, rel_path)`` when resolvable, otherwise
            ``None``.
        """
        payload = self._post_json(
            f"{self.INGEST_API_URL}/entities/file-system-rel-path",
            payload=[dataset_id],
            token=token,
        )
        if not isinstance(payload, list):
            return None

        for item in payload:
            if not isinstance(item, dict):
                continue
            candidate_id = self._text_value(item.get("id"), item.get("sennet_id"), default="")
            if candidate_id != dataset_id:
                continue
            endpoint_uuid = self._text_value(item.get("globus_endpoint_uuid"), default="")
            rel_path = self._text_value(item.get("rel_path"), default="")
            if endpoint_uuid and rel_path:
                return endpoint_uuid, rel_path
        return None

    def _list_globus_paths(self, endpoint_uuid: str, rel_path: str) -> list[str]:
        """List candidate file paths from Globus for a dataset directory.

        Parameters
        ----------
        endpoint_uuid : str
            Globus endpoint UUID returned by SenNet Ingest.
        rel_path : str
            Dataset directory path on the source Globus endpoint.

        Returns
        -------
        list of str
            Candidate file paths discovered from Globus listing output.
        """
        endpoint_ref = f"{endpoint_uuid}:{rel_path}"
        command = [
            "globus",
            "ls",
            endpoint_ref,
            "--recursive",
            "--recursive-depth-limit",
            "25",
            "--format=JSON",
        ]
        response = self._run_command(command)
        if response.returncode != 0:
            return []

        try:
            payload = json.loads((response.stdout or "").strip() or "{}")
        except Exception:
            return []

        return self._candidate_paths_from_globus_listing(payload, base_path=rel_path)

    def _can_list_globus_paths(self) -> bool:
        """Return whether Globus CLI is available and authenticated.

        Returns
        -------
        bool
            ``True`` when ``globus`` executable exists and ``globus whoami``
            succeeds in the current runtime environment.
        """
        if self._globus_ls_ready_cache is not None:
            return self._globus_ls_ready_cache
        if shutil.which("globus") is None:
            self._globus_ls_ready_cache = False
            return False
        probe = self._run_command(["globus", "whoami"])
        self._globus_ls_ready_cache = probe.returncode == 0
        return self._globus_ls_ready_cache

    def _candidate_paths_from_globus_listing(
        self,
        payload: object,
        *,
        base_path: str,
    ) -> list[str]:
        """Extract file-path candidates from ``globus ls --format=JSON`` data.

        Parameters
        ----------
        payload : object
            Parsed JSON payload from ``globus ls``.
        base_path : str
            Dataset directory used as fallback prefix when entries provide only
            file names.

        Returns
        -------
        list of str
            Candidate file paths that can be normalized and extension-filtered.
        """
        entries: list[object]
        if isinstance(payload, dict):
            raw = payload.get("DATA")
            entries = raw if isinstance(raw, list) else []
        elif isinstance(payload, list):
            entries = payload
        else:
            entries = []

        root = self._normalize_manifest_path(base_path) or "/"
        paths: list[str] = []
        for entry in entries:
            if isinstance(entry, str):
                paths.append(entry)
                continue
            if not isinstance(entry, dict):
                continue
            entry_type = self._text_value(entry.get("type"), default="").lower()
            if entry_type and entry_type != "file":
                continue

            explicit_path = self._text_value(
                entry.get("path"),
                entry.get("source_path"),
                default="",
            )
            if explicit_path:
                paths.append(explicit_path)
                continue

            name = self._text_value(
                entry.get("name"),
                entry.get("filename"),
                default="",
            )
            if not name:
                continue
            if name.startswith("/"):
                paths.append(name)
            else:
                paths.append(f"{root.rstrip('/')}/{name.lstrip('/')}")
        return paths

    @staticmethod
    def _record_from_item(item: object) -> dict[str, Any] | None:
        """Normalize a candidate item into a dataset dictionary.

        Parameters
        ----------
        item : object
            Candidate payload item.

        Returns
        -------
        dict of str to Any or None
            Dictionary data when available, otherwise ``None``.
        """
        if not isinstance(item, dict):
            return None
        source = item.get("_source")
        if isinstance(source, dict):
            return source
        return item

    @staticmethod
    def _dataset_id_from_payload(payload: dict[str, Any]) -> str:
        """Extract dataset identifier from SenNet payload.

        Parameters
        ----------
        payload : dict of str to Any
            Dataset summary or entity payload.

        Returns
        -------
        str
            ``sennet_id`` value or an empty string when unavailable.
        """
        value = payload.get("sennet_id")
        if isinstance(value, str) and value.strip():
            return value.strip()
        return ""

    def _dataset_title(
        self,
        summary_payload: dict[str, Any],
        entity_payload: dict[str, Any],
        dataset_id: str,
    ) -> str:
        """Resolve a user-facing dataset title from available metadata.

        Parameters
        ----------
        summary_payload : dict of str to Any
            Dataset summary record from search results.
        entity_payload : dict of str to Any
            Detailed entity payload for the dataset.
        dataset_id : str
            Fallback identifier used when no title-like fields are found.

        Returns
        -------
        str
            Title-like value suitable for UI display.
        """
        metadata = entity_payload.get("metadata")
        summary_metadata = summary_payload.get("metadata")
        if isinstance(metadata, dict):
            for key in ("title", "dataset_name", "description"):
                value = metadata.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        if isinstance(summary_metadata, dict):
            for key in ("title", "dataset_name", "description"):
                value = summary_metadata.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return dataset_id

    @staticmethod
    def _text_value(*values: object, default: str) -> str:
        """Return the first non-empty string from candidate values.

        Parameters
        ----------
        *values : object
            Candidate values to inspect.
        default : str
            Fallback value when no non-empty strings are present.

        Returns
        -------
        str
            First normalized non-empty string or ``default``.
        """
        for value in values:
            if isinstance(value, str) and value.strip():
                return value.strip()
        return default

    def _is_antibody_based_imaging(self, payload: dict[str, Any]) -> bool:
        """Check whether a record is tagged as antibody-based imaging.

        Parameters
        ----------
        payload : dict of str to Any
            Dataset summary payload from SenNet search endpoints.

        Returns
        -------
        bool
            ``True`` when ``dataset_type_hierarchy.first_level`` includes the
            literal SenNet first-level category ``"Antibody-based imaging"``.
        """
        hierarchy = payload.get("dataset_type_hierarchy")
        first_levels: list[str] = []
        if isinstance(hierarchy, dict):
            raw_first = hierarchy.get("first_level")
            if isinstance(raw_first, str):
                first_levels = [raw_first]
            elif isinstance(raw_first, list):
                first_levels = [str(value) for value in raw_first]
        elif isinstance(hierarchy, list):
            first_levels = [str(value) for value in hierarchy]

        target = self.ANTIBODY_FIRST_LEVEL.lower()
        return any(level.strip().lower() == target for level in first_levels)

    def _matches_requested_dataset_type(
        self,
        payload: dict[str, Any],
        requested_types: Sequence[str],
    ) -> bool:
        """Return whether payload dataset type is one of the requested types.

        Parameters
        ----------
        payload : dict of str to Any
            Dataset summary or entity payload.
        requested_types : sequence of str
            Dataset types requested by the caller.

        Returns
        -------
        bool
            ``True`` when payload dataset type is in requested types.
        """
        current = self._text_value(payload.get("dataset_type"), default="")
        requested = {str(name).strip() for name in requested_types if str(name).strip()}
        if not requested:
            return True
        return current in requested

    def _extract_supported_paths(self, payload: object) -> list[str]:
        """Extract unique compatible file paths from arbitrary nested payloads.

        Parameters
        ----------
        payload : object
            Entity payload or nested structure containing file descriptors.

        Returns
        -------
        list of str
            Normalized dataset-relative file paths with supported extensions.
        """
        candidates = self._extract_candidate_paths(payload)
        supported: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            normalized = self._normalize_manifest_path(candidate)
            if not normalized:
                continue
            if self._matching_supported_extension(normalized) is None:
                continue
            if normalized in seen:
                continue
            seen.add(normalized)
            supported.append(normalized)
        return supported

    def _extract_candidate_paths(self, payload: object) -> list[str]:
        """Collect path-like string values from nested dictionaries/lists.

        Parameters
        ----------
        payload : object
            Nested payload to inspect recursively.

        Returns
        -------
        list of str
            Raw candidate path strings before extension filtering.
        """
        paths: list[str] = []

        def walk(value: object) -> None:
            """Recursively traverse nested values and collect path fields.

            Parameters
            ----------
            value : object
                Nested payload node being visited.

            Returns
            -------
            None
                Candidate paths are accumulated in outer-scope ``paths``.
            """
            if isinstance(value, dict):
                for key, child in value.items():
                    key_lower = str(key).strip().lower()
                    if key_lower in self._PATH_FIELD_NAMES and isinstance(child, str):
                        if self._looks_like_file_path(child):
                            paths.append(child)
                    walk(child)
                return
            if isinstance(value, list):
                for child in value:
                    walk(child)

        walk(payload)
        return paths

    def _looks_like_file_path(self, value: str) -> bool:
        """Heuristically determine whether text resembles a file path.

        Parameters
        ----------
        value : str
            Raw path-like value.

        Returns
        -------
        bool
            ``True`` when the value appears to reference a file path.
        """
        text = value.strip()
        if not text:
            return False
        path_text = self._extract_url_path(text)
        lowered = path_text.lower().rstrip("/")
        if any(lowered.endswith(ext) for ext in self._extension_check_order):
            return True
        if "/" in path_text or "\\" in path_text:
            return "." in Path(path_text).name
        return False

    @staticmethod
    def _extract_url_path(value: str) -> str:
        """Extract and decode path segment from URL-like values.

        Parameters
        ----------
        value : str
            URL or plain path string.

        Returns
        -------
        str
            Decoded URL path for HTTP(S) inputs, otherwise the original value.
        """
        parsed = urlparse(value)
        if parsed.scheme in {"http", "https"}:
            return unquote(parsed.path or "")
        return value

    def _normalize_manifest_path(self, value: str) -> str | None:
        """Normalize path text into SenNet manifest-compatible absolute form.

        Parameters
        ----------
        value : str
            Candidate path value from metadata.

        Returns
        -------
        str or None
            Normalized ``/``-prefixed path, or ``None`` if empty.
        """
        path_text = self._extract_url_path(value).strip()
        if not path_text:
            return None
        normalized = path_text.replace("\\", "/")
        if normalized.startswith("./"):
            normalized = normalized[1:]
        if not normalized.startswith("/"):
            normalized = f"/{normalized.lstrip('/')}"
        return normalized

    def _matching_supported_extension(self, path: str) -> str | None:
        """Return the supported extension that matches a path suffix.

        Parameters
        ----------
        path : str
            Candidate normalized file path.

        Returns
        -------
        str or None
            Matching extension or ``None`` if unsupported.
        """
        lowered = path.lower().rstrip("/")
        for ext in self._extension_check_order:
            if lowered.endswith(ext):
                return ext
        return None

    def _build_manifest_lines(self, datasets: Sequence[SenNetDataset]) -> list[str]:
        """Build unique SenNet CLT manifest lines for selected datasets.

        Parameters
        ----------
        datasets : sequence of SenNetDataset
            Selected datasets with compatible file paths.

        Returns
        -------
        list of str
            Manifest entries in ``<sennet_id> <path>`` format.
        """
        lines: list[str] = []
        seen: set[str] = set()
        for dataset in datasets:
            for path in dataset.compatible_paths:
                normalized_path = self._normalize_manifest_path(path)
                if not normalized_path:
                    continue
                line = f"{dataset.sennet_id} {normalized_path}"
                if line in seen:
                    continue
                seen.add(line)
                lines.append(line)
        return lines

    def _resolve_clt_destination(self, destination: Path) -> tuple[str, Path | None]:
        """Resolve transfer destination argument accepted by ``sennet-clt``.

        Parameters
        ----------
        destination : pathlib.Path
            Requested local output directory.

        Returns
        -------
        tuple of (str, pathlib.Path or None)
            Relative destination for CLT and optional staging directory used
            when the requested destination is outside the home directory.
        """
        home = self._home_dir()
        try:
            relative = destination.relative_to(home)
        except ValueError:
            timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            staging = home / "sennet-downloads" / f"senoquant-{timestamp}"
            staging.mkdir(parents=True, exist_ok=True)
            return str(staging.relative_to(home)), staging

        rel_text = str(relative)
        return (rel_text if rel_text else "."), None

    @staticmethod
    def _home_dir() -> Path:
        """Return normalized user home directory.

        Returns
        -------
        pathlib.Path
            Expanded and resolved home directory path.
        """
        return Path.home().expanduser().resolve()

    def _run_command(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        """Execute a subprocess command and capture text output.

        Parameters
        ----------
        args : list of str
            Argument vector for subprocess execution.

        Returns
        -------
        subprocess.CompletedProcess of str
            Completed process with captured ``stdout`` and ``stderr``.
        """
        return subprocess.run(
            args,
            text=True,
            capture_output=True,
            check=False,
        )

    def _merge_directory(self, source: Path, destination: Path) -> None:
        """Recursively move contents from ``source`` into ``destination``.

        Parameters
        ----------
        source : pathlib.Path
            Directory containing staged transfer output.
        destination : pathlib.Path
            Final destination directory for merged files.

        Returns
        -------
        None
            Files are moved in place; duplicate names are deduplicated.
        """
        if not source.exists():
            return
        destination.mkdir(parents=True, exist_ok=True)
        for child in source.iterdir():
            target = destination / child.name
            if child.is_dir():
                self._merge_directory(child, target)
                child.rmdir()
                continue
            resolved_target = self._dedupe_path(target)
            resolved_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(child), str(resolved_target))

    @staticmethod
    def _dedupe_path(target: Path) -> Path:
        """Return a non-conflicting output path by appending numeric suffixes.

        Parameters
        ----------
        target : pathlib.Path
            Desired output file path.

        Returns
        -------
        pathlib.Path
            Original path when unused, else first available suffixed variant.
        """
        if not target.exists():
            return target
        suffix = "".join(target.suffixes)
        stem = target.name[: -len(suffix)] if suffix else target.name
        counter = 1
        while True:
            candidate = target.with_name(f"{stem}_{counter}{suffix}")
            if not candidate.exists():
                return candidate
            counter += 1
