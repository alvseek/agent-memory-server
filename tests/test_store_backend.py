"""Store-backend selection: config, validation, factory, and app wiring."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from munnin.app import StoreBackendError, _validate_backend, build_app
from munnin.business_services.service_factory import ServiceFactory
from munnin.configuration.config import Config, load_config
from munnin.data_repositories.postgres_memory_repository import PostgresMemoryRepository
from munnin.data_repositories.sqlite_memory_repository import SqliteMemoryRepository

URL = os.getenv("MUNNIN_PG_TEST_URL")
needs_pg = pytest.mark.skipif(not URL, reason="MUNNIN_PG_TEST_URL not set")


def test_config_defaults_to_sqlite(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MUNNIN_DB_BACKEND", raising=False)
    monkeypatch.delenv("MUNNIN_DB_URL", raising=False)
    config = load_config()
    assert config.db_backend == "sqlite"
    assert config.db_url == ""


def test_config_reads_and_normalises_backend_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MUNNIN_DB_BACKEND", "Postgres")
    monkeypatch.setenv("MUNNIN_DB_URL", "postgresql://host/db")
    config = load_config()
    assert config.db_backend == "postgres"
    assert config.db_url == "postgresql://host/db"


def test_validate_backend_refuses_unknown_and_incomplete() -> None:
    with pytest.raises(StoreBackendError):
        _validate_backend(Config(db_backend="mysql"))
    with pytest.raises(StoreBackendError):
        _validate_backend(Config(db_backend="postgres", db_url=""))
    _validate_backend(Config(db_backend="sqlite"))  # the default is always valid


def test_service_factory_selects_sqlite_by_default(tmp_path: Path) -> None:
    factory = ServiceFactory(tmp_path / "m.db")
    assert isinstance(factory._repository("alvi"), SqliteMemoryRepository)


@pytest.mark.postgres
@needs_pg
def test_service_factory_selects_postgres() -> None:
    factory = ServiceFactory(Path("unused.db"), backend="postgres", db_url=URL)
    assert isinstance(factory._repository("alvi"), PostgresMemoryRepository)


@pytest.mark.postgres
@needs_pg
def test_build_app_boots_on_the_postgres_backend() -> None:
    config = Config(
        db_backend="postgres",
        db_url=URL,
        auth_mode="off",
        public_base_url="http://127.0.0.1:8200",
        host="127.0.0.1",
    )
    app = build_app(config)  # local mode ensure_account touches Postgres at startup
    assert app is not None
