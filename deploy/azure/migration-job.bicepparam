using './migration-job.bicep'

param location = readEnvironmentVariable('ABDA_DEPLOY_LOCATION', 'eastus2')
param jobName = readEnvironmentVariable('ABDA_DEPLOY_MIGRATION_JOB_NAME', 'abda-nl-migrate')
param containerAppsEnvironmentName = readEnvironmentVariable('ABDA_DEPLOY_ENVIRONMENT_NAME')
param imageSha256 = readEnvironmentVariable('ABDA_DEPLOY_IMAGE_SHA256')
param postgresHost = readEnvironmentVariable('ABDA_DEPLOY_POSTGRES_HOST')
param postgresAdminLogin = readEnvironmentVariable('ABDA_DEPLOY_POSTGRES_ADMIN_LOGIN', 'abdaadmin')
param postgresAdminPassword = readEnvironmentVariable('ABDA_DEPLOY_POSTGRES_ADMIN_PASSWORD')
param postgresAppLogin = readEnvironmentVariable('ABDA_DEPLOY_POSTGRES_APP_LOGIN', 'abda_app')
param postgresAppPassword = readEnvironmentVariable('ABDA_DEPLOY_POSTGRES_APP_PASSWORD')
