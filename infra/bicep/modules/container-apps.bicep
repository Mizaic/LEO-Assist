// -- Container Apps Environment + all 9 apps ------------------------------
//
// Ingress policy (do not change without security review):
//   Only ui uses external ingress (public FQDN).
//   All other Container Apps must stay internal (ACA env DNS only).
//   CI enforces this in tests/test_infra_security.py (TestContainerAppsIngressPolicy).
//
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
var storageAccountUrl = 'https://${storageAccountName}.blob.${az.environment().suffixes.storage}'

// Non-secret config values passed from parameters file
param neo4jUser string
param neo4jKnowledgeUser string
param awsDefaultRegion string
param azureOpenAiBigModel string
param azureOpenAiSmallModel string
param azureOpenAiApiVersion string
param codingExtractorBackend string
param codingExtractorStrict string
param storageAccountName string
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
// Optional UI ingress custom domain (same hostname users open in the browser).
// If set with uiManagedCertificateId, Bicep declares customDomains on each deploy so
// GitHub Actions / az deployment group create does not drop a portal-only binding.
param uiCustomHostname string = ''
// ARM resource ID of the managed certificate in this Container Apps environment, e.g.
// /subscriptions/.../managedEnvironments/mizaicai-dev-cae/managedCertificates/<name>
param uiManagedCertificateId string = ''
param snomedTerminologyServer string = ''

// Optional UI hostname + env-scoped certificate (see ACA Custom domains blade).
// Certificate must already exist on the Container Apps environment (uploaded or managed).
param uiCustomDomainHost string = ''
param uiIngressCertificateName string = ''
param uiIngressCertificateIsManaged bool = false

// Azure Static Website hostname for the LEO widget CDN (DI-3C06AFD0).
param widgetPublicHost string = ''

// Sender address for Graph API mail (invite emails, notifications).
param mailFromAddress string

// Logical label for the knowledge graph deployment tier (defaults to environment).
// Set to the same value in val and prod when they share one Aura KG instance.
param knowledgeGraphEnvironment string = environment

var prefix = 'mizaicai-${environment}'
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

// -- Internal service URLs (same Container Apps environment) ---------------
// Backend apps use internal-only ingress, so service-to-service URLs must use
// the internal FQDN form exposed by the Container Apps environment.
var acaDefaultDomain = cae.properties.defaultDomain
var termApiUrl = 'https://terminology-api.internal.${acaDefaultDomain}'
var fhirApiUrl = 'https://fhir-api.internal.${acaDefaultDomain}'
var analyticsApiUrl = 'https://analytics-api.internal.${acaDefaultDomain}'
var modelInferenceUrl = 'https://model-inference.internal.${acaDefaultDomain}'
var pipelineWorkerUrl = 'https://pipeline-worker.internal.${acaDefaultDomain}'
var trainingWorkerUrl = 'https://training-worker.internal.${acaDefaultDomain}'
var researchWorkerUrl = 'https://research-worker.internal.${acaDefaultDomain}'
var coreApiInternalUrl = 'https://core-api.internal.${acaDefaultDomain}'

// -- Session namespace ----------------------------------------------------
// Every backend service that calls libs/redis_client/session.py::load_session
// must use the same Redis key prefix, otherwise inter-service session lookups
// (e.g. analytics-api validating an X-Leo-Session forwarded from core-api)
// silently miss and return 401. The Python fallback derives the namespace
// from the host of FRONTEND_URL when SESSION_KEY_NAMESPACE is unset, which
// only works on services where FRONTEND_URL is also set -- in our cluster
// only core-api has it. We therefore set SESSION_KEY_NAMESPACE explicitly
// on every container so the value is independent of which env vars happen
// to reach which service.
//
// Derivation matches Python's _detect_session_namespace(): take the host
// part of frontendUrl, then the first dotted label.
var _frontendHostPart = split(
  replace(replace(frontendUrl, 'https://', ''), 'http://', ''),
  '/'
)[0]
var sessionKeyNamespace = split(_frontendHostPart, '.')[0]

