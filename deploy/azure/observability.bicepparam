using './observability.bicep'

param location = readEnvironmentVariable('ABDA_DEPLOY_LOCATION', 'eastus2')
param resourcePrefix = readEnvironmentVariable('ABDA_DEPLOY_ALERT_PREFIX', 'abda-nl-stg')
param appName = readEnvironmentVariable('ABDA_DEPLOY_APP_NAME', 'abda-nl-stg-web')
param alertEmail = readEnvironmentVariable('ABDA_DEPLOY_ALERT_EMAIL', 'support@abda-nl.org')
