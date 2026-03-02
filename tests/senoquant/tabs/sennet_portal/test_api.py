"""Tests for SenNet Portal HTTP API helpers."""

from __future__ import annotations

from senoquant.tabs.sennet_portal.backend import SenNetPortalBackend
from senoquant.tabs.sennet_portal._backend import api as api_module


def test_fetch_json_uses_explicit_get_method(monkeypatch) -> None:
    """Build urllib request with explicit GET to prevent accidental verb drift."""
    backend = SenNetPortalBackend(request_timeout=12.5)
    captured: dict[str, object] = {}

    class _FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def read(self) -> bytes:
            return b'{"ok": true}'

    def fake_urlopen(request, timeout: float):
        captured["request"] = request
        captured["timeout"] = timeout
        return _FakeResponse()

    monkeypatch.setattr(api_module, "urlopen", fake_urlopen)

    payload = backend._fetch_json(
        "https://example.test/search",
        params={"dataset_sennet_id": "SNT1"},
        token="api-token",
    )

    assert payload == {"ok": True}
    request = captured["request"]
    assert request.full_url == "https://example.test/search?dataset_sennet_id=SNT1"
    assert request.method == "GET"
    assert request.get_header("Accept") == "application/json"
    assert request.get_header("Authorization") == "Bearer api-token"
    assert captured["timeout"] == 12.5
