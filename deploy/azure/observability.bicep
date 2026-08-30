targetScope = 'resourceGroup'

param location string = resourceGroup().location

@description('Prefix used for the ABDA-NL alert resources.')
@minLength(3)
@maxLength(32)
param resourcePrefix string = 'abda-nl-stg'

@description('Existing Container App monitored by these alert rules.')
param appName string = 'abda-nl-stg-web'

@description('Existing Log Analytics workspace used by Application Insights.')
param logWorkspaceName string = 'abda-nl-stg-logs-bgjhpbgw'

@description('Public readiness URL checked from three Azure regions every five minutes.')
param publicReadinessUrl string = 'https://demo.abda-nl.org/health/ready'

@description('Monitored operator address that receives Azure alert notifications.')
param alertEmail string = 'support@abda-nl.org'

param tags object = {
  application: 'ABDA-NL'
  purpose: 'COMMA-2026-research-demo'
}

var actionGroupName = '${resourcePrefix}-operators'
var serverErrorAlertName = '${resourcePrefix}-web-5xx'
var unavailableAlertName = '${resourcePrefix}-web-unavailable'
var applicationInsightsName = '${resourcePrefix}-availability'
var readinessTestName = '${resourcePrefix}-public-ready'
var readinessAlertName = '${resourcePrefix}-public-ready-failed'

resource app 'Microsoft.App/containerApps@2025-01-01' existing = {
  name: appName
}

resource logWorkspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' existing = {
  name: logWorkspaceName
}

resource operatorActionGroup 'Microsoft.Insights/actionGroups@2023-01-01' = {
  name: actionGroupName
  location: 'global'
  tags: tags
  properties: {
    groupShortName: 'abda-alert'
    enabled: true
    emailReceivers: [
      {
        name: 'abda-support'
        emailAddress: alertEmail
        useCommonAlertSchema: true
      }
    ]
  }
}

resource serverErrorAlert 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: serverErrorAlertName
  location: 'global'
  tags: tags
  properties: {
    description: 'ABDA-NL served at least five HTTP 5xx responses in five minutes.'
    severity: 2
    enabled: true
    scopes: [
      app.id
    ]
    evaluationFrequency: 'PT1M'
    windowSize: 'PT5M'
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          criterionType: 'StaticThresholdCriterion'
          name: 'FiveServerErrors'
          metricName: 'Requests'
          metricNamespace: 'Microsoft.App/containerapps'
          operator: 'GreaterThanOrEqual'
          timeAggregation: 'Total'
          threshold: 5
          dimensions: [
            {
              name: 'statusCodeCategory'
              operator: 'Include'
              values: [
                '5xx'
              ]
            }
          ]
          skipMetricValidation: false
        }
      ]
    }
    autoMitigate: true
    targetResourceType: 'Microsoft.App/containerApps'
    targetResourceRegion: location
    actions: [
      {
        actionGroupId: operatorActionGroup.id
      }
    ]
  }
}

resource unavailableAlert 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: unavailableAlertName
  location: 'global'
  tags: tags
  properties: {
    description: 'ABDA-NL reported fewer than one active replica in five minutes.'
    severity: 1
    enabled: true
    scopes: [
      app.id
    ]
    evaluationFrequency: 'PT1M'
    windowSize: 'PT5M'
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          criterionType: 'StaticThresholdCriterion'
          name: 'NoActiveReplica'
          metricName: 'Replicas'
          metricNamespace: 'Microsoft.App/containerapps'
          operator: 'LessThan'
          timeAggregation: 'Minimum'
          threshold: 1
          dimensions: []
          skipMetricValidation: false
        }
      ]
    }
    autoMitigate: true
    targetResourceType: 'Microsoft.App/containerApps'
    targetResourceRegion: location
    actions: [
      {
        actionGroupId: operatorActionGroup.id
      }
    ]
  }
}

resource applicationInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: applicationInsightsName
  location: location
  kind: 'web'
  tags: tags
  properties: {
    Application_Type: 'web'
    IngestionMode: 'LogAnalytics'
    WorkspaceResourceId: logWorkspace.id
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
  }
}

resource readinessTest 'Microsoft.Insights/webtests@2022-06-15' = {
  name: readinessTestName
  location: location
  tags: union(tags, {
    'hidden-link:${applicationInsights.id}': 'Resource'
  })
  properties: {
    SyntheticMonitorId: readinessTestName
    Name: readinessTestName
    Description: 'ABDA-NL public readiness and TLS check.'
    Enabled: true
    Frequency: 300
    Timeout: 30
    Kind: 'standard'
    RetryEnabled: true
    Locations: [
      {
        Id: 'us-il-ch1-azr'
      }
      {
        Id: 'us-va-ash-azr'
      }
      {
        Id: 'emea-nl-ams-azr'
      }
    ]
    Request: {
      RequestUrl: publicReadinessUrl
      HttpVerb: 'GET'
    }
    ValidationRules: {
      ExpectedHttpStatusCode: 200
      SSLCheck: true
      SSLCertRemainingLifetimeCheck: 14
    }
  }
}

resource readinessAlert 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: readinessAlertName
  location: 'global'
  tags: union(tags, {
    'hidden-link:${applicationInsights.id}': 'Resource'
    'hidden-link:${readinessTest.id}': 'Resource'
  })
  properties: {
    description: 'ABDA-NL public readiness failed from at least two Azure regions.'
    severity: 1
    enabled: true
    scopes: [
      readinessTest.id
      applicationInsights.id
    ]
    evaluationFrequency: 'PT1M'
    windowSize: 'PT5M'
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.WebtestLocationAvailabilityCriteria'
      webTestId: readinessTest.id
      componentId: applicationInsights.id
      failedLocationCount: 2
    }
    autoMitigate: true
    actions: [
      {
        actionGroupId: operatorActionGroup.id
      }
    ]
  }
}

output actionGroupName string = operatorActionGroup.name
output serverErrorAlertName string = serverErrorAlert.name
output unavailableAlertName string = unavailableAlert.name
output applicationInsightsName string = applicationInsights.name
output readinessTestName string = readinessTest.name
output readinessAlertName string = readinessAlert.name
