"""Versioned SQLAlchemy schema migrations kept in the existing infrastructure package."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Index, Integer, MetaData, String, Table, inspect, select, text
from sqlalchemy.engine import Connection, Engine


MIGRATION_TABLE = "schema_migrations"


def _ensure_migration_table(connection: Connection) -> Table:
    metadata = MetaData()
    table = Table(
        MIGRATION_TABLE,
        metadata,
        Column("version", Integer, primary_key=True),
        Column("name", String(160), nullable=False),
        Column("applied_at", DateTime(timezone=True), nullable=False),
    )
    table.create(connection, checkfirst=True)
    return table


def _bootstrap_schema(connection: Connection) -> None:
    # This is a named, recorded baseline revision. Startup never calls metadata.create_all.
    from scr.infrastructure.persistence import Base

    for table in Base.metadata.sorted_tables:
        table.create(connection, checkfirst=True)


def _add_missing_task_project_column(connection: Connection) -> None:
    """Upgrade databases initialized by the earlier unversioned MVP schema."""
    if "research_tasks" not in inspect(connection).get_table_names():
        return
    columns = {column["name"] for column in inspect(connection).get_columns("research_tasks")}
    if "project_id" not in columns:
        connection.execute(text("ALTER TABLE research_tasks ADD COLUMN project_id VARCHAR(36)"))
        if connection.dialect.name in {"postgresql", "mysql"}:
            connection.execute(text(
                "ALTER TABLE research_tasks ADD CONSTRAINT fk_research_tasks_project "
                "FOREIGN KEY (project_id) REFERENCES research_projects(id) ON DELETE SET NULL"
            ))
    if not inspect(connection).has_index("research_tasks", "ix_research_tasks_project_id"):
        from scr.infrastructure.persistence import ResearchTaskRecord

        Index("ix_research_tasks_project_id", ResearchTaskRecord.project_id).create(connection, checkfirst=True)


def _add_missing_token_version_column(connection: Connection) -> None:
    if "users" not in inspect(connection).get_table_names():
        return
    columns = {column["name"] for column in inspect(connection).get_columns("users")}
    if "token_version" not in columns:
        connection.execute(text("ALTER TABLE users ADD COLUMN token_version INTEGER NOT NULL DEFAULT 0"))


def _create_bootstrap_claims(connection: Connection) -> None:
    from scr.infrastructure.persistence import BootstrapClaimRecord

    BootstrapClaimRecord.__table__.create(connection, checkfirst=True)


MIGRATIONS = (
    (1, "baseline_schema", _bootstrap_schema),
    (2, "enterprise_lifecycle", lambda connection: (_add_missing_task_project_column(connection), _add_missing_token_version_column(connection))),
    (3, "atomic_initial_workspace", _create_bootstrap_claims),
)


def migrate(engine: Engine) -> int:
    """Apply pending revisions atomically and return the resulting schema version."""
    with engine.begin() as connection:
        mysql_lock_acquired = False
        if connection.dialect.name == "postgresql":
            connection.execute(text("SELECT pg_advisory_xact_lock(741920261)"))
        elif connection.dialect.name == "mysql":
            mysql_lock_acquired = connection.execute(
                text("SELECT GET_LOCK(:lock_name, 10)"),
                {"lock_name": "crossborder_research_schema_migrations"},
            ).scalar_one() == 1
            if not mysql_lock_acquired:
                raise RuntimeError("Timed out waiting for the MySQL schema migration lock.")
        try:
            versions = _ensure_migration_table(connection)
            current = connection.execute(select(versions.c.version).order_by(versions.c.version.desc()).limit(1)).scalar_one_or_none() or 0
            known = {version for version, _, _ in MIGRATIONS}
            if current > max(known):
                raise RuntimeError(f"Database schema version {current} is newer than this application supports.")
            for version, name, operation in MIGRATIONS:
                if version <= current:
                    continue
                operation(connection)
                connection.execute(versions.insert().values(
                    version=version,
                    name=name,
                    applied_at=datetime.now(timezone.utc),
                ))
                current = version
        finally:
            if mysql_lock_acquired:
                connection.execute(
                    text("SELECT RELEASE_LOCK(:lock_name)"),
                    {"lock_name": "crossborder_research_schema_migrations"},
                )
    return int(current)
