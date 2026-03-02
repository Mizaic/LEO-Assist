// -- Container Apps Environment + all 9 apps ------------------------------
param location string = resourceGroup().location
param environment string
param managedIdentityId string
param managedIdentityClientId string
param acrLoginServer string
param kvUri string
param sbNamespaceFqdn string
param aoaiEndpoint string
param imageTag string = 'placeholder'

// Use a public placeholder image on first deploy (before images are in ACR).
// GitHub Actions updates each app to the real image after ci-build.yml runs.
var usePlaceholder = imageTag == 'placeholder'
var placeholderImage = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
var registryConfig = usePlaceholder ? [] : [{ server: acrLoginServer, identity: managedIdentityId }]

// Non-secret config values passed from parameters file
param neo4jUser string
param neo4jKnowledgeUser string
param azureAdTenantId string
param awsBedrockModel string
param awsDefaultRegion string
param azureOpenAiBigModel string
param azureOpenAiSmallModel string
param azureOpenAiApiVersion string
param codingExtractorBackend string
param codingExtractorStrict string
param modelStoreContainer string
param modelStoreModelName string
param hitlLowConfidenceThreshold string
param hitlPeerReviewRate string
param modelMinPrecision string
param sbMaxLockRenewalSeconds string
param allowedOrigins string
param cookieSecure string
param sessionTtlHours string

var prefix = 'leoai-${environment}'
var caeName = '${prefix}-cae'
var logWorkspaceName = '${prefix}-logs'

// -- Log Analytics workspace -----------------------------------------------
resource logWorkspace 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: logWorkspaceName
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

// -- Container Apps Environment --------------------------------------------
resource cae 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: caeName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logWorkspace.properties.customerId
        sharedKey: logWorkspace.listKeys().primarySharedKey
      }
    }
    peerTrafficConfiguration: {
      encryption: {
        enabled: true
      }
    }
  }
}

// -- Internal service URLs (resolved by ACA DNS within the environment) ---
var termApiUrl = 'http://terminology-api'
var fhirApiUrl = 'http://fhir-api'
var analyticsApiUrl = 'http://analytics-api'
var modelInferenceUrl = 'http://model-inference'

// -- Shared env vars injected into every app -------------------------------
var sharedEnv = [
  { name: 'AZURE_KEYVAULT_URL', value: kvUri }
  { name: 'AZURE_CLIENT_ID', value: managedIdentityClientId }
  { name: 'AZURE_SERVICE_BUS_NAMESPACE', value: sbNamespaceFqdn }
  { name: 'AZURE_OPENAI_ENDPOINT', value: aoaiEndpoint }
  { name: 'AZURE_OPENAI_BIG_MODEL', value: azureOpenAiBigModel }
  { name: 'AZURE_OPENAI_SMALL_MODEL', value: azureOpenAiSmallModel }
  { name: 'AZURE_OPENAI_API_VERSION', value: azureOpenAiApiVersion }
  { name: 'AZURE_AD_TENANT_ID', value: azureAdTenantId }
  { name: 'AWS_BEDROCK_MODEL', value: awsBedrockModel }
  { name: 'AWS_DEFAULT_REGION', value: awsDefaultRegion }
  { name: 'MODEL_STORE_CONTAINER', value: modelStoreContainer }
  { name: 'MODEL_STORE_MODEL_NAME', value: modelStoreModelName }
  { name: 'COOKIE_SECURE', value: cookieSecure }
  { name: 'SESSION_TTL_HOURS', value: sessionTtlHours }
  { name: 'ALLOWED_ORIGINS', value: allowedOrigins }
  // Key Vault secret references -- injected as env vars at runtime
  { name: 'NEO4J_PASSWORD', secretRef: 'neo4j-patient-password' }
  { name: 'NEO4J_URI', secretRef: 'neo4j-patient-uri' }
  { name: 'KNOWLEDGE_GRAPH_NEO4J_URI', secretRef: 'neo4j-knowledge-uri' }
  { name: 'KNOWLEDGE_GRAPH_NEO4J_PASSWORD', secretRef: 'neo4j-knowledge-password' }
  { name: 'REDIS_URL', secretRef: 'redis-url' }
  { name: 'AWS_ACCESS_KEY_ID', secretRef: 'aws-access-key-id' }
  { name: 'AWS_SECRET_ACCESS_KEY', secretRef: 'aws-secret-access-key' }
  { name: 'AZURE_OPENAI_API_KEY', secretRef: 'azure-openai-api-key' }
  { name: 'SERVICE_AUTH_SECRET', secretRef: 'service-auth-secret' }
]

