"""Audit context attached to every tool invocation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class AuditContext(BaseModel):
    """Immutable record of who called what and when.

    Written to the audit log before the tool executes, so failures are
    still traceable. Sensitive fields in the arguments are masked before
    persistence (see utils.audit.mask_pii).
    """

    request_id: UUID = Field(default_factory=uuid4)
    timestamp_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    caller_id: str  # token sub / API-key fingerprint / "anonymous"
    tool_name: str
    arguments_hash: str  # SHA-256 of the serialised arguments (not the raw args)
    source_ip: str | None = None
    session_id: str | None = None
    environment: str = "development"
    outcome: Literal["pending", "success", "error"] = "pending"
    error_code: str | None = None
    duration_ms: float | None = None

    class Config:
        frozen = True  # audit records must not be mutated after creation
