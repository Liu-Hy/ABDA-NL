using './infra.bicep'

param resourcePrefix = readEnvironmentVariable('ABDA_DEPLOY_PREFIX', 'abda-nl')
param location = readEnvironmentVariable('ABDA_DEPLOY_LOCATION', 'eastus2')
param postgresAdminLogin = readEnvironmentVariable('ABDA_DEPLOY_POSTGRES_ADMIN_LOGIN', 'abdaadmin')
param postgresAdminPassword = readEnvironmentVariable('ABDA_DEPLOY_POSTGRES_ADMIN_PASSWORD')
