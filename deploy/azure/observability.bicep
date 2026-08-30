targetScope = 'resourceGroup'

param location string = resourceGroup().location

@description('Prefix used for the ABDA-NL alert resources.')
@minLength(3)
@maxLength(32)
param resourcePrefix string = 'abda-nl-stg'

@description('Existing Container App monitored by these alert rules.')
param appName string = 'abda-nl-stg-web'

@description('Monitored operator address that receives Azure alert notifications.')
param alertEmail string = 'support@abda-nl.org'

param tags object = {
  application: 'ABDA-NL'
  purpose: 'COMMA-2026-research-demo'
}

var actionGroupName = '${resourcePrefix}-operators'
var serverErrorAlertName = '${resourcePrefix}-web-5xx'
var unavailableAlertName = '${resourcePrefix}-web-unavailable'

resource app 'Microsoft.App/containerApps@2025-01-01' existing = {
  name: appName
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

output actionGroupName string = operatorActionGroup.name
output serverErrorAlertName string = serverErrorAlert.name
output unavailableAlertName string = unavailableAlert.name
