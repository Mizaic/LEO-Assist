// -- Container Apps Environment + 8 apps ---------------------------------
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
param codingMode string = 'hitl'
param modelMinPrecision string
param modelMinRecall string = '0.75'
param sbMaxLockRenewalSeconds string
param allowedOrigins string
param cookieSecure string
param sessionTtlHours string
param frontendUrl string
param snomedTerminologyServer string = ''

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
var pipelineWorkerUrl = 'http://pipeline-worker'

// -- Shared env vars injected into every app -------------------------------
var sharedEnv = [
  // Azure infrastructure
  { name: 'AZURE_KEYVAULT_URL', value: kvUri }
  { name: 'AZURE_CLIENT_ID', value: managedIdentityClientId }
  { name: 'AZURE_SERVICE_BUS_NAMESPACE', value: sbNamespaceFqdn }

  // Azure OpenAI (non-secret config)
  { name: 'OPENAI_API_TYPE', value: 'azure' }
  { name: 'AZURE_OPENAI_ENDPOINT', value: aoaiEndpoint }
  { name: 'AZURE_OPENAI_BIG_MODEL', value: azureOpenAiBigModel }
  { name: 'AZURE_OPENAI_SMALL_MODEL', value: azureOpenAiSmallModel }
  { name: 'AZURE_OPENAI_API_VERSION', value: azureOpenAiApiVersion }

  // AWS Bedrock (non-secret config)
  { name: 'AWS_DEFAULT_REGION', value: awsDefaultRegion }

  // Pipeline and coding extractor
  { name: 'PIPELINE_MODEL_PROVIDER', value: 'aws' }
  { name: 'PIPELINE_MODEL_TIER', value: 'small' }
  { name: 'CODING_EXTRACTOR_BACKEND', value: codingExtractorBackend }
  { name: 'CODING_EXTRACTOR_STRICT', value: codingExtractorStrict }
  { name: 'CODING_MODEL_PROVIDER', value: 'service' }
  { name: 'CODING_MODEL_NAME', value: modelStoreModelName }
  { name: 'CODING_MODEL_TIMEOUT_MS', value: '10000' }
  { name: 'CODING_MODEL_MAX_RETRIES', value: '2' }

  // Model store
  { name: 'MODEL_STORE_CONTAINER', value: modelStoreContainer }
  { name: 'MODEL_STORE_MODEL_NAME', value: modelStoreModelName }
  { name: 'MODEL_REGISTRY_STORE', value: 'neo4j' }
  // Keep fallback path aligned with local startup script for json mode.
  { name: 'MODEL_REGISTRY_STORE_PATH', value: '/var/model_cache/model_registry.json' }

  // Model quality gates
  { name: 'MODEL_MIN_PRECISION', value: modelMinPrecision }
  { name: 'MODEL_MIN_RECALL', value: modelMinRecall }
  { name: 'MODEL_CANARY_MIN_PRECISION', value: modelMinPrecision }
  { name: 'MODEL_CANARY_MIN_RECALL', value: modelMinRecall }
  { name: 'MODEL_REQUIRED_SCHEMA_VERSION', value: '1.0' }
  { name: 'MODEL_REQUIRED_DEID_VERSION', value: '1.0' }
  { name: 'MODEL_REQUIRED_LABEL_VERSION', value: '1.0' }

  // HITL thresholds
  { name: 'HITL_LOW_CONFIDENCE_THRESHOLD', value: hitlLowConfidenceThreshold }
  { name: 'HITL_PEER_REVIEW_RATE', value: hitlPeerReviewRate }
  { name: 'CODING_MODE', value: codingMode }

  // Label verification
  { name: 'LABEL_VERIFY_WORKERS', value: '50' }
  { name: 'LABEL_VERIFY_ADAPTIVE_MIN_CONCURRENCY', value: '20' }
  { name: 'LABEL_VERIFY_ADAPTIVE_MAX_CONCURRENCY', value: '120' }
  { name: 'LABEL_VERIFY_ADAPTIVE_INITIAL_CONCURRENCY', value: '60' }

  // Training
  { name: 'TRAINING_HF_BASE_MODEL', value: 'emilyalsentzer/Bio_ClinicalBERT' }
  { name: 'TRAINING_FROZEN_COMPONENTS', value: 'transformer' }
  { name: 'TRAINING_MAX_CONCURRENT_JOBS', value: '1' }
  { name: 'TRAINING_JOB_TIMEOUT_S', value: '43200' }
  { name: 'TRAINING_MIN_LABEL_COUNT', value: '50' }
  { name: 'TRAINING_USE_GPU', value: 'false' }
  { name: 'HF_HOME', value: '/var/model_cache/hf_cache' }
  { name: 'HF_HUB_OFFLINE', value: '1' }

  // Vector / embedding model (same base model as NER)
  { name: 'VECTOR_MODEL', value: 'emilyalsentzer/Bio_ClinicalBERT' }
  { name: 'VECTOR_DIMENSION', value: '768' }
  { name: 'VECTOR_DEVICE', value: 'cpu' }

  // Terminology
  { name: 'SNOMED_TERMINOLOGY_SERVER', value: snomedTerminologyServer }
  { name: 'NCDA_CONFIG_DIR', value: 'configs/snomed' }
  // Local startup exports TERMINOLOGY_API_URLS; set single ACA endpoint for parity.
  { name: 'TERMINOLOGY_API_URLS', value: termApiUrl }

  // Security / session
  { name: 'COOKIE_SECURE', value: cookieSecure }
  { name: 'SESSION_TTL_HOURS', value: sessionTtlHours }
  { name: 'ALLOWED_ORIGINS', value: allowedOrigins }
  { name: 'CORS_ORIGINS', value: allowedOrigins }

  // Key Vault secret references -- injected as env vars at runtime
  { name: 'NEO4J_PASSWORD', secretRef: 'neo4j-patient-password' }
  { name: 'NEO4J_URI', secretRef: 'neo4j-patient-uri' }
  { name: 'KNOWLEDGE_GRAPH_NEO4J_URI', secretRef: 'neo4j-knowledge-uri' }
  { name: 'KNOWLEDGE_GRAPH_NEO4J_PASSWORD', secretRef: 'neo4j-knowledge-password' }
  { name: 'GUIDELINE_NEO4J_URI', secretRef: 'neo4j-guideline-uri' }
  { name: 'GUIDELINE_NEO4J_PASSWORD', secretRef: 'neo4j-guideline-password' }
  { name: 'REDIS_URL', secretRef: 'redis-url' }
  { name: 'AZURE_AD_TENANT_ID', secretRef: 'azure-ad-tenant-id' }
  { name: 'AZURE_AD_CLIENT_SECRET', secretRef: 'azure-ad-client-secret' }
  { name: 'AZURE_OPENAI_API_KEY', secretRef: 'azure-openai-api-key' }
  { name: 'AZURE_STORAGE_CONNECTION_STRING', secretRef: 'azure-storage-connection-string' }
  { name: 'AZURE_SERVICE_BUS_CONNECTION_STRING', secretRef: 'azure-service-bus-connection-string' }
  { name: 'AWS_ACCESS_KEY_ID', secretRef: 'aws-access-key-id' }
  { name: 'AWS_SECRET_ACCESS_KEY', secretRef: 'aws-secret-access-key' }
  { name: 'AWS_BIG_MODEL', secretRef: 'aws-big-model' }
  { name: 'AWS_SMALL_MODEL', secretRef: 'aws-small-model' }
  { name: 'AWS_MAX_MODEL', secretRef: 'aws-max-model' }
  { name: 'SNOMED_API_KEY', secretRef: 'snomed-api-key' }
  { name: 'UMLS_API_KEY', secretRef: 'umls-api-key' }
  { name: 'NHS_TRUD_API_KEY', secretRef: 'nhs-trud-api-key' }
  { name: 'AZURE_AD_CLIENT_ID', secretRef: 'azure-ad-client-id' }
  { name: 'ANALYTICS_API_APP_ID', secretRef: 'analytics-api-app-id' }
  { name: 'FHIR_API_APP_ID', secretRef: 'fhir-api-app-id' }
  { name: 'MODEL_INFERENCE_APP_ID', secretRef: 'model-inference-app-id' }
  { name: 'TERMINOLOGY_API_APP_ID', secretRef: 'terminology-api-app-id' }
  { name: 'AUTH_SECRET', secretRef: 'auth-secret' }
  { name: 'SERVICE_AUTH_SECRET', secretRef: 'service-auth-secret' }
]

