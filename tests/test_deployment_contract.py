"""Static contracts for production deployment privilege boundaries."""

from __future__ import annotations

from pathlib import Path
import re
import subprocess


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


def test_container_app_health_probes_preserve_strict_host_validation():
    application = (AZURE / "app.bicep").read_text(encoding="utf-8")

    assert "var healthProbeHeaders = [" in application
    assert "name: 'Host'" in application
    assert "value: defaultHostname" in application
    assert application.count("httpHeaders: healthProbeHeaders") == 3
    assert "var trustedHosts = customDomainConfigured" in application
    assert "{ name: 'ABDA_TRUSTED_HOSTS', value: trustedHosts }" in application
    assert "ABDA_TRUSTED_HOSTS', value: '*'" not in application


def test_virtual_network_mutations_are_serialized():
    infrastructure = (AZURE / "infra.bicep").read_text(encoding="utf-8")
    postgres_subnet = infrastructure.split("resource postgresSubnet", 1)[1].split(
        "resource privateDns", 1
    )[0]
    environment = infrastructure.split("resource environment", 1)[1].split(
        "resource postgres", 1
    )[0]
    postgres = infrastructure.split(
        "resource postgres 'Microsoft.DBforPostgreSQL", 1
    )[1].split("resource database", 1)[0]

    assert "dependsOn: [\n    containerAppsSubnet\n  ]" in postgres_subnet
    assert "dependsOn: [\n    postgresSubnet\n  ]" in environment
    assert "dependsOn: [\n    privateDnsLink\n    environment\n  ]" in postgres


def test_public_rollout_defaults_disable_paid_activation_and_fallback():
    application = (AZURE / "app.bicep").read_text(encoding="utf-8")
    parameters = (AZURE / "app.bicepparam").read_text(encoding="utf-8")
    example_environment = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "param deploymentEnvironment string = 'staging'" in application
    assert "param trialEnabled bool = false" in application
    assert "param openrouterFailoverEnabled bool = false" in application
    assert "ABDA_DEPLOY_TRIAL_ENABLED', 'false'" in parameters
    assert "ABDA_DEPLOY_OPENROUTER_FAILOVER_ENABLED', 'false'" in parameters
    assert "ABDA_TRIAL_ENABLED=0" in example_environment


def test_operator_bootstrap_is_owner_controlled_and_secret_safe():
    operations = ROOT / "docs" / "operations"
    bootstrap = (operations / "operator-service-bootstrap.md").read_text(
        encoding="utf-8"
    )
    auth0 = (operations / "auth0-email-otp.md").read_text(encoding="utf-8")
    deployment = (operations / "public-deployment.md").read_text(encoding="utf-8")
    example_environment = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "without depending on iSchool IT" in bootstrap
    assert "support@DOMAIN" in bootstrap
    assert "privacy@DOMAIN" in bootstrap
    assert "no-reply@auth.DOMAIN" in bootstrap
    assert "dedicated ABDA-NL inference key with a $500" in bootstrap
    assert (
        "ABDA_DEPLOY_OPENROUTER_FAILOVER_ENABLED` remains `false`" in bootstrap
    )
    assert "operator-controlled, long-lived account" in auth0
    assert "select Resend" in auth0
    assert "ABDA_DEPLOY_DESIRED_HOSTNAME" in deployment
    assert deployment.count("read -rsp") >= 7
    public_url_lines = [
        line
        for line in example_environment.splitlines()
        if line.startswith("# ABDA_PUBLIC_BASE_URL=")
    ]
    assert public_url_lines == [
        "# ABDA_PUBLIC_BASE_URL=https://demo.example.org"
    ]
    assert "ischool.illinois.edu" not in example_environment


def test_postgres_recovery_is_private_new_server_and_reviewed_cutover():
    operations = ROOT / "docs" / "operations"
    recovery = (operations / "database-recovery.md").read_text(encoding="utf-8")
    deployment = (operations / "public-deployment.md").read_text(encoding="utf-8")
    checklist = (operations / "release-checklist.md").read_text(encoding="utf-8")
    traceability = (operations / "requirements-traceability.md").read_text(
        encoding="utf-8"
    )
    playbook = (operations / "comma-2026-demo-playbook.md").read_text(
        encoding="utf-8"
    )
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    normalized_recovery = " ".join(recovery.split())

    assert "Source server: `abda-nl-stg-postgres-bgjhpbgw`" in recovery
    assert "Native backup retention: 7 days" in recovery
    assert "Every point-in-time restore creates a new server" in recovery
    assert "Do not select public access" in normalized_recovery
    assert "Cutover is a separate maintenance event" in recovery
    assert "az postgres flexible-server delete" not in recovery
    assert "database-recovery.md" in deployment
    assert "database-recovery.md" in checklist
    assert "database-recovery.md" in playbook
    assert "[PostgreSQL recovery runbook](database-recovery.md)" in traceability
    assert "docs/operations/database-recovery.md" in readme


