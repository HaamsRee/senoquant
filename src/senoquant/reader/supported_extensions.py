"""Supported image-extension helpers for the SenoQuant reader."""

from __future__ import annotations


_FALLBACK_SUPPORTED_IMAGE_EXTENSIONS: tuple[str, ...] = (
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


def supported_image_extensions() -> tuple[str, ...]:
    """Return extensions supported by SenoQuant's BioIO-backed reader.

    Returns
    -------
    tuple of str
        Normalized lowercase extensions in ``.ext`` format. Values are
        discovered dynamically from BioIO plugin registration and augmented
        with a stable fallback set to preserve compatibility when plugin
        discovery is unavailable.

    Notes
    -----
    This function is intentionally defensive:

    - If BioIO is unavailable or plugin introspection fails, fallback
      extensions are returned.
    - Fallback values are always merged so common microscopy formats remain
      available even when plugin metadata is incomplete.
    """
    discovered: set[str] = set(_FALLBACK_SUPPORTED_IMAGE_EXTENSIONS)
    try:
        import bioio
    except Exception:
        return tuple(sorted(discovered, key=len, reverse=True))

    try:
        plugins_by_extension = bioio.plugins.get_plugins(use_cache=True)
    except Exception:
        return tuple(sorted(discovered, key=len, reverse=True))

    for extension_key in plugins_by_extension:
        normalized = _normalize_extension(extension_key)
        if normalized is None:
            continue
        discovered.add(normalized)
    return tuple(sorted(discovered, key=len, reverse=True))


def _normalize_extension(value: object) -> str | None:
    """Normalize a plugin key into a canonical extension.

    Parameters
    ----------
    value : object
        Candidate extension key from BioIO plugin metadata.

    Returns
    -------
    str or None
        Lowercase extension in ``.ext`` format, or ``None`` when the input is
        not extension-like.
    """
    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    if not text:
        return None
    if not text.startswith("."):
        text = f".{text.lstrip('.')}"
    return text


__all__ = ["supported_image_extensions"]
