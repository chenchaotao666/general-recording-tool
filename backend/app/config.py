from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/


class Settings(BaseSettings):
    # 默认 SQLite，零配置即可运行；局域网部署可切 MySQL（见 .env.example）
    database_url: str = f"sqlite:///{(BASE_DIR / 'grt.db').as_posix()}"
    upload_dir: Path = BASE_DIR / "uploads"
    secret_key_file: Path = BASE_DIR / ".secret_key"

    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", env_prefix="GRT_", extra="ignore")


settings = Settings()
