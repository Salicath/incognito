from pathlib import Path

from backend.core.config import AppConfig


def test_default_config():
    config = AppConfig()
    assert config.data_dir == Path.home() / ".incognito"
    assert config.db_name == "incognito.db"
    assert config.rate_limit_per_hour == 10
    assert config.session_timeout_minutes == 30
    assert config.gdpr_deadline_days == 30
    assert config.log_level == "info"


def test_config_db_path():
    config = AppConfig()
    assert config.db_path == config.data_dir / config.db_name


def test_config_vault_path():
    config = AppConfig()
    assert config.vault_path == config.data_dir / "profile.enc"


def test_config_override():
    config = AppConfig(data_dir=Path("/tmp/test-incognito"), rate_limit_per_hour=20)
    assert config.data_dir == Path("/tmp/test-incognito")
    assert config.rate_limit_per_hour == 20
