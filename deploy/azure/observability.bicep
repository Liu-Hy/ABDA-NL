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

@description('Only manage the three model-routing log alerts, retaining the existing availability resources and receiver.')
param routingAlertsOnly bool = false

@description('Settled emergency-provider spend in a fifteen-minute window that notifies operators, in millionths of a dollar. This does not change a spending cap.')
@minValue(100000)
@maxValue(10000000)
param fallbackSpendThresholdMicrousd int = 1000000

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

resource operatorActionGroup 'Microsoft.Insights/actionGroups@2023-01-01' = if (!routingAlertsOnly) {
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

resource serverErrorAlert 'Microsoft.Insights/metricAlerts@2018-03-01' = if (!routingAlertsOnly) {
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

resource unavailableAlert 'Microsoft.Insights/metricAlerts@2018-03-01' = if (!routingAlertsOnly) {
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

resource applicationInsights 'Microsoft.Insights/components@2020-02-02' = if (!routingAlertsOnly) {
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

resource readinessTest 'Microsoft.Insights/webtests@2022-06-15' = if (!routingAlertsOnly) {
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

resource readinessAlert 'Microsoft.Insights/metricAlerts@2018-03-01' = if (!routingAlertsOnly) {
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

// Only sanitized event names, bounded route identifiers, timestamps, and
// aggregate counts or costs reach alert results. Logs are not invoice evidence.
var routeConfigurationQuery = format('''
ContainerAppConsoleLogs_CL
| where ContainerAppName_s == "{0}"
| where Log_s contains "llm_configuration_unavailable"
| extend Route = extract("route=([^ ]+)", 1, Log_s)
| extend Route = iff(isempty(Route), "public-routes", Route)
| project TimeGenerated, Route
''', appName)

var routeCircuitQuery = format('''
ContainerAppConsoleLogs_CL
| where ContainerAppName_s == "{0}"
| where Log_s contains "llm_circuit_open "
| extend Route = extract("primary=([^ ]+)", 1, Log_s)
| where isnotempty(Route)
| summarize Opens = count() by Route, bin(TimeGenerated, 5m)
''', appName)

var fallbackSpendQuery = format('''
ContainerAppConsoleLogs_CL
| where ContainerAppName_s == "{0}"
| where Log_s contains "llm_fallback_spend "
| extend SpentMicrousd = tolong(extract("cost_microusd=([0-9]+)", 1, Log_s))
| where SpentMicrousd > 0
| project TimeGenerated, SpentMicrousd
''', appName)

resource routeConfigurationAlert 'Microsoft.Insights/scheduledQueryRules@2023-12-01' = {
  name: '${resourcePrefix}-llm-configuration'
  location: location
  kind: 'LogAlert'
  tags: tags
  properties: {
    description: 'ABDA-NL has unavailable local provider configuration. Restore CloudBank configuration before enabling funded requests.'
    severity: 1
    enabled: true
    scopes: [logWorkspace.id]
    evaluationFrequency: 'PT5M'
    windowSize: 'PT5M'
    autoMitigate: true
    skipQueryValidation: false
    criteria: {
      allOf: [{
        query: routeConfigurationQuery
        timeAggregation: 'Count'
        operator: 'GreaterThanOrEqual'
        threshold: 1
        dimensions: [{name: 'Route', operator: 'Include', values: ['*']}]
        failingPeriods: {numberOfEvaluationPeriods: 1, minFailingPeriodsToAlert: 1}
      }]
    }
    actions: {
      actionGroups: [resourceId('Microsoft.Insights/actionGroups', actionGroupName)]
    }
  }
  dependsOn: [operatorActionGroup]
}

resource routeCircuitAlert 'Microsoft.Insights/scheduledQueryRules@2023-12-01' = {
  name: '${resourcePrefix}-llm-circuit'
  location: location
  kind: 'LogAlert'
  tags: tags
  properties: {
    description: 'ABDA-NL opened the same funded route circuit in at least two five-minute periods out of three. Investigate provider health and emergency usage.'
    severity: 2
    enabled: true
    scopes: [logWorkspace.id]
    evaluationFrequency: 'PT5M'
    windowSize: 'PT5M'
    autoMitigate: true
    skipQueryValidation: false
    criteria: {
      allOf: [{
        query: routeCircuitQuery
        metricMeasureColumn: 'Opens'
        timeAggregation: 'Total'
        operator: 'GreaterThanOrEqual'
        threshold: 1
        dimensions: [{name: 'Route', operator: 'Include', values: ['*']}]
        failingPeriods: {numberOfEvaluationPeriods: 3, minFailingPeriodsToAlert: 2}
      }]
    }
    actions: {
      actionGroups: [resourceId('Microsoft.Insights/actionGroups', actionGroupName)]
    }
  }
  dependsOn: [operatorActionGroup]
}

resource fallbackSpendAlert 'Microsoft.Insights/scheduledQueryRules@2023-12-01' = {
  name: '${resourcePrefix}-llm-fallback-spend'
  location: location
  kind: 'LogAlert'
  tags: tags
  properties: {
    description: 'ABDA-NL settled emergency-provider charges reached the reviewed fifteen-minute notification threshold. Amounts can include conservative timeout assessments.'
    severity: 2
    enabled: true
    scopes: [logWorkspace.id]
    evaluationFrequency: 'PT5M'
    windowSize: 'PT15M'
    autoMitigate: true
    skipQueryValidation: false
    criteria: {
      allOf: [{
        query: fallbackSpendQuery
        metricMeasureColumn: 'SpentMicrousd'
        timeAggregation: 'Total'
        operator: 'GreaterThanOrEqual'
        threshold: fallbackSpendThresholdMicrousd
        dimensions: []
        failingPeriods: {numberOfEvaluationPeriods: 1, minFailingPeriodsToAlert: 1}
      }]
    }
    actions: {
      actionGroups: [resourceId('Microsoft.Insights/actionGroups', actionGroupName)]
    }
  }
  dependsOn: [operatorActionGroup]
}

output actionGroupName string = operatorActionGroup.name
output serverErrorAlertName string = serverErrorAlert.name
output unavailableAlertName string = unavailableAlert.name
output applicationInsightsName string = applicationInsights.name
output readinessTestName string = readinessTest.name
output readinessAlertName string = readinessAlert.name
output routeConfigurationAlertName string = routeConfigurationAlert.name
output routeCircuitAlertName string = routeCircuitAlert.name
output fallbackSpendAlertName string = fallbackSpendAlert.name