var hasUiTlsCustomDomain = !empty(uiCustomDomainHost) && !empty(uiIngressCertificateName)
var hasUiManagedCustomDomain = !empty(uiCustomHostname) && !empty(uiManagedCertificateId)
// Inner ternary: managed free cert vs uploaded / imported cert on the environment.
var uiIngressCertificateResourceId = hasUiTlsCustomDomain
  ? uiIngressCertificateIsManaged
      ? resourceId(
          'Microsoft.App/managedEnvironments/managedCertificates',
          caeName,
          uiIngressCertificateName
        )
      : resourceId(
          'Microsoft.App/managedEnvironments/certificates',
          caeName,
          uiIngressCertificateName
        )
  : ''
var uiIngressCustomDomains = hasUiTlsCustomDomain
  ? [
      {
        name: uiCustomDomainHost
        bindingType: 'SniEnabled'
        certificateId: uiIngressCertificateResourceId
      }
    ]
  : hasUiManagedCustomDomain
      ? [
          {
            name: uiCustomHostname
            bindingType: 'SniEnabled'
            certificateId: uiManagedCertificateId
          }
        ]
      : []

// -- Shared env vars injected into every app -------------------------------
var sharedEnv = [
  // Azure infrastructure
  { name: 'AZURE_KEYVAULT_URL', value: kvUri }
  { name: 'AZURE_CLIENT_ID', value: managedIdentityClientId }
  { name: 'AZURE_SERVICE_BUS_NAMESPACE', value: sbNamespaceFqdn }
  { name: 'AZURE_STORAGE_ACCOUNT_URL', value: storageAccountUrl }

  // Azure OpenAI (non-secret config)
  { name: 'OPENAI_API_TYPE', value: 'azure' }
  { name: 'AZURE_OPENAI_ENDPOINT', value: aoaiEndpoint }
  { name: 'AZURE_OPENAI_BIG_MODEL', value: azureOpenAiBigModel }
  { name: 'AZURE_OPENAI_SMALL_MODEL', value: azureOpenAiSmallModel }
  { name: 'AZURE_OPENAI_API_VERSION', value: azureOpenAiApiVersion }

  // AWS Bedrock (non-secret config)
  { name: 'AWS_DEFAULT_REGION', value: awsDefaultRegion }

  // Pipeline and coding extractor
  { name: 'PIPELINE_MODEL_PROVIDER', value: 'azure' }
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
  { name: 'TRANSFORMERS_OFFLINE', value: '1' }

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
  { name: 'SESSION_KEY_NAMESPACE', value: sessionKeyNamespace }
  { name: 'ALLOWED_ORIGINS', value: allowedOrigins }
  { name: 'CORS_ORIGINS', value: allowedOrigins }

  // -- Concurrency tuning (Phase 6 backend overhaul) -----------------------
  // Lift the anyio default threadpool ceiling so sync FastAPI handlers
  // (and any libs/auth call into Neo4j) do not bottleneck on Starlette's
  // default of 40 worker threads. Set per service in lifespan() too, but
  // putting it in the env keeps the value visible from `az containerapp
  // show` and overridable without a code change.
  { name: 'ANYIO_THREADPOOL_TOKENS', value: '200' }
  // Singleton Neo4j driver pool. NEO4J_MAX_POOL_SIZE bounds connections
  // per (uri, user); NEO4J_ACQUIRE_TIMEOUT keeps callers from waiting
  // forever when the pool is exhausted.
  { name: 'NEO4J_MAX_POOL_SIZE', value: '50' }
  { name: 'NEO4J_ACQUIRE_TIMEOUT', value: '60' }
  // CallerScope cache TTL -- 60s is the right balance between freshness
  // (org membership changes) and protecting Neo4j on every request.
  { name: 'CALLER_SCOPE_CACHE_TTL_SECONDS', value: '60' }
  // Audit dashboards fan out three scope queries (practice / alliance /
  // England) per endpoint; running them in a 3-wide threadpool roughly
  // thirds the wall-clock latency.
  { name: 'AUDIT_SCOPE_PARALLELISM', value: '3' }

  // Deployment tier (dev / val / prod) for startup guards and logging.
  { name: 'LEO_DEPLOYMENT_ENVIRONMENT', value: environment }
  { name: 'KNOWLEDGE_GRAPH_ENVIRONMENT', value: knowledgeGraphEnvironment }

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
  // Widget / Validation Lab SBAR token exchange (UI host + core-api).
  // UI also accepts SCENARIO_SDK_HOST_SECRET; SDK_HOST_SHARED_SECRET is enough.
  { name: 'SDK_HOST_SHARED_SECRET', secretRef: 'sdk-host-shared-secret' }
  { name: 'SDK_WIDGET_TOKEN_SECRET', secretRef: 'sdk-widget-token-secret' }
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
  { name: 'mail-graph-tenant-id', keyVaultUrl: '${kvUri}secrets/mail-graph-tenant-id', identity: managedIdentityId }
  { name: 'mail-graph-client-id', keyVaultUrl: '${kvUri}secrets/mail-graph-client-id', identity: managedIdentityId }
  { name: 'mail-graph-client-secret', keyVaultUrl: '${kvUri}secrets/mail-graph-client-secret', identity: managedIdentityId }
  { name: 'analytics-api-app-id', keyVaultUrl: '${kvUri}secrets/analytics-api-app-id', identity: managedIdentityId }
  { name: 'fhir-api-app-id', keyVaultUrl: '${kvUri}secrets/fhir-api-app-id', identity: managedIdentityId }
  { name: 'model-inference-app-id', keyVaultUrl: '${kvUri}secrets/model-inference-app-id', identity: managedIdentityId }
  { name: 'terminology-api-app-id', keyVaultUrl: '${kvUri}secrets/terminology-api-app-id', identity: managedIdentityId }
  { name: 'auth-secret', keyVaultUrl: '${kvUri}secrets/auth-secret', identity: managedIdentityId }
  { name: 'service-auth-secret', keyVaultUrl: '${kvUri}secrets/service-auth-secret', identity: managedIdentityId }
  { name: 'sdk-host-shared-secret', keyVaultUrl: '${kvUri}secrets/sdk-host-shared-secret', identity: managedIdentityId }
  { name: 'sdk-widget-token-secret', keyVaultUrl: '${kvUri}secrets/sdk-widget-token-secret', identity: managedIdentityId }
]