var sharedSecrets = [
  { name: 'neo4j-patient-password', keyVaultUrl: '${kvUri}secrets/neo4j-patient-password', identity: managedIdentityId }
  { name: 'neo4j-patient-uri', keyVaultUrl: '${kvUri}secrets/neo4j-patient-uri', identity: managedIdentityId }
  { name: 'neo4j-knowledge-uri', keyVaultUrl: '${kvUri}secrets/neo4j-knowledge-uri', identity: managedIdentityId }
  { name: 'neo4j-knowledge-password', keyVaultUrl: '${kvUri}secrets/neo4j-knowledge-password', identity: managedIdentityId }
  { name: 'neo4j-guideline-uri', keyVaultUrl: '${kvUri}secrets/neo4j-guideline-uri', identity: managedIdentityId }
  { name: 'neo4j-guideline-password', keyVaultUrl: '${kvUri}secrets/neo4j-guideline-password', identity: managedIdentityId }
  { name: 'redis-url', keyVaultUrl: '${kvUri}secrets/redis-url', identity: managedIdentityId }
  { name: 'azure-ad-client-secret', keyVaultUrl: '${kvUri}secrets/azure-ad-client-secret', identity: managedIdentityId }
  { name: 'azure-ad-tenant-id', keyVaultUrl: '${kvUri}secrets/azure-ad-tenant-id', identity: managedIdentityId }
  { name: 'azure-openai-api-key', keyVaultUrl: '${kvUri}secrets/azure-openai-api-key', identity: managedIdentityId }
  { name: 'azure-storage-connection-string', keyVaultUrl: '${kvUri}secrets/azure-storage-connection-string', identity: managedIdentityId }
  { name: 'azure-service-bus-connection-string', keyVaultUrl: '${kvUri}secrets/azure-service-bus-connection-string', identity: managedIdentityId }
  { name: 'aws-access-key-id', keyVaultUrl: '${kvUri}secrets/aws-access-key-id', identity: managedIdentityId }
  { name: 'aws-secret-access-key', keyVaultUrl: '${kvUri}secrets/aws-secret-access-key', identity: managedIdentityId }
  { name: 'aws-big-model', keyVaultUrl: '${kvUri}secrets/aws-big-model', identity: managedIdentityId }
  { name: 'aws-small-model', keyVaultUrl: '${kvUri}secrets/aws-small-model', identity: managedIdentityId }
  { name: 'aws-max-model', keyVaultUrl: '${kvUri}secrets/aws-max-model', identity: managedIdentityId }
  { name: 'snomed-api-key', keyVaultUrl: '${kvUri}secrets/snomed-api-key', identity: managedIdentityId }
  { name: 'umls-api-key', keyVaultUrl: '${kvUri}secrets/umls-api-key', identity: managedIdentityId }
  { name: 'nhs-trud-api-key', keyVaultUrl: '${kvUri}secrets/nhs-trud-api-key', identity: managedIdentityId }
  { name: 'azure-ad-client-id', keyVaultUrl: '${kvUri}secrets/azure-ad-client-id', identity: managedIdentityId }
  { name: 'analytics-api-app-id', keyVaultUrl: '${kvUri}secrets/analytics-api-app-id', identity: managedIdentityId }
  { name: 'fhir-api-app-id', keyVaultUrl: '${kvUri}secrets/fhir-api-app-id', identity: managedIdentityId }
  { name: 'model-inference-app-id', keyVaultUrl: '${kvUri}secrets/model-inference-app-id', identity: managedIdentityId }
  { name: 'terminology-api-app-id', keyVaultUrl: '${kvUri}secrets/terminology-api-app-id', identity: managedIdentityId }
  { name: 'auth-secret', keyVaultUrl: '${kvUri}secrets/auth-secret', identity: managedIdentityId }
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
          // proxy.py / auth.py read *_API_BASE; audit_emitter uses FHIR_API_URL
          { name: 'FHIR_API_URL', value: fhirApiUrl }
          { name: 'FHIR_API_BASE', value: fhirApiUrl }
          { name: 'ANALYTICS_API_URL', value: analyticsApiUrl }
          { name: 'ANALYTICS_API_BASE', value: analyticsApiUrl }
          { name: 'CODING_MODEL_ENDPOINT', value: modelInferenceUrl }
          { name: 'PIPELINE_WORKER_URL', value: pipelineWorkerUrl }
          { name: 'SB_MAX_LOCK_RENEWAL_SECONDS', value: sbMaxLockRenewalSeconds }
          // URL of the UI -- controls OAuth redirects and invite email links.
          { name: 'FRONTEND_URL', value: frontendUrl }
          { name: 'AUTH_REDIRECT_URI', value: '${frontendUrl}/auth/callback' }
          { name: 'MAIL_FROM_ADDRESS', value: 'leo.support@healthcarecopilot.ai' }
        ])
        probes: [
          {
            type: 'Liveness'
            httpGet: { path: '/health', port: 8000, scheme: 'HTTP' }
            initialDelaySeconds: 10
            periodSeconds: 30
            failureThreshold: 3
          }
          {
            type: 'Readiness'
            httpGet: { path: '/health', port: 8000, scheme: 'HTTP' }
            initialDelaySeconds: 5
            periodSeconds: 10
            failureThreshold: 3
          }
        ]
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
        env: union(sharedEnv, [
          { name: 'INTERNAL_API_BASE', value: 'http://core-api' }
          { name: 'TERMINOLOGY_API_URL', value: termApiUrl }
          { name: 'TRAINING_WORKER_URL', value: 'http://training-worker' }
          { name: 'NODE_ENV', value: 'production' }
          // NextAuth needs the public base URL of this environment
          { name: 'AUTH_URL', value: frontendUrl }
          { name: 'NEXT_PUBLIC_API_BASE', value: '' }
        ])
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
        probes: [
          {
            type: 'Liveness'
            httpGet: { path: '/health', port: 8001, scheme: 'HTTP' }
            initialDelaySeconds: 10
            periodSeconds: 30
            failureThreshold: 3
          }
          {
            type: 'Readiness'
            httpGet: { path: '/health', port: 8001, scheme: 'HTTP' }
            initialDelaySeconds: 5
            periodSeconds: 10
            failureThreshold: 3
          }
        ]
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
        probes: [
          {
            type: 'Liveness'
            httpGet: { path: '/health', port: 8002, scheme: 'HTTP' }
            initialDelaySeconds: 10
            periodSeconds: 30
            failureThreshold: 3
          }
          {
            type: 'Readiness'
            httpGet: { path: '/health', port: 8002, scheme: 'HTTP' }
            initialDelaySeconds: 5
            periodSeconds: 10
            failureThreshold: 3
          }
        ]
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
        probes: [
          {
            type: 'Liveness'
            httpGet: { path: '/health', port: 8003, scheme: 'HTTP' }
            initialDelaySeconds: 10
            periodSeconds: 30
            failureThreshold: 3
          }
          {
            type: 'Readiness'
            httpGet: { path: '/health', port: 8003, scheme: 'HTTP' }
            initialDelaySeconds: 5
            periodSeconds: 10
            failureThreshold: 3
          }
        ]
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
        probes: [
          {
            type: 'Liveness'
            httpGet: { path: '/health', port: 8004, scheme: 'HTTP' }
            initialDelaySeconds: 15
            periodSeconds: 30
            failureThreshold: 3
          }
          {
            type: 'Readiness'
            httpGet: { path: '/health', port: 8004, scheme: 'HTTP' }
            initialDelaySeconds: 10
            periodSeconds: 10
            failureThreshold: 3
          }
        ]
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
        probes: [
          {
            type: 'Liveness'
            httpGet: { path: '/health', port: 8005, scheme: 'HTTP' }
            initialDelaySeconds: 10
            periodSeconds: 30
            failureThreshold: 3
          }
          {
            type: 'Readiness'
            httpGet: { path: '/health', port: 8005, scheme: 'HTTP' }
            initialDelaySeconds: 5
            periodSeconds: 10
            failureThreshold: 3
          }
        ]
      }]
      scale: { minReplicas: 0, maxReplicas: 1 }
    }
  }
}

