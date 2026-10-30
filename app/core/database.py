from sqlalchemy import event, inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import DATABASE_URL, settings

if DATABASE_URL.startswith("sqlite"):
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)

async_engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
async_session_marker = async_sessionmaker(
    async_engine, expire_on_commit=False, class_=AsyncSession
)

if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(async_engine.sync_engine, "connect")
    def configure_sqlite(connection, _):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()


class Base(DeclarativeBase):
    pass


async def initialize_database() -> None:
    """Create only a fresh development SQLite; existing DBs use Alembic."""
    from app import models  # register all tables before metadata creation

    if settings.AUTO_CREATE_TABLES and DATABASE_URL.startswith("sqlite"):
        async with async_engine.begin() as connection:
            tables = await connection.run_sync(lambda conn: inspect(conn).get_table_names())
            if not tables:
                await connection.run_sync(Base.metadata.create_all)
                await connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"))
                await connection.execute(text("INSERT INTO alembic_version VALUES ('f103_service')"))


async def check_connection() -> None:
    async with async_engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