var identityConfig = {
  type: 'UserAssigned'
  userAssignedIdentities: {
    '${managedIdentityId}': {}
  }
}

// -- core-api (internal ingress) ------------------------------------------
// Sized for production: 1 vCPU lets uvicorn run with 2 workers comfortably,
// and the HTTP autoscale rule lets ACA add replicas when concurrent
// requests climb (target = 50 in-flight requests per replica).
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
        external: false
        targetPort: 8000
        transport: 'http'
      }
    }
    template: {
      containers: [{
        name: 'core-api'
        image: usePlaceholder ? placeholderImage : '${acrLoginServer}/core-api:${imageTag}'
        resources: { cpu: json('1.0'), memory: '2Gi' }
        env: union(sharedEnv, [
          { name: 'NEO4J_USER', value: neo4jUser }
          { name: 'KNOWLEDGE_GRAPH_NEO4J_USERNAME', value: neo4jKnowledgeUser }
          { name: 'TERMINOLOGY_API_URL', value: termApiUrl }
          // proxy.py / auth.py read *_API_BASE; audit_emitter uses FHIR_API_URL
          { name: 'FHIR_API_URL', value: fhirApiUrl }
          { name: 'FHIR_API_BASE', value: fhirApiUrl }
          { name: 'ANALYTICS_API_URL', value: analyticsApiUrl }
          { name: 'ANALYTICS_API_BASE', value: analyticsApiUrl }
          { name: 'CODING_MODEL_ENDPOINT', value: modelInferenceUrl }
          { name: 'PIPELINE_WORKER_URL', value: pipelineWorkerUrl }
          { name: 'RESEARCH_WORKER_URL', value: researchWorkerUrl }
          { name: 'SB_MAX_LOCK_RENEWAL_SECONDS', value: sbMaxLockRenewalSeconds }
          // URL of the UI -- controls OAuth redirects and invite email links.
          { name: 'FRONTEND_URL', value: frontendUrl }
          { name: 'AUTH_REDIRECT_URI', value: '${frontendUrl}/auth/callback' }
          { name: 'WIDGET_PUBLIC_HOST', value: widgetPublicHost }
          { name: 'MAIL_FROM_ADDRESS', value: mailFromAddress }
          { name: 'MAIL_GRAPH_TENANT_ID', secretRef: 'mail-graph-tenant-id' }
          { name: 'MAIL_GRAPH_CLIENT_ID', secretRef: 'mail-graph-client-id' }
          { name: 'MAIL_GRAPH_CLIENT_SECRET', secretRef: 'mail-graph-client-secret' }
          // Multi-worker uvicorn: 2 workers per 1.0 vCPU container is the
          // sweet spot before context-switching dominates. Distroless image
          // has no shell so we set UVICORN_WORKERS instead of using
          // shell-expanded WEB_CONCURRENCY.
          { name: 'UVICORN_WORKERS', value: '2' }
          // Seed the Validation Lab / scenario-runner SDK host at startup.
          { name: 'SCENARIO_SDK_HOST_ENABLED', value: '1' }
          { name: 'SCENARIO_SDK_HOST_ID', value: 'leo-scenario-runner' }
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
      scale: {
        minReplicas: 1
        maxReplicas: 6
        rules: [{
          name: 'core-api-http'
          http: {
            metadata: {
              concurrentRequests: '50'
            }
          }
        }]
      }
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
        customDomains: uiIngressCustomDomains
      }
    }
    template: {
      containers: [{
        name: 'ui'
        image: usePlaceholder ? placeholderImage : '${acrLoginServer}/ui:${imageTag}'
        resources: { cpu: json('0.5'), memory: '1Gi' }
        env: union(sharedEnv, [
          { name: 'INTERNAL_API_BASE', value: coreApiInternalUrl }
          { name: 'TERMINOLOGY_API_URL', value: termApiUrl }
          { name: 'TRAINING_WORKER_URL', value: trainingWorkerUrl }
          { name: 'PIPELINE_WORKER_URL', value: pipelineWorkerUrl }
          { name: 'NODE_ENV', value: 'production' }
          // NextAuth needs the public base URL of this environment
          { name: 'AUTH_URL', value: frontendUrl }
          { name: 'NEXT_PUBLIC_API_BASE', value: '' }
          // Tune the shared undici Agent used by Next.js Route Handlers
          // (see services/ui/src/lib/serverFetch.ts). 16 keep-alive
          // connections per upstream is enough headroom for a busy
          // dashboard hitting 5+ APIs in parallel.
          { name: 'UI_FETCH_CONNECTIONS_PER_HOST', value: '16' }
          { name: 'UI_FETCH_KEEPALIVE_MS', value: '30000' }
        ])
      }]
      scale: {
        minReplicas: 1
        maxReplicas: 4
        rules: [{
          name: 'ui-http'
          http: {
            metadata: {
              concurrentRequests: '100'
            }
          }
        }]
      }
    }
  }
}

// -- terminology-api (internal ingress) -- minReplicas: 1 keeps one warm instance so
// the first terminology/SNOMED search does not block for 20-60s on embedder load.
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
        resources: { cpu: json('0.5'), memory: '1Gi' }
        env: union(sharedEnv, [
          { name: 'KNOWLEDGE_GRAPH_NEO4J_USERNAME', value: neo4jKnowledgeUser }
          { name: 'UVICORN_WORKERS', value: '2' }
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
      scale: { minReplicas: 1, maxReplicas: 3 }
    }
  }
}

