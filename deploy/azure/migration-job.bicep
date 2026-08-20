targetScope = 'resourceGroup'

param location string = resourceGroup().location
param jobName string = 'abda-nl-migrate'
param containerAppsEnvironmentName string
param registryName string
param pullIdentityName string
param image string
param postgresHost string
param postgresAdminLogin string = 'abdaadmin'

@secure()
param postgresAdminPassword string

param postgresAppLogin string = 'abda_app'

@secure()
@minLength(32)
param postgresAppPassword string

resource environment 'Microsoft.App/managedEnvironments@2025-01-01' existing = {
  name: containerAppsEnvironmentName
}

resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: registryName
}

resource pullIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = {
  name: pullIdentityName
}

var adminDatabaseUrl = 'postgresql+psycopg://${postgresAdminLogin}:${uriComponent(postgresAdminPassword)}@${postgresHost}:5432/abda?sslmode=require'

resource migrationJob 'Microsoft.App/jobs@2025-01-01' = {
  name: jobName
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${pullIdentity.id}': {}
    }
  }
  properties: {
    environmentId: environment.id
    configuration: {
      triggerType: 'Manual'
      replicaTimeout: 900
      replicaRetryLimit: 0
      manualTriggerConfig: {
        parallelism: 1
        replicaCompletionCount: 1
      }
      registries: [
        {
          server: registry.properties.loginServer
          identity: pullIdentity.id
        }
      ]
      secrets: [
        {
          name: 'admin-database-url'
          #disable-next-line use-secure-value-for-secure-inputs
          value: adminDatabaseUrl
        }
        {
          name: 'app-database-password'
          value: postgresAppPassword
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'migrate'
          image: image
          command: [
            '/opt/venv/bin/python'
          ]
          args: [
            '-m'
            'app.cli.migrate'
          ]
          env: [
            {
              name: 'ABDA_DATABASE_URL'
              secretRef: 'admin-database-url'
            }
            {
              name: 'ABDA_DATABASE_APP_LOGIN'
              value: postgresAppLogin
            }
            {
              name: 'ABDA_DATABASE_APP_PASSWORD'
              secretRef: 'app-database-password'
            }
          ]
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
        }
      ]
    }
  }
}

output migrationJobName string = migrationJob.name
