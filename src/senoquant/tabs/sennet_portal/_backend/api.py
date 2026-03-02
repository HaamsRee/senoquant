"""HTTP API helper mixin for the SenNet Portal backend."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


class SenNetPortalApiMixin:
    """Mixin containing HTTP request helpers for SenNet APIs."""

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

        request = Request(request_url, headers=headers, method="GET")
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
        payload: dict[str, Any] | list[Any],
        token: str | None,
    ) -> object:
        """POST JSON payload to a SenNet endpoint and parse JSON response.

        Parameters
        ----------
        url : str
            Endpoint URL.
        payload : dict of str to Any or list of Any
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


__all__ = ["SenNetPortalApiMixin"]
