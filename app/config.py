from functools import lru_cache
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    database_url: str = 'sqlite:///./development.db'
    secret_key: str = Field(min_length=32)
    base_url: str = 'http://127.0.0.1:8000'
    cookie_secure: bool = True
    demo_mode: bool = True
    canteen_opening_hour: int = Field(default=8, ge=0, le=23)
    demo_staffing_enabled: bool = False
    smtp_host: str = ''
    smtp_port: int = 587
    smtp_username: str = ''
    smtp_password: str = ''
    smtp_from: str = ''
    sportlink_client_id: str = ''
    sportlink_club_code: str = ''

    @model_validator(mode='after')
    def production_database(self):
        if not self.demo_mode and not self.database_url.startswith('postgresql'):
            raise ValueError('Production requires PostgreSQL')
        return self

    @property
    def mail_ready(self):
        return bool(self.smtp_host and self.smtp_username and self.smtp_password and self.smtp_from)


@lru_cache
def settings():
    return Settings()
