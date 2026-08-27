targetScope = 'resourceGroup'

param location string = resourceGroup().location
param appName string = 'abda-nl-web'
param containerAppsEnvironmentName string

@description('Public GHCR image repository without a tag or digest, for example ghcr.io/liu-hy/abda-nl.')
param imageRepository string

@description('The 64-character hexadecimal sha256 digest of the public ABDA-NL GHCR image.')
@minLength(64)
@maxLength(64)
param imageSha256 string

var image = '${imageRepository}@sha256:${imageSha256}'

@description('Application safety profile. Promote to production only after staging acceptance passes.')
@allowed([
  'staging'
  'production'
])
param deploymentEnvironment string = 'staging'

@description('Optional operator-owned hostname, without a scheme or path.')
param customHostname string = ''

@description('Managed certificate resource ID for customHostname. Set both values after the first domain bind.')
param customDomainCertificateId string = ''

param oidcMetadataUrl string
param oidcIssuer string
param oidcClientId string
param foundryEndpoint string
param foundryClaudeDeployment string = 'claude-sonnet-4-6'
param postgresHost string
param postgresAppLogin string = 'abda_app'

@secure()
@minLength(32)
param postgresAppPassword string

@secure()
@minLength(32)
param sessionSecret string

@secure()
@minLength(32)
param mcpTokenPepper string

@secure()
@minLength(32)
param metricsToken string

@secure()
param oidcClientSecret string

@secure()
param foundryApiKey string

@secure()
param openrouterApiKey string

@minValue(0)
@maxValue(1000000000)
param openrouterBudgetMicrousd int = 500000000

@description('Enable new verified users to claim funded trial credit.')
param trialEnabled bool = false

@minValue(0)
@maxValue(100)
param trialMaxUsers int = 100

@minValue(0)
@maxValue(500000000)
param trialBudgetMicrousd int = 500000000

@description('Allow qualifying CloudBank outages to spend the bounded OpenRouter budget.')
param openrouterFailoverEnabled bool = false

@minValue(1)
@maxValue(3)
param minReplicas int = 1

@minValue(1)
@maxValue(3)
param maxReplicas int = 3

resource environment 'Microsoft.App/managedEnvironments@2025-01-01' existing = {
  name: containerAppsEnvironmentName
}

var defaultHostname = '${appName}.${environment.properties.defaultDomain}'
var customDomainConfigured = !empty(customHostname) && !empty(customDomainCertificateId)
var publicHostname = customDomainConfigured ? customHostname : defaultHostname
var publicOrigin = 'https://${publicHostname}'
var trustedHosts = customDomainConfigured ? '${defaultHostname},${customHostname}' : defaultHostname
var budgetAcknowledgement = openrouterBudgetMicrousd > 500000000 ? 'I_ACCEPT_UP_TO_1000_USD' : ''
var databaseUrl = 'postgresql+psycopg://${postgresAppLogin}:${uriComponent(postgresAppPassword)}@${postgresHost}:5432/abda?sslmode=require'