var sharedSecrets = [
  { name: 'neo4j-patient-password', keyVaultUrl: '${kvUri}secrets/neo4j-patient-password', identity: managedIdentityId }
  { name: 'neo4j-patient-uri', keyVaultUrl: '${kvUri}secrets/neo4j-patient-uri', identity: managedIdentityId }
  { name: 'neo4j-knowledge-uri', keyVaultUrl: '${kvUri}secrets/neo4j-knowledge-uri', identity: managedIdentityId }
  { name: 'neo4j-knowledge-password', keyVaultUrl: '${kvUri}secrets/neo4j-knowledge-password', identity: managedIdentityId }
  { name: 'redis-url', keyVaultUrl: '${kvUri}secrets/redis-url', identity: managedIdentityId }
  { name: 'aws-access-key-id', keyVaultUrl: '${kvUri}secrets/aws-access-key-id', identity: managedIdentityId }
  { name: 'aws-secret-access-key', keyVaultUrl: '${kvUri}secrets/aws-secret-access-key', identity: managedIdentityId }
  { name: 'azure-openai-api-key', keyVaultUrl: '${kvUri}secrets/azure-openai-api-key', identity: managedIdentityId }
  { name: 'service-auth-secret', keyVaultUrl: '${kvUri}secrets/service-auth-secret', identity: managedIdentityId }
]

var identityConfig = {
  type: 'UserAssigned'
  userAssignedIdentities: {
    '${managedIdentityId}': {}
  }
}

// -- core-api (external ingress) ------------------------------------------
resource coreApi 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'core-api'
  location: location
  identity: identityConfig
  properties: {
    environmentId: cae.id
    configuration: {
      secrets: sharedSecrets
      registries: registryConfig
      ingress: {
        external: true
        targetPort: 8000
        transport: 'http'
      }
    }
    template: {
      containers: [{
        name: 'core-api'
        image: usePlaceholder ? placeholderImage : '${acrLoginServer}/core-api:${imageTag}'
        resources: { cpu: json('0.5'), memory: '1Gi' }
        env: union(sharedEnv, [
          { name: 'NEO4J_USER', value: neo4jUser }
          { name: 'TERMINOLOGY_API_URL', value: termApiUrl }
          { name: 'FHIR_API_URL', value: fhirApiUrl }
          { name: 'ANALYTICS_API_URL', value: analyticsApiUrl }
          { name: 'CODING_MODEL_ENDPOINT', value: modelInferenceUrl }
          { name: 'CODING_EXTRACTOR_BACKEND', value: codingExtractorBackend }
          { name: 'CODING_EXTRACTOR_STRICT', value: codingExtractorStrict }
          { name: 'HITL_LOW_CONFIDENCE_THRESHOLD', value: hitlLowConfidenceThreshold }
          { name: 'HITL_PEER_REVIEW_RATE', value: hitlPeerReviewRate }
          { name: 'MODEL_MIN_PRECISION', value: modelMinPrecision }
        ])
      }]
      scale: { minReplicas: 1, maxReplicas: 3 }
    }
  }
}

