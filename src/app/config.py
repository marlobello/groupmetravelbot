from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    azure_openai_endpoint: str
    azure_openai_deployment: str = "gpt-4o"
    storage_account_name: str
    storage_container_name: str = "trips"
    groupme_bot_id: str
    bot_trigger_keyword: str = "@sensei"
    azure_client_id: str | None = None
    webhook_secret: str = ""
    web_access_key: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
