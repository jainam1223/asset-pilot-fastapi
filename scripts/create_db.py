"""Ensure the target Postgres database exists, creating it if missing.

Reads the single `DATABASE_URL` connection string from `settings` (works
whether that's your local Postgres install or a distributed/managed
instance), connects to its `postgres` maintenance database, checks
whether the target database (the URL's path) exists, and issues
`CREATE DATABASE` if it isn't there yet. Safe to run repeatedly (no-ops
if already present). Run via `make create-db`, before `make migrate` on
a fresh Postgres server.
"""

import argparse
import asyncio

import asyncpg

from app.core.config import settings


def _target_db_name() -> str:
    return settings.DATABASE_URL.path.lstrip("/")  # type: ignore[union-attr]


def _maintenance_connection_kwargs() -> dict[str, str | int | None]:
    host_parts = settings.DATABASE_URL.hosts()[0]
    return {
        "user": host_parts["username"],
        "password": host_parts["password"],
        "host": host_parts["host"],
        "port": host_parts["port"] or 5432,
        "database": "postgres",
    }


async def create_db_if_not_exists(recreate: bool = False) -> None:
    db_name = _target_db_name()
    conn = await asyncpg.connect(**_maintenance_connection_kwargs())
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", db_name)
        # CREATE/DROP DATABASE cannot run inside a transaction / take a
        # parameter placeholder for the identifier, so quote it manually.
        quoted_name = '"' + db_name.replace('"', '""') + '"'
        if exists and recreate:
            await conn.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = $1 AND pid <> pg_backend_pid()",
                db_name,
            )
            await conn.execute(f"DROP DATABASE {quoted_name}")
            print(f"Database '{db_name}' dropped.")
            exists = False
        if exists:
            print(f"Database '{db_name}' already exists.")
            return
        await conn.execute(f"CREATE DATABASE {quoted_name}")
        print(f"Database '{db_name}' created.")
    finally:
        await conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Drop the database first if it already exists (destructive).",
    )
    args = parser.parse_args()
    asyncio.run(create_db_if_not_exists(recreate=args.recreate))
