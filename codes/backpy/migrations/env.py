import asyncio

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from app.contrib.db import Base
from app.settings import get_settings

target_metadata = Base.metadata


def run(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def main() -> None:
    url = get_settings().database_url
    if not url:
        raise SystemExit("DATABASE_URL is not set")
    engine = create_async_engine(url)
    async with engine.connect() as connection:
        await connection.run_sync(run)
        await connection.commit()
    await engine.dispose()


asyncio.run(main())
