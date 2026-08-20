"""Static contracts for production deployment privilege boundaries."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AZURE = ROOT / "deploy" / "azure"


def test_web_revision_receives_only_the_restricted_database_login():
    module = (AZURE / "app.bicep").read_text(encoding="utf-8")
    parameters = (AZURE / "app.bicepparam").read_text(encoding="utf-8")

    assert "postgresAppLogin" in module
    assert "postgresAppPassword" in module
    assert "postgresAdminLogin" not in module
    assert "postgresAdminPassword" not in module
    assert "ABDA_DEPLOY_POSTGRES_APP_PASSWORD" in parameters
    assert "ABDA_DEPLOY_POSTGRES_ADMIN_PASSWORD" not in parameters


def test_migration_job_owns_admin_access_and_provisions_the_web_role():
    module = (AZURE / "migration-job.bicep").read_text(encoding="utf-8")
    parameters = (AZURE / "migration-job.bicepparam").read_text(encoding="utf-8")

    assert "postgresAdminPassword" in module
    assert "postgresAppPassword" in module
    assert "'app.cli.migrate'" in module
    assert "ABDA_DATABASE_APP_PASSWORD" in module
    assert "ABDA_DEPLOY_POSTGRES_ADMIN_PASSWORD" in parameters
    assert "ABDA_DEPLOY_POSTGRES_APP_PASSWORD" in parameters


def test_b1ms_connection_budget_is_bounded_across_three_replicas():
    infrastructure = (AZURE / "infra.bicep").read_text(encoding="utf-8")
    application = (AZURE / "app.bicep").read_text(encoding="utf-8")

    assert "name: 'Standard_B1ms'" in infrastructure
    assert application.count("@maxValue(3)") >= 2
    assert "{ name: 'ABDA_DATABASE_POOL_SIZE', value: '4' }" in application
    assert "{ name: 'ABDA_DATABASE_MAX_OVERFLOW', value: '1' }" in application
