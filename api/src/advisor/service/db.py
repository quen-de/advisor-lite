from pathlib import Path

import asyncpg

SCHEMA = Path(__file__).parent / 'schema.sql'


async def create_pool(database_url: str) -> asyncpg.Pool:
    return await asyncpg.create_pool(database_url)


async def apply_schema(pool: asyncpg.Pool) -> None:
    """Apply schema.sql. Idempotent."""
    async with pool.acquire() as conn:
        await conn.execute(SCHEMA.read_text())
