"""Config loader — YAML for defaults, .env for secrets/overrides."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AzureSettings(BaseSettings):
    """All Azure resource identifiers. Populated from .env after Bicep deploy."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="AZURE_",
        extra="ignore",
    )

    storage_account_name: str = Field(..., description="ADLS Gen2 account")
    key_vault_name: str
    sql_server_fqdn: str
    sql_database_name: str = "bankpulsedb"


class AppSettings(BaseSettings):
    """Runtime settings merged from configs/<env>.yaml."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "dev"
    log_level: str = "INFO"
    data_dir: Path = Path("./data")

    # Ingestion batching
    upload_batch_size: int = 50_000
    max_concurrent_uploads: int = 8

    # Synthetic data defaults
    default_customer_count: int = 50_000
    default_days: int = 90
    default_fraud_rate: float = 0.008


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text()) or {}


@lru_cache
def get_azure_settings() -> AzureSettings:
    return AzureSettings()  # type: ignore[call-arg]


@lru_cache
def get_app_settings(env: str = "dev") -> AppSettings:
    yaml_overrides = _load_yaml(Path(f"configs/{env}.yaml"))
    return AppSettings(**yaml_overrides)
