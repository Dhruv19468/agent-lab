from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Every setting the backend reads, mapped 1:1 from environment variables / backend/.env.

    Locally the values come from backend/.env. On Azure they come from the Container App's
    environment variables and secrets (deploy/azure/setup.ps1 sets them).
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App metadata ---
    app_name: str = Field(default="Agent-Lab")
    project_description: str = Field(default="Practice agent platform.")
    environment: str = Field(default="development")
    api_prefix: str = Field(default="/api")
    root_path: str = Field(default="")
    docs_path: str = Field(default="/docs")
    openapi_path: str = Field(default="/openapi.json")
    include_openapi_docs: bool = Field(default=True)

    # --- Startup behaviour ---
    run_alembic_on_startup: bool = Field(default=False)
    # Create the built-in tools, the "BRD to Test Plan" skill and the "Test Plan Agent" if missing.
    sync_catalog_on_startup: bool = Field(default=True)

    # --- Database ---
    database_url: str = Field(default="postgresql+asyncpg://postgres:postgres@localhost:5432/agent_lab_db")
    database_schema: str = Field(default="public")

    # --- CORS ---
    cors_origins: str = Field(default="http://localhost:3000")

    # --- Azure OpenAI (models deployed in Azure AI Foundry) ---
    azure_openai_endpoint: str = Field(default="")
    azure_openai_api_key: SecretStr = Field(default=SecretStr(""))
    azure_openai_deployment: str = Field(default="")
    azure_openai_timeout_seconds: float = Field(default=180.0)
    azure_openai_max_retries: int = Field(default=2)
    # The model that scores test plans. Empty = the same deployment as the agent.
    eval_judge_deployment: str = Field(default="")
    # Extra deployments to offer in the model dropdowns, comma-separated: "gpt-4.1,o4-mini".
    # With Foundry configured, the project's deployments are listed automatically as well.
    azure_openai_deployments: str = Field(default="")

    # --- Azure AI Foundry (publish registers the agent there) ---
    # The project endpoint from the Foundry portal's overview page:
    #   https://<resource>.services.ai.azure.com/api/projects/<project>
    # Empty = publish only inside Agent Lab.
    foundry_project_endpoint: str = Field(default="")
    # "entra": your `az login` locally, the Container App's managed identity on Azure (recommended).
    # "api_key": send FOUNDRY_API_KEY as an api-key header.
    foundry_auth_mode: str = Field(default="entra")
    foundry_api_key: SecretStr = Field(default=SecretStr(""))
    foundry_entra_scope: str = Field(default="https://ai.azure.com/.default")
    foundry_timeout_seconds: float = Field(default=60.0)

    # --- Data the agent's file tools can see ---
    # "local": the folder AGENT_DATA_DIR. "blob": the Azure Blob container below (used on Azure).
    agent_storage: str = Field(default="local")
    azure_storage_account_url: str = Field(default="")  # https://<account>.blob.core.windows.net
    azure_storage_container: str = Field(default="agentdata")
    # Optional, for testing Blob from a laptop without `az login`. On Azure the managed identity is used.
    azure_storage_connection_string: SecretStr = Field(default=SecretStr(""))
    # Locally: the repo's data/ folder. On Azure: the Azure Files share mounted at /data.
    agent_data_dir: str = Field(default="../data")

    @field_validator("azure_openai_endpoint")
    @classmethod
    def _check_endpoint(cls, value: str) -> str:
        value = value.strip()
        if not value:
            return value
        if "/openai/v1" not in value:
            raise ValueError(
                "AZURE_OPENAI_ENDPOINT must be the v1 base URL, e.g. "
                "https://<resource>.openai.azure.com/openai/v1/"
            )
        return value if value.endswith("/") else value + "/"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def azure_openai_configured(self) -> bool:
        return bool(
            self.azure_openai_endpoint
            and self.azure_openai_api_key.get_secret_value()
            and self.azure_openai_deployment
        )

    @property
    def configured_deployments(self) -> list[str]:
        """AZURE_OPENAI_DEPLOYMENT first, then AZURE_OPENAI_DEPLOYMENTS, without duplicates."""
        names = [self.azure_openai_deployment, *self.azure_openai_deployments.split(",")]
        return list(dict.fromkeys(name.strip() for name in names if name.strip()))

    @property
    def foundry_enabled(self) -> bool:
        return bool(self.foundry_project_endpoint.strip())

    @property
    def judge_deployment(self) -> str:
        return self.eval_judge_deployment or self.azure_openai_deployment

    @property
    def agent_data_path(self) -> Path:
        return Path(self.agent_data_dir).expanduser().resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()
