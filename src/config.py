"""
Central configuration loaded from environment variables.
Never hard-code credentials — always use .env or a secrets manager.
"""

from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class PMSConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PMS_", env_file=".env", extra="ignore")

    adapter: str = "mock"
    base_url: str = ""
    api_key: str = Field(default="", repr=False)
    property_id: str = ""
    timeout_seconds: float = 10.0
    rate_limit_rps: float = 5.0


class CRMConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CRM_", env_file=".env", extra="ignore")

    adapter: str = "mock"
    base_url: str = ""
    api_key: str = Field(default="", repr=False)
    instance_url: str = ""
    timeout_seconds: float = 10.0
    rate_limit_rps: float = 3.0


class ServerConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HOTEL_MCP_", env_file=".env", extra="ignore")

    server_name: str = "hotel-mcp-server"
    log_level: str = "INFO"
    env: str = "development"


class AuthConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MCP_", env_file=".env", extra="ignore")

    require_auth: bool = False
    allowed_tokens: list[str] = Field(default_factory=list)


class AuditConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    audit_log_file: str = "./audit.jsonl"
    audit_include_response_hash: bool = True
    pii_fields_mask_in_logs: list[str] = Field(
        default=["email", "phone", "passport_number", "credit_card"],
        exclude=True,
    )


class Settings(BaseSettings):
    """Aggregated top-level settings."""
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    server: ServerConfig = Field(default_factory=ServerConfig)
    pms: PMSConfig = Field(default_factory=PMSConfig)
    crm: CRMConfig = Field(default_factory=CRMConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    audit: AuditConfig = Field(default_factory=AuditConfig)


# Module-level singleton — import this everywhere
settings = Settings()
