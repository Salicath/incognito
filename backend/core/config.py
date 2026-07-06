import logging
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
    cors_origins: str = ""  # Comma-separated extra origins (e.g. for dev)
    secure_cookies: bool = False  # Set True behind HTTPS reverse proxy
    notify_url: str = ""  # Ntfy/Gotify/webhook URL for push notifications
    trusted_proxy_header: str = ""  # e.g. "Remote-User" for Authentik/Authelia
    user_country: str = "DK"  # Residence SA for controller-track Art. 77 complaints
    searxng_url: str = ""  # Self-hosted SearXNG sidecar (e.g. http://127.0.0.1:8888)

    def setup_logging(self) -> logging.Logger:
        level = getattr(logging, self.log_level.upper(), None)
        if level is None:
            level = logging.INFO
            logging.warning("Invalid log level '%s', defaulting to INFO", self.log_level)
        logging.basicConfig(
            level=level,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        return logging.getLogger("incognito")

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
