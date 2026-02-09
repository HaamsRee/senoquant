"""JSON Schema helpers for model details manifests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import ValidationError
from jsonschema import validate as jsonschema_validate


MODEL_DETAILS_JSON_SCHEMA_PATH = Path(__file__).with_name(
    "model_details.schema.json"
)


def load_model_details_json_schema() -> dict[str, Any]:
    """Load the JSON Schema for model ``details.json`` payloads."""
    with MODEL_DETAILS_JSON_SCHEMA_PATH.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if isinstance(payload, dict):
        return payload
    raise ValueError("Invalid model details schema payload.")


def validate_model_details(
    payload: object,
    *,
    details_path: Path | None = None,
    require_tasks: bool = False,
) -> dict[str, Any]:
    """Validate a parsed model-details payload against the schema.

    Parameters
    ----------
    payload : object
        Parsed JSON payload to validate.
    details_path : pathlib.Path or None, optional
        Source path used to enrich validation error messages.
    require_tasks : bool, optional
        Whether segmentation-style ``tasks`` metadata is required.

    Returns
    -------
    dict[str, Any]
        Validated payload as a dictionary.
    """
    if not isinstance(payload, dict):
        source = str(details_path) if details_path is not None else "details payload"
        raise ValueError(f"Invalid model details at {source}: expected JSON object.")

    schema = load_model_details_json_schema()
    try:
        jsonschema_validate(instance=payload, schema=schema)
    except ValidationError as exc:
        source = str(details_path) if details_path is not None else "details payload"
        raise ValueError(f"Invalid model details at {source}: {exc.message}") from exc

    if require_tasks:
        tasks = payload.get("tasks")
        if not isinstance(tasks, dict):
            source = str(details_path) if details_path is not None else "details payload"
            raise ValueError(
                f"Invalid model details at {source}: segmentation models must define 'tasks'."
            )
        for task in ("nuclear", "cytoplasmic"):
            if task not in tasks:
                source = (
                    str(details_path) if details_path is not None else "details payload"
                )
                raise ValueError(
                    f"Invalid model details at {source}: missing tasks.{task}."
                )

    return payload