resource containerApp 'Microsoft.App/containerApps@2025-01-01' = {
  name: appName
  location: location
  properties: {
    environmentId: environment.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        allowInsecure: false
        targetPort: 8000
        transport: 'auto'
        customDomains: customDomainConfigured ? [
          {
            name: customHostname
            bindingType: 'SniEnabled'
            certificateId: customDomainCertificateId
          }
        ] : []
        traffic: [
          {
            latestRevision: true
            weight: 100
          }
        ]
      }
      secrets: [
        {
          name: 'database-url'
          #disable-next-line use-secure-value-for-secure-inputs
          value: databaseUrl
        }
        {
          name: 'session-secret'
          value: sessionSecret
        }
        {
          name: 'mcp-token-pepper'
          value: mcpTokenPepper
        }
        {
          name: 'metrics-token'
          value: metricsToken
        }
        {
          name: 'oidc-client-secret'
          value: oidcClientSecret
        }
        {
          name: 'foundry-api-key'
          value: foundryApiKey
        }
        {
          name: 'openrouter-api-key'
          value: openrouterApiKey
        }
      ]
    }
    template: {
      terminationGracePeriodSeconds: 30
      containers: [
        {
          name: 'web'
          image: image
          env: [
            { name: 'ABDA_ENVIRONMENT', value: deploymentEnvironment }
            { name: 'ABDA_ENABLE_LLM', value: '1' }
            { name: 'ABDA_AUTH_MODE', value: 'oidc' }
            { name: 'ABDA_AUTO_CREATE_DB', value: '0' }
            { name: 'ABDA_DATABASE_URL', secretRef: 'database-url' }
            { name: 'ABDA_DATABASE_POOL_SIZE', value: '4' }
            { name: 'ABDA_DATABASE_MAX_OVERFLOW', value: '1' }
            { name: 'ABDA_DATABASE_POOL_TIMEOUT_SECONDS', value: '10' }
            { name: 'ABDA_PUBLIC_BASE_URL', value: publicOrigin }
            { name: 'ABDA_TRUSTED_HOSTS', value: trustedHosts }
            { name: 'ABDA_SESSION_COOKIE', value: '__Host-abda_session' }
            { name: 'ABDA_COOKIE_SECURE', value: '1' }
            { name: 'ABDA_SESSION_SECRET', secretRef: 'session-secret' }
            { name: 'ABDA_MCP_TOKEN_PEPPER', secretRef: 'mcp-token-pepper' }
            { name: 'ABDA_METRICS_TOKEN', secretRef: 'metrics-token' }
            { name: 'ABDA_OIDC_METADATA_URL', value: oidcMetadataUrl }
            { name: 'ABDA_OIDC_ISSUER', value: oidcIssuer }
            { name: 'ABDA_OIDC_CLIENT_ID', value: oidcClientId }
            { name: 'ABDA_OIDC_CLIENT_SECRET', secretRef: 'oidc-client-secret' }
            { name: 'ABDA_TRIAL_ENABLED', value: string(trialEnabled) }
            { name: 'ABDA_TRIAL_MAX_USERS', value: string(trialMaxUsers) }
            { name: 'ABDA_TRIAL_GRANT_MICROUSD', value: '5000000' }
            { name: 'ABDA_TRIAL_BUDGET_MICROUSD', value: string(trialBudgetMicrousd) }
            { name: 'ABDA_LLM_BACKEND', value: 'claude' }
            { name: 'ABDA_CLAUDE_PROVIDER', value: 'foundry' }
            { name: 'ABDA_LLM_DEFAULT_PROFILE', value: 'balanced' }
            { name: 'ABDA_LLM_ALLOW_BYOK', value: '1' }
            { name: 'ABDA_LLM_REQUIRE_AUTH', value: '1' }
            { name: 'ABDA_OPENROUTER_FAILOVER_ENABLED', value: string(openrouterFailoverEnabled) }
            { name: 'ABDA_OPENROUTER_BUDGET_MICROUSD', value: string(openrouterBudgetMicrousd) }
            { name: 'ABDA_OPENROUTER_BUDGET_ACK', value: budgetAcknowledgement }
            { name: 'ABDA_PROXY_MODE', value: 'azure-container-apps' }
            { name: 'ABDA_ABUSE_PROTECTION_ENABLED', value: '1' }
            { name: 'ABDA_MAX_REQUEST_BODY_BYTES', value: '2000000' }
            { name: 'ABDA_ANONYMOUS_REQUESTS_PER_MINUTE', value: '120' }
            { name: 'ABDA_MUTATION_REQUESTS_PER_MINUTE', value: '60' }
            { name: 'ABDA_LLM_REQUESTS_PER_MINUTE', value: '20' }
            { name: 'AZURE_ANTHROPIC_ENDPOINT', value: foundryEndpoint }
            { name: 'AZURE_OPENAI_API_KEY', secretRef: 'foundry-api-key' }
            { name: 'ANTHROPIC_FOUNDRY_CLAUDE_SONNET_4_6_MODEL', value: foundryClaudeDeployment }
            { name: 'OPENROUTER_API_KEY', secretRef: 'openrouter-api-key' }
          ]
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          probes: [
            {
              type: 'Startup'
              httpGet: {
                path: '/health/live'
                port: 8000
                scheme: 'HTTP'
              }
              initialDelaySeconds: 2
              periodSeconds: 5
              timeoutSeconds: 3
              failureThreshold: 30
            }
            {
              type: 'Liveness'
              httpGet: {
                path: '/health/live'
                port: 8000
                scheme: 'HTTP'
              }
              periodSeconds: 20
              timeoutSeconds: 3
              failureThreshold: 3
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/health/ready'
                port: 8000
                scheme: 'HTTP'
              }
              periodSeconds: 10
              timeoutSeconds: 3
              failureThreshold: 3
            }
          ]
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
        rules: [
          {
            name: 'http-concurrency'
            http: {
              metadata: {
                concurrentRequests: '20'
              }
            }
          }
        ]
      }
    }
  }
}

output defaultHostname string = defaultHostname
output publicHostname string = publicHostname
output publicOrigin string = publicOrigin
output oidcCallback string = '${publicOrigin}/auth/callback'
output oidcLogoutReturn string = '${publicOrigin}/'
output domainVerificationId string = containerApp.properties.customDomainVerificationId
output customDomainConfigured bool = customDomainConfigured
