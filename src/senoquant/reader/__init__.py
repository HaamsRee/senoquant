"""Reader package for SenoQuant."""

from .core import get_reader
from .supported_extensions import supported_image_extensions

__all__ = ["get_reader", "supported_image_extensions"]
