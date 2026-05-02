"""
Audit logging utilities.

Every tool invocation writes a structured JSONL record to disk and to the
structured logger so it can be forwarded to a SIEM (Splunk, Datadog, etc.).

Design goals:
- Append-only — records are never mutated.
- PII fields are hashed (SHA-256) in persisted records, not stored in clear.
- Each record carries a request_id for correlation across distributed traces.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator
from uuid import UUID

import structlog

from src.config import settings
from src.models.audit import AuditContext

logger = structlog.get_logger(__name__)


def _mask_pii(data: dict[str, Any]) -> dict[str, Any]:
    """Shallow-copy data with PII field values replaced by '<masked>'."""
    masked = dict(data)
    for field in settings.audit.pii_fields_mask_in_logs:
        if field in masked:
            masked[field] = "<masked>"
    return masked


def _sha256_args(arguments: dict[str, Any]) -> str:
    serialised = json.dumps(arguments, sort_keys=True, default=str).encode()
    return hashlib.sha256(serialised).hexdigest()


def _append_audit_record(ctx: AuditContext) -> None:
    try:
        record = ctx.model_dump(mode="json")
        audit_path = Path(settings.audit.audit_log_file)
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        with audit_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except OSError as exc:
        # Never let audit failures block the tool from executing
        logger.warning("audit_write_failed", error=str(exc))


def build_audit_context(
    tool_name: str,
    arguments: dict[str, Any],
    caller_id: str = "anonymous",
    session_id: str | None = None,
) -> AuditContext:
    return AuditContext(
        caller_id=caller_id,
        tool_name=tool_name,
        arguments_hash=_sha256_args(arguments),
        session_id=session_id,
        environment=settings.server.env,
    )


@asynccontextmanager
async def audit_tool_call(
    tool_name: str,
    arguments: dict[str, Any],
    caller_id: str = "anonymous",
) -> AsyncGenerator[AuditContext, None]:
    """
    Async context manager that:
    1. Creates an AuditContext with outcome='pending' and persists it.
    2. Yields the context so the caller can reference the request_id.
    3. Updates the outcome and duration on exit, then persists the final record.
    """
    ctx = build_audit_context(tool_name, arguments, caller_id)
    _append_audit_record(ctx)  # write pending record immediately

    start = time.monotonic()
    final_outcome = "success"
    error_code: str | None = None

    try:
        yield ctx
    except Exception as exc:
        final_outcome = "error"
        error_code = type(exc).__name__
        raise
    finally:
        duration_ms = (time.monotonic() - start) * 1000
        final_ctx = ctx.model_copy(
            update={
                "outcome": final_outcome,
                "error_code": error_code,
                "duration_ms": round(duration_ms, 2),
            }
        )
        _append_audit_record(final_ctx)
        logger.info(
            "tool_call_completed",
            tool=tool_name,
            outcome=final_outcome,
            duration_ms=round(duration_ms, 2),
            request_id=str(ctx.request_id),
        )
