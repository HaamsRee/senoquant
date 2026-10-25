"""SenoQuant napari plugin package."""

import ssl as _ssl
import sys as _sys

# Validate the environment's startup hook without patching SSL during plugin import.
try:
    if "pip_system_certs.bootstrap" not in _sys.modules:
        raise RuntimeError("pip-system-certs did not run at Python startup.")
    _truststore = _sys.modules["pip._vendor.truststore"]
    _context = _ssl.create_default_context()
    if (
        not isinstance(_context, _truststore.SSLContext)
        or _context.verify_mode != _ssl.CERT_REQUIRED
        or not _context.check_hostname
    ):
        raise RuntimeError("The default SSL context is not using verified system trust.")
except Exception as _exc:
    raise RuntimeError(
        "SenoQuant requires active system certificate support. Install "
        "pip-system-certs in this Python environment, then restart Python/napari."
    ) from _exc

try:
    from importlib.metadata import version
    __version__ = version("senoquant")
except Exception:
    __version__ = "1.0.0b13.post2"  # Fallback for development

from ._widget import SenoQuantWidget
__all__ = ["SenoQuantWidget"]
