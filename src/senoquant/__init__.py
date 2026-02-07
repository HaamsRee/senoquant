"""SenoQuant napari plugin package."""

try:
    from importlib.metadata import version
    __version__ = version("senoquant")
except Exception:
    __version__ = "1.0.0b5"  # Fallback for development

from ._widget import SenoQuantWidget
__all__ = ["SenoQuantWidget"]
