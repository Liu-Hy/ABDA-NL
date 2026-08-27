"""Static contracts for production deployment privilege boundaries."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AZURE = ROOT / "deploy" / "azure"
WORKFLOWS = ROOT / ".github" / "workflows"


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


def test_public_rollout_defaults_disable_paid_activation_and_fallback():
    application = (AZURE / "app.bicep").read_text(encoding="utf-8")
    parameters = (AZURE / "app.bicepparam").read_text(encoding="utf-8")

    assert "param deploymentEnvironment string = 'staging'" in application
    assert "param trialEnabled bool = false" in application
    assert "param openrouterFailoverEnabled bool = false" in application
    assert "ABDA_DEPLOY_TRIAL_ENABLED', 'false'" in parameters
    assert "ABDA_DEPLOY_OPENROUTER_FAILOVER_ENABLED', 'false'" in parameters


def test_azure_deploys_only_the_public_digest_pinned_ghcr_image():
    infrastructure = (AZURE / "infra.bicep").read_text(encoding="utf-8")
    application = (AZURE / "app.bicep").read_text(encoding="utf-8")
    migration = (AZURE / "migration-job.bicep").read_text(encoding="utf-8")
    parameters = "\n".join(
        (AZURE / name).read_text(encoding="utf-8")
        for name in ("app.bicepparam", "migration-job.bicepparam")
    )

    for module in (application, migration):
        assert "ghcr.io/idaks/abda-nl@sha256:" in module
        assert "param imageSha256 string" in module
        assert "@minLength(64)" in module
        assert "@maxLength(64)" in module
        assert "var image = 'ghcr.io/idaks/abda-nl@sha256:${imageSha256}'" in module

    assert parameters.count("ABDA_DEPLOY_IMAGE_SHA256") == 2

    continuous_integration = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
    assert (
        'ABDA_DEPLOY_IMAGE_SHA256: "'
        + ("0" * 64)
        + '"'
        in continuous_integration
    )

    combined = "\n".join((infrastructure, application, migration, parameters))
    for forbidden in (
        "Microsoft.Authorization/roleAssignments",
        "Microsoft.ContainerRegistry/registries",
        "Microsoft.ManagedIdentity/userAssignedIdentities",
        "ABDA_DEPLOY_REGISTRY_NAME",
        "ABDA_DEPLOY_PULL_IDENTITY_NAME",
        "ABDA_DEPLOY_IMAGE')",
        "pullIdentity",
    ):
        assert forbidden not in combined


def test_service_image_workflow_prevents_mutable_or_unverified_deployments():
    workflow = (WORKFLOWS / "publish-service-image.yml").read_text(encoding="utf-8")
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "tags:\n      - service-image-*" in workflow
    assert "ABDA_IMAGE_NAME: ghcr.io/idaks/abda-nl" in workflow
    assert "password: ${{ secrets.GITHUB_TOKEN }}" in workflow
    assert "docker manifest inspect" in workflow
    assert "Smoke test the exact pushed digest" in workflow
    assert "subject-digest: ${{ steps.publish.outputs.digest }}" in workflow
    assert "push-to-registry: true" in workflow
    assert ":latest" not in workflow
    assert "org.opencontainers.image.source=\"https://github.com/idaks/ABDA-NL\"" in dockerfile
