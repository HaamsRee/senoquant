"""Fresh-process checks for the existing Python system-trust startup hook."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import pytest


_STARTUP_CHECK = r"""
import importlib.abc
import importlib.util
import ssl
import sys
import types

sys.path.insert(0, sys.argv[1])
scenario = sys.argv[2]

from pip._vendor import truststore
from pip_system_certs import wrapt_requests

original_context_type = ssl.SSLContext
if scenario == "missing_hook":
    sys.modules.pop("pip_system_certs.bootstrap", None)
elif scenario == "inactive_hook":
    truststore.extract_from_ssl()
    assert wrapt_requests._injected  # A stale success flag must not pass the guard.
elif scenario == "missing_backend":
    sys.modules.pop("pip._vendor.truststore", None)
elif scenario == "context_failure":
    def broken_context():
        raise OSError("simulated system trust initialization failure")
    ssl.create_default_context = broken_context
elif scenario in {"no_certificate_check", "no_hostname_check"}:
    context = ssl.create_default_context()
    context.check_hostname = False
    if scenario == "no_certificate_check":
        context.verify_mode = ssl.CERT_NONE
    ssl.create_default_context = lambda: context

expected_context_type = ssl.SSLContext
widget_imports = []

class WidgetStub(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "senoquant._widget":
            widget_imports.append(fullname)
            return importlib.util.spec_from_loader(fullname, self)

    def create_module(self, spec):
        return types.ModuleType(spec.name)

    def exec_module(self, module):
        module.SenoQuantWidget = object()

sys.meta_path.insert(0, WidgetStub())

try:
    import senoquant
except RuntimeError as exc:
    assert scenario != "active", str(exc)
    assert "pip-system-certs" in str(exc)
    assert "restart Python/napari" in str(exc)
    assert not widget_imports, "Trust must be checked before loading the widget."
else:
    assert scenario == "active", "Startup accepted unavailable or disabled trust."
    assert widget_imports == ["senoquant._widget"]
    assert senoquant.SenoQuantWidget is sys.modules["senoquant._widget"].SenoQuantWidget

assert ssl.SSLContext is expected_context_type, "Plugin import must not patch SSL."
if scenario == "active":
    assert expected_context_type is original_context_type
print("startup check passed:", scenario)
"""


@pytest.mark.parametrize(
    "scenario",
    [
        "active",
        "missing_hook",
        "inactive_hook",
        "missing_backend",
        "context_failure",
        "no_certificate_check",
        "no_hostname_check",
    ],
)
def test_system_trust_before_plugin_load(scenario: str, tmp_path: Path) -> None:
    """Accept verified system trust and reject failures before loading the UI."""
    source_root = Path(__file__).resolve().parents[2] / "src"
    result = subprocess.run(
        [sys.executable, "-B", "-c", _STARTUP_CHECK, str(source_root), scenario],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
