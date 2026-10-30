"""Configuration with paths independent of the working directory."""
from functools import lru_cache
from pathlib import Path
import os
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    DATABASE_URL: str = ""
    POSTGRESS_DB_USER: str = ""
    POSTGRESS_DB_PASSWORD: str = ""
    POSTGRESS_DB_PORT: int = 5432
    POSTGRESS_DB_HOST: str = "localhost"
    POSTGRESS_DB_NAME: str = ""
    TRACK_ENCRYPTION_KEY: str = ""
    DATA_DIR: Path = BASE_DIR / "data"
    MEDIA_DIR: Path = BASE_DIR / "media" / "tracks"
    CLAMSCAN_PATH: str = "clamscan"
    CLAMAV_DATABASE_DIR: str = ""
    CLAMAV_HOST: str = ""
    CLAMAV_PORT: int = 3310
    FFMPEG_PATH: str = "ffmpeg"
    MAX_UPLOAD_MB: int = 25
    MAX_USER_STORAGE_MB: int = 1024
    COOKIE_SECURE: bool = False
    SESSION_HOURS: int = 12
    AUTO_CREATE_TABLES: bool = True
    ALLOWED_HOSTS: str = "localhost,127.0.0.1,[::1],testserver"

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    @property
    def database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        if self.POSTGRESS_DB_USER and self.POSTGRESS_DB_NAME:
            user = quote_plus(self.POSTGRESS_DB_USER)
            password = quote_plus(self.POSTGRESS_DB_PASSWORD)
            return f"postgresql+asyncpg://{user}:{password}@{self.POSTGRESS_DB_HOST}:{self.POSTGRESS_DB_PORT}/{self.POSTGRESS_DB_NAME}"
        return f"sqlite+aiosqlite:///{(self.DATA_DIR / 'app.db').as_posix()}"

    @property
    def media_dir(self) -> Path:
        return self.MEDIA_DIR.resolve()

    @property
    def cookie_secure(self) -> bool:
        return self.COOKIE_SECURE or self.ENVIRONMENT == "production"

    def encryption_key(self) -> bytes:
        """Create a local development key once; never rotate it implicitly."""
        from cryptography.fernet import Fernet

        if self.TRACK_ENCRYPTION_KEY:
            key = self.TRACK_ENCRYPTION_KEY.encode("ascii")
            Fernet(key)
            return key
        if self.ENVIRONMENT == "production":
            raise RuntimeError("TRACK_ENCRYPTION_KEY is required in production")
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        key_file = self.DATA_DIR / "encryption.key"
        try:
            descriptor = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as target:
                target.write(Fernet.generate_key())
            try:
                key_file.chmod(0o600)
            except OSError:
                pass
        except FileExistsError:
            pass
        key = key_file.read_bytes().strip()
        Fernet(key)
        return key


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
DATABASE_URL = settings.database_url
