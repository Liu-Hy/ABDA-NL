targetScope = 'resourceGroup'

@description('Short lowercase prefix used for Azure resource names.')
@minLength(3)
@maxLength(18)
param resourcePrefix string = 'abda-nl'

param location string = resourceGroup().location

@description('PostgreSQL administrator name used only for deployment and recovery.')
param postgresAdminLogin string = 'abdaadmin'

@secure()
@minLength(16)
param postgresAdminPassword string

param tags object = {
  application: 'ABDA-NL'
  purpose: 'COMMA-2026-research-demo'
}

var suffix = take(uniqueString(subscription().id, resourceGroup().id), 8)
var networkName = '${resourcePrefix}-network'
var environmentName = '${resourcePrefix}-environment'
var postgresName = '${resourcePrefix}-postgres-${suffix}'
var privateDnsName = '${resourcePrefix}-${suffix}.postgres.database.azure.com'
var appName = '${resourcePrefix}-web'
var migrationJobName = '${resourcePrefix}-migrate'

resource network 'Microsoft.Network/virtualNetworks@2024-05-01' = {
  name: networkName
  location: location
  tags: tags
  properties: {
    addressSpace: {
      addressPrefixes: [
        '10.42.0.0/16'
      ]
    }
  }
}

resource containerAppsSubnet 'Microsoft.Network/virtualNetworks/subnets@2024-05-01' = {
  parent: network
  name: 'container-apps'
  properties: {
    addressPrefix: '10.42.0.0/27'
    delegations: [
      {
        name: 'container-apps-delegation'
        properties: {
          serviceName: 'Microsoft.App/environments'
        }
      }
    ]
  }
}

resource postgresSubnet 'Microsoft.Network/virtualNetworks/subnets@2024-05-01' = {
  parent: network
  name: 'postgres'
  properties: {
    addressPrefix: '10.42.1.0/28'
    delegations: [
      {
        name: 'postgres-delegation'
        properties: {
          serviceName: 'Microsoft.DBforPostgreSQL/flexibleServers'
        }
      }
    ]
  }
}

resource privateDns 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: privateDnsName
  location: 'global'
  tags: tags
}

resource privateDnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: privateDns
  name: 'abda-network-link'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: network.id
    }
  }
}

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${resourcePrefix}-logs-${suffix}'
  location: location
  tags: tags
  properties: {
    retentionInDays: 30
    sku: {
      name: 'PerGB2018'
    }
  }
}

resource environment 'Microsoft.App/managedEnvironments@2025-01-01' = {
  name: environmentName
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
    vnetConfiguration: {
      infrastructureSubnetId: containerAppsSubnet.id
      internal: false
    }
    workloadProfiles: [
      {
        name: 'Consumption'
        workloadProfileType: 'Consumption'
      }
    ]
    zoneRedundant: false
  }
}

resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: postgresName
  location: location
  tags: tags
  sku: {
    name: 'Standard_B1ms'
    tier: 'Burstable'
  }
  properties: {
    administratorLogin: postgresAdminLogin
    administratorLoginPassword: postgresAdminPassword
    version: '16'
    authConfig: {
      activeDirectoryAuth: 'Disabled'
      passwordAuth: 'Enabled'
    }
    backup: {
      backupRetentionDays: 7
      geoRedundantBackup: 'Disabled'
    }
    highAvailability: {
      mode: 'Disabled'
    }
    network: {
      delegatedSubnetResourceId: postgresSubnet.id
      privateDnsZoneArmResourceId: privateDns.id
      publicNetworkAccess: 'Disabled'
    }
    storage: {
      autoGrow: 'Enabled'
      storageSizeGB: 32
    }
  }
  dependsOn: [
    privateDnsLink
  ]
}

resource database 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2024-08-01' = {
  parent: postgres
  name: 'abda'
  properties: {
    charset: 'UTF8'
    collation: 'en_US.utf8'
  }
}

output containerAppsEnvironmentName string = environment.name
output containerAppsDefaultDomain string = environment.properties.defaultDomain
output expectedAppName string = appName
output expectedPublicOrigin string = 'https://${appName}.${environment.properties.defaultDomain}'
output expectedOidcCallback string = 'https://${appName}.${environment.properties.defaultDomain}/auth/callback'
output expectedOidcLogoutReturn string = 'https://${appName}.${environment.properties.defaultDomain}/'
output migrationJobName string = migrationJobName
output postgresHost string = postgres.properties.fullyQualifiedDomainName
output postgresDatabase string = database.name
output postgresAdminLogin string = postgresAdminLogin