def test_operations_index_names_one_current_sequence_and_has_valid_doc_links():
    index_path = ROOT / "docs" / "operations" / "README.md"
    index = index_path.read_text(encoding="utf-8")
    normalized_index = " ".join(index.split())

    assert "only current ordered sequence" in normalized_index
    assert "[final public-service operator batch](final-operator-batch.md)" in index
    assert (
        "Do not reconstruct a current command from a historical checkpoint"
        in normalized_index
    )

    relative_links = re.findall(r"\]\(([^)#]+\.md)(?:#[^)]*)?\)", index)
    assert relative_links
    for relative_link in relative_links:
        assert (index_path.parent / relative_link).is_file(), relative_link


def test_ci_exercises_chromium_firefox_and_webkit():
    workflow = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")

    assert "browser: [chromium, firefox, webkit]" in workflow
    assert 'ABDA_BROWSER_ENGINE: "${{ matrix.browser }}"' in workflow
    assert 'playwright install --with-deps "${{ matrix.browser }}"' in workflow


def test_foundry_inventory_instructions_are_copyable_and_read_only():
    promotion = (ROOT / "docs" / "operations" / "model-promotion.md").read_text(
        encoding="utf-8"
    )
    section = promotion.split(
        "### Read the actual Azure deployment inventory", maxsplit=1
    )[1]
    block = re.search(r"```bash\n(.*?)\n```", section, flags=re.DOTALL)

    assert block is not None
    shell = block.group(1)
    syntax = subprocess.run(
        ["bash", "-n"],
        input=shell,
        capture_output=True,
        check=False,
        text=True,
    )
    assert syntax.returncode == 0, syntax.stderr
    assert "azure_identity: verified" in shell
    assert "AZURE_ANTHROPIC_ENDPOINT" in shell
    assert "az cognitiveservices account deployment list" in shell
    assert "FOUNDRY_DEPLOYMENT_INVENTORY_LISTED_READ_ONLY" in shell
    for forbidden in (
        " deployment create",
        " deployment delete",
        " deployment update",
        " api-key",
        " x-api-key",
        " curl ",
    ):
        assert forbidden not in shell


def test_azure_deploys_only_the_public_digest_pinned_ghcr_image():
    infrastructure = (AZURE / "infra.bicep").read_text(encoding="utf-8")
    application = (AZURE / "app.bicep").read_text(encoding="utf-8")
    migration = (AZURE / "migration-job.bicep").read_text(encoding="utf-8")
    parameters = "\n".join(
        (AZURE / name).read_text(encoding="utf-8")
        for name in ("app.bicepparam", "migration-job.bicepparam")
    )

    for module in (application, migration):
        assert "param imageRepository string" in module
        assert "param imageSha256 string" in module
        assert "@minLength(64)" in module
        assert "@maxLength(64)" in module
        assert "var image = '${imageRepository}@sha256:${imageSha256}'" in module

    assert parameters.count("ABDA_DEPLOY_IMAGE_REPOSITORY") == 2
    assert parameters.count("ABDA_DEPLOY_IMAGE_SHA256") == 2

    continuous_integration = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
    assert (
        "ABDA_DEPLOY_IMAGE_REPOSITORY: ghcr.io/example/abda-nl"
        in continuous_integration
    )
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
    assert 'ABDA_IMAGE_OWNER="${GITHUB_REPOSITORY_OWNER,,}"' in workflow
    assert 'ABDA_IMAGE_NAME="ghcr.io/${ABDA_IMAGE_OWNER}/abda-nl"' in workflow
    assert "password: ${{ secrets.GITHUB_TOKEN }}" in workflow
    assert "docker manifest inspect" in workflow
    assert "Smoke test the exact pushed digest" in workflow
    assert "subject-digest: ${{ steps.publish.outputs.digest }}" in workflow
    assert "push-to-registry: true" in workflow
    assert ":latest" not in workflow
    assert "ARG ABDA_IMAGE_SOURCE=https://github.com/idaks/ABDA-NL" in dockerfile
    assert 'org.opencontainers.image.source="${ABDA_IMAGE_SOURCE}"' in dockerfile
    assert "pyproject.toml README.md LICENSE ./" in dockerfile
    assert "test -s /srv/abda/LICENSE" in workflow
    assert "ABDA_IMAGE_SOURCE=${{ github.server_url }}/${{ github.repository }}" in workflow


def test_continuous_integration_verifies_the_container_license_file():
    workflow = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")

    assert '.dist-info/licenses/LICENSE")' in workflow
    assert "test -s /srv/abda/LICENSE" in workflow


def test_service_image_workflow_enforces_the_source_license_gate():
    workflow = (WORKFLOWS / "publish-service-image.yml").read_text(encoding="utf-8")
    review = (ROOT / "docs" / "operations" / "source-license-review.md").read_text(
        encoding="utf-8"
    )

    lines = set(review.splitlines())
    cleared_gate = "Public image publication gate: cleared"
    blocked_gate = "Public image publication gate: blocked"
    assert cleared_gate in workflow
    assert (cleared_gate in lines) != (blocked_gate in lines)
