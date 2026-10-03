from sqlalchemy import create_engine, inspect

from app.migrations import run_migrations
from app.seed import reset_and_seed


def test_upgrade_creates_lifecycle_columns(tmp_path):
    database_url = f"sqlite:///{(tmp_path / 'migration.db').as_posix()}"
    run_migrations(database_url)

    columns = inspect(create_engine(database_url)).get_columns("contracts")

    assert {column["name"] for column in columns} >= {
        "archived_at",
        "updated_at",
        "counterparty",
        "jurisdiction",
        "description",
    }
    inspector = inspect(create_engine(database_url))
    assert {"playbooks", "playbook_rules", "findings"} <= set(inspector.get_table_names())


def test_seed_after_migration_is_deterministic(tmp_path):
    database_url = f"sqlite:///{(tmp_path / 'seed.db').as_posix()}"

    first = reset_and_seed(database_url)
    second = reset_and_seed(database_url)

    assert first == second == {
        "contracts": 12,
        "versions": 36,
        "clauses": 276,
        "obligations": 10,
        "reviewers": 6,
    }
