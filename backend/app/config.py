from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    # .env is read locally; in Docker plain environment variables are used.
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    database_url: str
    test_database_url: str | None = None

    kt_url: str | None = None
    kt_api_key: str | None = None
    kt_domain: str | None = None
    kt_group: str | None = None
    kt_traffic_source: str | None = None
    # Prepended to every new campaign name, e.g. "test_iudkin_"; empty = none
    campaign_name_prefix: str = ""

    app_login: str
    app_password: str
    jwt_secret: str
    access_ttl_min: int = 15
    refresh_ttl_days: int = 7
    cookie_secure: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
