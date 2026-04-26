import logging
import os

from sqlalchemy import inspect
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from backend.config import get_settings
from backend.db.models import Base

engine: AsyncEngine | None = None
async_session: sessionmaker | None = None


def get_engine():
    global engine
    if engine is None:
        settings = get_settings()
        engine = create_async_engine(settings.database_url, future=True, echo=False)
    return engine


def get_session_maker():
    global async_session
    if async_session is None:
        e = get_engine()
        async_session = sessionmaker(e, expire_on_commit=False, class_=AsyncSession)
    return async_session


async def get_db() -> AsyncSession:
    sm = get_session_maker()
    async with sm() as session:
        yield session


async def init_db():
    # Ensure the database directory exists if using SQLite
    url = make_url(get_settings().database_url)
    if url.drivername.startswith("sqlite") and url.database:
        db_dir = os.path.dirname(url.database)
        if db_dir and not os.path.exists(db_dir):
            logging.getLogger("ir2mqtt").info("Creating database directory: %s", db_dir)
            os.makedirs(db_dir, exist_ok=True)

    e = get_engine()
    async with e.begin() as conn:
        # Check if the database is already under Alembic control
        def check_alembic(sync_conn):
            inspector = inspect(sync_conn)
            return "alembic_version" in inspector.get_table_names()

        alembic_active = await conn.run_sync(check_alembic)
        if not alembic_active:
            logging.getLogger("ir2mqtt").info("No migrations found. Initializing database schema...")
            await conn.run_sync(Base.metadata.create_all)