// -- pipeline-worker (services/pipeline_worker: HTTP + Service Bus consumer)
// Matches local dev: scripts/start_leo-ai-core.ps1 -Services pipeline_worker
resource pipelineWorker 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'pipeline-worker'
  location: location
  identity: identityConfig
  properties: {
    environmentId: cae.id
    configuration: {
      secrets: sharedSecrets
      registries: registryConfig
      ingress: {
        external: false
        targetPort: 8006
        transport: 'http'
      }
    }
    template: {
      containers: [{
        name: 'pipeline-worker'
        image: usePlaceholder ? placeholderImage : '${acrLoginServer}/pipeline-worker:${imageTag}'
        resources: { cpu: json('1.0'), memory: '2Gi' }
        env: union(sharedEnv, [
          { name: 'NEO4J_USER', value: neo4jUser }
          { name: 'TERMINOLOGY_API_URL', value: termApiUrl }
          { name: 'CODING_MODEL_ENDPOINT', value: modelInferenceUrl }
          { name: 'ANALYTICS_API_URL', value: analyticsApiUrl }
          { name: 'PIPELINE_WORKER_PORT', value: '8006' }
          { name: 'PIPELINE_QUEUE_NAME', value: 'pipeline-jobs' }
          { name: 'SB_MAX_LOCK_RENEWAL_SECONDS', value: sbMaxLockRenewalSeconds }
        ])
        probes: [
          {
            type: 'Liveness'
            httpGet: { path: '/health', port: 8006, scheme: 'HTTP' }
            initialDelaySeconds: 10
            periodSeconds: 30
            failureThreshold: 3
          }
          {
            type: 'Readiness'
            httpGet: { path: '/health', port: 8006, scheme: 'HTTP' }
            initialDelaySeconds: 5
            periodSeconds: 10
            failureThreshold: 3
          }
        ]
      }]
      scale: {
        minReplicas: 1
        maxReplicas: 5
        rules: [{
          name: 'pipeline-jobs-keda'
          custom: {
            type: 'azure-servicebus'
            metadata: {
              queueName: 'pipeline-jobs'
              namespace: sbNamespaceFqdn
              messageCount: '5'
            }
            auth: [{
              secretRef: 'azure-service-bus-connection-string'
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
