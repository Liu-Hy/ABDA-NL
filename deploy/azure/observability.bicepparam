using './observability.bicep'

param location = readEnvironmentVariable('ABDA_DEPLOY_LOCATION', 'eastus2')
param resourcePrefix = readEnvironmentVariable('ABDA_DEPLOY_ALERT_PREFIX', 'abda-nl-stg')
param appName = readEnvironmentVariable('ABDA_DEPLOY_APP_NAME', 'abda-nl-stg-web')
param logWorkspaceName = readEnvironmentVariable('ABDA_DEPLOY_LOG_WORKSPACE_NAME', 'abda-nl-stg-logs-bgjhpbgw')
param publicReadinessUrl = readEnvironmentVariable('ABDA_DEPLOY_PUBLIC_READINESS_URL', 'https://demo.abda-nl.org/health/ready')
param alertEmail = readEnvironmentVariable('ABDA_DEPLOY_ALERT_EMAIL', 'support@abda-nl.org')