// -- fhir-api (internal ingress) -- minReplicas: 1 keeps one warm instance so
// benchmark and Measure requests do not block on cold start.
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
        resources: { cpu: json('0.5'), memory: '1Gi' }
        env: union(sharedEnv, [
          { name: 'NEO4J_USER', value: neo4jUser }
          { name: 'KNOWLEDGE_GRAPH_NEO4J_USERNAME', value: neo4jKnowledgeUser }
          { name: 'UVICORN_WORKERS', value: '2' }
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
      scale: { minReplicas: 1, maxReplicas: 3 }
    }
  }
}

// -- analytics-api (internal ingress) -- minReplicas: 1 keeps one warm instance so
// the UI dashboard does not block on a cold start (0 -> 1 takes ~30-60s in ACA).
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
        resources: { cpu: json('1.0'), memory: '2Gi' }
        env: union(sharedEnv, [
          { name: 'NEO4J_USER', value: neo4jUser }
          { name: 'KNOWLEDGE_GRAPH_NEO4J_USERNAME', value: neo4jKnowledgeUser }
          // Audit + dashboard pages drive the bulk of synchronous Neo4j
          // load. Two uvicorn workers + lifted threadpool ceiling lets us
          // service ~60 concurrent dashboard requests per replica.
          { name: 'UVICORN_WORKERS', value: '2' }
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
      scale: {
        minReplicas: 1
        maxReplicas: 6
        rules: [{
          name: 'analytics-api-http'
          http: {
            metadata: {
              concurrentRequests: '50'
            }
          }
        }]
      }
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
          // -- Concurrency tuning for the pipeline worker --
          // The Service Bus consumer now dispatches handlers concurrently
          // (libs/message_bus/azure_adapter.py); 8 in-flight messages per
          // replica matches the per-encounter LLM/Neo4j fan-out budget.
          { name: 'SB_MAX_CONCURRENT_CALLS', value: '8' }
          // Per-patient encounter dispatch parallelism (services/coding_worker
          // /app/services/job_handler.py).
          { name: 'CODING_ENCOUNTER_PARALLELISM', value: '4' }
          // Episode engine candidate fan-out (services/analysis_worker
          // /app/episode_engine/chain.py).
          { name: 'EPISODE_ENGINE_CANDIDATE_PARALLELISM', value: '8' }
          // Match the model_inference cap so we never queue more LLM
          // extracts than the inference service can absorb.
          { name: 'MODEL_INFERENCE_MAX_CONCURRENCY', value: '4' }
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
        maxReplicas: 10
        rules: [{
          name: 'pipeline-jobs-keda'
          custom: {
            type: 'azure-servicebus'
            metadata: {
              queueName: 'pipeline-jobs'
              namespace: sbNamespaceFqdn
              // Trigger a new replica for every 16 queued messages
              // (~2 in-flight per replica * SB_MAX_CONCURRENT_CALLS).
              messageCount: '16'
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

// -- research-worker (internal ingress) -- Pathway Explorer job executor ----
// Scales to 0 when no graph algorithm missions are running; scales up on
// Redis queue depth (KEDA http-requests trigger can be added when available).
resource researchWorker 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'research-worker'
  location: location
  identity: identityConfig
  properties: {
    environmentId: cae.id
    configuration: {
      secrets: sharedSecrets
      registries: registryConfig
      ingress: {
        external: false
        targetPort: 8007
        transport: 'http'
      }
    }
    template: {
      containers: [{
        name: 'research-worker'
        image: usePlaceholder ? placeholderImage : '${acrLoginServer}/research-worker:${imageTag}'
        resources: { cpu: json('1.0'), memory: '2Gi' }
        env: union(sharedEnv, [
          { name: 'NEO4J_USER', value: neo4jUser }
          { name: 'ANALYTICS_API_URL', value: analyticsApiUrl }
          { name: 'RESEARCH_WORKER_PORT', value: '8007' }
        ])
        probes: [
          {
            type: 'Liveness'
            httpGet: { path: '/health', port: 8007, scheme: 'HTTP' }
            initialDelaySeconds: 10
            periodSeconds: 30
            failureThreshold: 3
          }
          {
            type: 'Readiness'
            httpGet: { path: '/health', port: 8007, scheme: 'HTTP' }
            initialDelaySeconds: 5
            periodSeconds: 10
            failureThreshold: 3
          }
        ]
      }]
      scale: { minReplicas: 0, maxReplicas: 2 }
    }
  }
}

output coreApiFqdn string = coreApi.properties.configuration.ingress.fqdn
output uiFqdn string = ui.properties.configuration.ingress.fqdn
// Environment DNS suffix for in-mesh HTTP (e.g. proudriver-82c5b80a.uksouth.azurecontainerapps.io)
output acaDefaultDomain string = cae.properties.defaultDomain
