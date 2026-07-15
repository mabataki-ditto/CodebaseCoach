import tempfile
from pathlib import Path

import pytest
from sqlalchemy.orm import sessionmaker

from app.db.session import create_engine_for_url, init_db


@pytest.fixture
def db_session_factory():
    engine = create_engine_for_url("sqlite:///:memory:")
    init_db(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    try:
        yield factory
    finally:
        engine.dispose()


@pytest.fixture(scope="function")
def temp_dir():
    """函数级别的临时目录，每个测试独立。"""
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)
