from functools import lru_cache
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from urllib.parse import urlsplit


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
    local_mail_capture: bool = False
    sportlink_client_id: str = ''
    sportlink_club_code: str = ''

    @model_validator(mode='after')
    def production_database(self):
        if not self.demo_mode and not self.database_url.startswith('postgresql'):
            raise ValueError('Production requires PostgreSQL')
        if self.local_mail_capture:
            url = urlsplit(self.base_url)
            if (not self.demo_mode or self.cookie_secure or url.scheme != 'http'
                    or url.hostname not in ('localhost', '127.0.0.1', '::1')
                    or self.smtp_host not in ('mailpit', 'localhost', '127.0.0.1', '::1')
                    or self.smtp_port != 1025 or self.smtp_username or self.smtp_password
                    or not self.smtp_from.endswith('@example.invalid')):
                raise ValueError('Local capture requires HTTP loopback, demo mode, insecure local cookies, '
                                 'Mailpit on port 1025 without credentials and an example.invalid sender')
        return self

    @property
    def mail_ready(self):
        return self.local_mail_capture or bool(self.smtp_host and self.smtp_username and self.smtp_password and self.smtp_from)


@lru_cache
def settings():
    return Settings()