// -- ui (external ingress) -------------------------------------------------
resource ui 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ui'
  location: location
  identity: identityConfig
  properties: {
    environmentId: cae.id
    configuration: {
      secrets: sharedSecrets
      registries: registryConfig
      ingress: {
        external: true
        targetPort: 3000
        transport: 'http'
      }
    }
    template: {
      containers: [{
        name: 'ui'
        image: usePlaceholder ? placeholderImage : '${acrLoginServer}/ui:${imageTag}'
        resources: { cpu: json('0.25'), memory: '0.5Gi' }
        env: [
          { name: 'INTERNAL_API_BASE', value: 'http://core-api' }
          { name: 'TERMINOLOGY_API_URL', value: termApiUrl }
          { name: 'TRAINING_WORKER_URL', value: 'http://training-worker' }
          { name: 'NODE_ENV', value: 'production' }
        ]
      }]
      scale: { minReplicas: 1, maxReplicas: 2 }
    }
  }
}

// -- terminology-api (internal ingress) -----------------------------------
resource terminologyApi 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'terminology-api'
  location: location
  identity: identityConfig
  properties: {
    environmentId: cae.id
    configuration: {
      secrets: sharedSecrets
      registries: registryConfig
      ingress: {
        external: false
        targetPort: 8001
        transport: 'http'
      }
    }
    template: {
      containers: [{
        name: 'terminology-api'
        image: usePlaceholder ? placeholderImage : '${acrLoginServer}/terminology-api:${imageTag}'
        resources: { cpu: json('0.25'), memory: '0.5Gi' }
        env: union(sharedEnv, [
          { name: 'KNOWLEDGE_GRAPH_NEO4J_USERNAME', value: neo4jKnowledgeUser }
        ])
      }]
      scale: { minReplicas: 0, maxReplicas: 3 }
    }
  }
}

// -- fhir-api (internal ingress) ------------------------------------------
resource fhirApi 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'fhir-api'
  location: location
  identity: identityConfig
  properties: {
    environmentId: cae.id
    configuration: {
      secrets: sharedSecrets
      registries: registryConfig
      ingress: {
        external: false
        targetPort: 8002
        transport: 'http'
      }
    }
    template: {
      containers: [{
        name: 'fhir-api'
        image: usePlaceholder ? placeholderImage : '${acrLoginServer}/fhir-api:${imageTag}'
        resources: { cpu: json('0.25'), memory: '0.5Gi' }
        env: union(sharedEnv, [
          { name: 'NEO4J_USER', value: neo4jUser }
          { name: 'KNOWLEDGE_GRAPH_NEO4J_USERNAME', value: neo4jKnowledgeUser }
        ])
      }]
      scale: { minReplicas: 0, maxReplicas: 3 }
    }
  }
}

// -- analytics-api (internal ingress) -------------------------------------
resource analyticsApi 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'analytics-api'
  location: location
  identity: identityConfig
  properties: {
    environmentId: cae.id
    configuration: {
      secrets: sharedSecrets
      registries: registryConfig
      ingress: {
        external: false
        targetPort: 8003
        transport: 'http'
      }
    }
    template: {
      containers: [{
        name: 'analytics-api'
        image: usePlaceholder ? placeholderImage : '${acrLoginServer}/analytics-api:${imageTag}'
        resources: { cpu: json('0.25'), memory: '0.5Gi' }
        env: union(sharedEnv, [
          { name: 'NEO4J_USER', value: neo4jUser }
        ])
      }]
      scale: { minReplicas: 0, maxReplicas: 3 }
    }
  }
}

// -- model-inference (internal ingress) -----------------------------------
resource modelInference 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'model-inference'
  location: location
  identity: identityConfig
  properties: {
    environmentId: cae.id
    configuration: {
      secrets: sharedSecrets
      registries: registryConfig
      ingress: {
        external: false
        targetPort: 8004
        transport: 'http'
      }
    }
    template: {
      containers: [{
        name: 'model-inference'
        image: usePlaceholder ? placeholderImage : '${acrLoginServer}/model-inference:${imageTag}'
        resources: { cpu: json('1.0'), memory: '2Gi' }
        env: union(sharedEnv, [
          { name: 'MODEL_STORE_CACHE_DIR', value: '/var/model_cache' }
        ])
      }]
      scale: { minReplicas: 0, maxReplicas: 2 }
    }
  }
}

