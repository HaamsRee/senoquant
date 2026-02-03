"""Public UFish utility API for spot enhancement.

This package exposes a minimal stable surface used by the Spots tab:

``UFishConfig``
    Configuration dataclass for model initialization and weight loading.
``enhance_image``
    Convenience function that runs UFish enhancement on an input image.
"""

from .core import UFishConfig, enhance_image

__all__ = ["UFishConfig", "enhance_image"]
