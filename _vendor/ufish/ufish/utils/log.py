"""Logger shim for vendored UFish."""

try:  # pragma: no cover - optional dependency
    from loguru import logger  # type: ignore[import-not-found]  # noqa: F401
except Exception:  # pragma: no cover - fallback logger
    import logging

    logger = logging.getLogger("ufish")