// -- training-worker (internal ingress) -----------------------------------
resource trainingWorker 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'training-worker'
  location: location
  identity: identityConfig
  properties: {
    environmentId: cae.id
    configuration: {
      secrets: sharedSecrets
      registries: registryConfig
      ingress: {
        external: false
        targetPort: 8005
        transport: 'http'
      }
    }
    template: {
      containers: [{
        name: 'training-worker'
        image: usePlaceholder ? placeholderImage : '${acrLoginServer}/training-worker:${imageTag}'
        resources: { cpu: json('1.0'), memory: '2Gi' }
        env: sharedEnv
      }]
      scale: { minReplicas: 0, maxReplicas: 1 }
    }
  }
}

// -- coding-worker (no ingress, KEDA Service Bus scaler) ------------------
resource codingWorker 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'coding-worker'
  location: location
  identity: identityConfig
  properties: {
    environmentId: cae.id
    configuration: {
      secrets: sharedSecrets
      registries: registryConfig
    }
    template: {
      containers: [{
        name: 'coding-worker'
        image: usePlaceholder ? placeholderImage : '${acrLoginServer}/coding-worker:${imageTag}'
        resources: { cpu: json('0.5'), memory: '1Gi' }
        env: union(sharedEnv, [
          { name: 'NEO4J_USER', value: neo4jUser }
          { name: 'TERMINOLOGY_API_URL', value: termApiUrl }
          { name: 'CODING_MODEL_ENDPOINT', value: modelInferenceUrl }
          { name: 'CODING_EXTRACTOR_BACKEND', value: codingExtractorBackend }
          { name: 'SB_MAX_LOCK_RENEWAL_SECONDS', value: sbMaxLockRenewalSeconds }
        ])
      }]
      scale: {
        minReplicas: 0
        maxReplicas: 5
        rules: [{
          name: 'coding-jobs-keda'
          custom: {
            type: 'azure-servicebus'
            metadata: {
              queueName: 'coding-jobs'
              namespace: sbNamespaceFqdn
              messageCount: '5'
            }
            auth: [{
              secretRef: 'service-auth-secret'
              triggerParameter: 'connection'
            }]
          }
        }]
      }
    }
  }
}

// -- analysis-worker (no ingress, KEDA Service Bus scaler) ----------------
resource analysisWorker 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'analysis-worker'
  location: location
  identity: identityConfig
  properties: {
    environmentId: cae.id
    configuration: {
      secrets: sharedSecrets
      registries: registryConfig
    }
    template: {
      containers: [{
        name: 'analysis-worker'
        image: usePlaceholder ? placeholderImage : '${acrLoginServer}/analysis-worker:${imageTag}'
        resources: { cpu: json('0.5'), memory: '1Gi' }
        env: union(sharedEnv, [
          { name: 'NEO4J_USER', value: neo4jUser }
          { name: 'SB_MAX_LOCK_RENEWAL_SECONDS', value: sbMaxLockRenewalSeconds }
        ])
      }]
      scale: {
        minReplicas: 0
        maxReplicas: 5
        rules: [{
          name: 'analysis-jobs-keda'
          custom: {
            type: 'azure-servicebus'
            metadata: {
              queueName: 'analysis-jobs'
              namespace: sbNamespaceFqdn
              messageCount: '5'
            }
            auth: [{
              secretRef: 'service-auth-secret'
              triggerParameter: 'connection'
            }]
          }
        }]
      }
    }
  }
}

output coreApiFqdn string = coreApi.properties.configuration.ingress.fqdn
output uiFqdn string = ui.properties.configuration.ingress.fqdn
