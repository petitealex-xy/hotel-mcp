"""
Configuration via plain os.environ — no pydantic-settings, no parsing errors.
Works identically on local, Railway, Hetzner, and Docker.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def _env_bool(key: str, default: bool = False) -> bool:
    return _env(key, str(default)).lower() in ("true", "1", "yes")


def _env_float(key: str, default: float) -> float:
    try:
        return float(_env(key, str(default)))
    except ValueError:
        return default


@dataclass
class PMSConfig:
    adapter: str = field(default_factory=lambda: _env("PMS_ADAPTER", "mock"))
    base_url: str = field(default_factory=lambda: _env("PMS_BASE_URL", ""))
    api_key: str = field(default_factory=lambda: _env("PMS_API_KEY", ""))
    property_id: str = field(default_factory=lambda: _env("PMS_PROPERTY_ID", ""))
    timeout_seconds: float = field(default_factory=lambda: _env_float("PMS_TIMEOUT_SECONDS", 10.0))
    rate_limit_rps: float = field(default_factory=lambda: _env_float("PMS_RATE_LIMIT_RPS", 5.0))


@dataclass
class CRMConfig:
    adapter: str = field(default_factory=lambda: _env("CRM_ADAPTER", "mock"))
    base_url: str = field(default_factory=lambda: _env("CRM_BASE_URL", ""))
    api_key: str = field(default_factory=lambda: _env("CRM_API_KEY", ""))
    instance_url: str = field(default_factory=lambda: _env("CRM_INSTANCE_URL", ""))
    timeout_seconds: float = field(default_factory=lambda: _env_float("CRM_TIMEOUT_SECONDS", 10.0))
    rate_limit_rps: float = field(default_factory=lambda: _env_float("CRM_RATE_LIMIT_RPS", 3.0))


@dataclass
class ServerConfig:
    server_name: str = field(default_factory=lambda: _env("HOTEL_MCP_SERVER_NAME", "hotel-mcp-server"))
    log_level: str = field(default_factory=lambda: _env("HOTEL_MCP_LOG_LEVEL", "INFO"))
    env: str = field(default_factory=lambda: _env("HOTEL_MCP_ENV", "development"))


@dataclass
class AuthConfig:
    require_auth: bool = field(default_factory=lambda: _env_bool("MCP_REQUIRE_AUTH", False))


@dataclass
class AuditConfig:
    audit_log_file: str = field(default_factory=lambda: _env("AUDIT_LOG_FILE", "./audit.jsonl"))
    audit_include_response_hash: bool = field(
        default_factory=lambda: _env_bool("AUDIT_INCLUDE_RESPONSE_HASH", True)
    )
    pii_fields_mask_in_logs: list[str] = field(
        default_factory=lambda: ["email", "phone", "passport_number", "credit_card"]
    )


@dataclass
class Settings:
    server: ServerConfig = field(default_factory=ServerConfig)
    pms: PMSConfig = field(default_factory=PMSConfig)
    crm: CRMConfig = field(default_factory=CRMConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)
    audit: AuditConfig = field(default_factory=AuditConfig)


# Load .env file manually if it exists (local dev only)
def _load_dotenv() -> None:
    env_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    if not os.path.exists(env_file):
        return
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


_load_dotenv()

settings = Settings()
