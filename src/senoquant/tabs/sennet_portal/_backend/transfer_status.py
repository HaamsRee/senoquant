"""Status-parsing helpers for SenNet transfer monitoring."""

from __future__ import annotations

import re
from typing import Sequence


def extract_task_ids(stdout: str | None, stderr: str | None) -> list[str]:
    """Extract Globus transfer task IDs from ``sennet-clt`` output text.

    Parameters
    ----------
    stdout : str or None
        Standard output emitted by ``sennet-clt transfer``.
    stderr : str or None
        Standard error emitted by ``sennet-clt transfer``.

    Returns
    -------
    list of str
        Unique task identifiers in appearance order.
    """
    text = "\n".join(part for part in ((stdout or ""), (stderr or "")) if part).strip()
    if not text:
        return []
    matches = re.findall(
        r"^\s*Task ID:\s*([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\s*$",
        text,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    unique: list[str] = []
    seen: set[str] = set()
    for task_id in matches:
        normalized = task_id.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        unique.append(normalized)
    return unique


def aggregate_task_status(tasks: Sequence[dict[str, object]]) -> dict[str, object]:
    """Aggregate per-task Globus payloads into one progress summary.

    Parameters
    ----------
    tasks : sequence of dict of str to object
        Raw JSON payloads from ``globus task show --format json``.

    Returns
    -------
    dict of str to object
        Unified status payload for frontend polling.
    """
    terminal_states = {"SUCCEEDED", "FAILED", "CANCELED", "EXPIRED"}
    total_subtasks = 0
    completed_subtasks = 0
    files = 0
    files_transferred = 0
    speed_bps = 0
    bytes_transferred = 0
    statuses: list[str] = []
    task_rows: list[dict[str, object]] = []

    for payload in tasks:
        status = str(payload.get("status", "")).upper().strip()
        statuses.append(status)
        subtasks_total = int(payload.get("subtasks_total", 0) or 0)
        subtasks_pending = int(payload.get("subtasks_pending", 0) or 0)
        subtasks_retrying = int(payload.get("subtasks_retrying", 0) or 0)
        total_subtasks += subtasks_total
        completed_subtasks += max(0, subtasks_total - subtasks_pending - subtasks_retrying)
        task_files = int(payload.get("files", 0) or 0)
        task_files_transferred = int(payload.get("files_transferred", 0) or 0)
        files += task_files
        files_transferred += task_files_transferred
        speed_bps += int(payload.get("effective_bytes_per_second", 0) or 0)
        bytes_transferred += int(payload.get("bytes_transferred", 0) or 0)
        task_rows.append(
            {
                "task_id": str(payload.get("task_id", "")).strip(),
                "status": status,
                "files": task_files,
                "files_transferred": task_files_transferred,
                "subtasks_total": subtasks_total,
                "subtasks_pending": subtasks_pending,
                "subtasks_succeeded": int(payload.get("subtasks_succeeded", 0) or 0),
                "subtasks_failed": int(payload.get("subtasks_failed", 0) or 0),
                "speed_bps": int(payload.get("effective_bytes_per_second", 0) or 0),
                "bytes_transferred": int(payload.get("bytes_transferred", 0) or 0),
            }
        )

    if files > 0:
        progress_percent = int(round((files_transferred / files) * 100))
    elif total_subtasks > 0:
        progress_percent = int(round((completed_subtasks / total_subtasks) * 100))
    else:
        progress_percent = 0
    all_complete = all(status in terminal_states for status in statuses)
    any_failed = any(status in {"FAILED", "CANCELED", "EXPIRED"} for status in statuses)
    if all(status == "SUCCEEDED" for status in statuses):
        overall = "SUCCEEDED"
    elif all_complete and any_failed:
        overall = "FAILED"
    elif any(status == "ACTIVE" for status in statuses):
        overall = "ACTIVE"
    else:
        overall = statuses[0] if statuses else "UNKNOWN"

    return {
        "task_count": len(tasks),
        "overall_status": overall,
        "all_complete": all_complete,
        "all_succeeded": all_complete and not any_failed,
        "any_failed": any_failed,
        "progress_percent": max(0, min(100, progress_percent)),
        "files": files,
        "files_transferred": files_transferred,
        "subtasks_total": total_subtasks,
        "subtasks_completed": completed_subtasks,
        "speed_bps": speed_bps,
        "bytes_transferred": bytes_transferred,
        "tasks": task_rows,
    }


__all__ = ["aggregate_task_status", "extract_task_ids"]
