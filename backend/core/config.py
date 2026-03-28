from pathlib import Path

from pydantic_settings import BaseSettings


class AppConfig(BaseSettings):
    model_config = {"env_prefix": "INCOGNITO_"}

    data_dir: Path = Path.home() / ".incognito"
    db_name: str = "incognito.db"
    rate_limit_per_hour: int = 10
    session_timeout_minutes: int = 30
    gdpr_deadline_days: int = 30
    log_level: str = "info"
    host: str = "127.0.0.1"
    port: int = 8080

    @property
    def db_path(self) -> Path:
        return self.data_dir / self.db_name

    @property
    def vault_path(self) -> Path:
        return self.data_dir / "profile.enc"

    @property
    def brokers_dir(self) -> Path:
        return self.data_dir / "brokers"

    @property
    def log_dir(self) -> Path:
        return self.data_dir / "logs"
