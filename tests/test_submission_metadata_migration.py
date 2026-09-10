"""Upgrade existing public examples without silently opting authors into attribution."""
from alembic import command
from sqlalchemy import create_engine, text

from app.db.session import _alembic_config


def test_metadata_upgrade_preserves_existing_snapshot_and_credit_retention(tmp_path):
    database_url = f"sqlite+pysqlite:///{tmp_path / 'metadata.db'}"
    config = _alembic_config(database_url)
    command.upgrade(config, "20260910_0007")
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text("""
            INSERT INTO users (id, email, email_verified, display_name, status, created_at, updated_at)
            VALUES ('legacy-author', 'private@example.org', 1, 'Unconsented name', 'active',
                    '2026-09-10 12:00:00', '2026-09-10 12:00:00')
        """))
        connection.execute(text("""
            INSERT INTO scenario_submissions
                (id, submitter_id, project_version, title, description, scenario_json, status,
                 version, review_note, created_at, reviewed_at)
            VALUES ('legacy-snapshot', 'legacy-author', 1, 'Consented title', 'Full public background',
                    '{"title":"Consented title"}', 'published', 2, 'Private review note',
                    '2026-09-10 12:00:00', '2026-09-10 12:00:01')
        """))
        connection.execute(text("""
            INSERT INTO credit_eligibility_markers (digest, kind, user_id, claimed_at)
            VALUES (:digest, 'email', 'legacy-author', '2026-09-10 12:00:00')
        """), {"digest": "a" * 64})
    command.upgrade(config, "20260910_0008")
    with engine.connect() as connection:
        row = connection.execute(text("SELECT * FROM scenario_submissions")).mappings().one()
        assert row["public_summary"] == "" and row["author_note"] == ""
        assert row["attribution_name"] is None
        assert row["title"] == "Consented title" and row["description"] == "Full public background"
        assert row["review_note"] == "Private review note" and row["version"] == 2
    command.downgrade(config, "20260910_0007")
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT digest FROM credit_eligibility_markers")) == "a" * 64
        assert connection.scalar(text("SELECT title FROM scenario_submissions")) == "Consented title"
    engine.dispose()
