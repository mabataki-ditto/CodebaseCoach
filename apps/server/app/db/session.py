from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.models import Base


def create_engine_for_url(database_url: str | None = None) -> Engine:
    url = database_url or settings.resolved_database_url
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    if url == "sqlite:///:memory:":
        return create_engine(url, connect_args=connect_args, poolclass=StaticPool)
    return create_engine(url, connect_args=connect_args)


engine = create_engine_for_url()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def init_db(target_engine: Engine | None = None) -> None:
    Base.metadata.create_all(bind=target_engine or engine)


def get_db_session() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session
