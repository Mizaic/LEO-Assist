using '../main.bicep'

param environment = 'val'
param imageTag = 'latest'

// Neo4j
param neo4jUser = 'neo4j'
param neo4jKnowledgeUser = 'neo4j'

// AWS Bedrock (model ARNs stored in Key Vault as aws-big-model / aws-small-model / aws-max-model)
param awsDefaultRegion = 'eu-west-2'

// Azure OpenAI - endpoint hosted in EU
param azureOpenAiEndpoint = 'https://eu-ai-models.openai.azure.com/'
param azureOpenAiBigModel = 'gpt-5.2-chat'
param azureOpenAiSmallModel = 'gpt-5-mini'
param azureOpenAiApiVersion = '2024-12-01-preview'

// Coding extractor
param codingExtractorBackend = 'auto'
param codingExtractorStrict = 'false'

// Model store
param modelStoreContainer = 'ner-models'
param modelStoreModelName = 'medspacy_clinical_ner'

// HITL thresholds
param hitlLowConfidenceThreshold = '0.5'
param hitlPeerReviewRate = '0.10'
param codingMode = 'hitl'
param modelMinPrecision = '0.80'
param modelMinRecall = '0.75'

// Service Bus
param sbMaxLockRenewalSeconds = '14400'

// Security (include widget Static Website origin for /sdk/* from CDN surfaces)
param allowedOrigins = 'https://atlas-val.healthcarecopilot.ai,https://leoaiwidgetcdnval.z33.web.core.windows.net'

// LEO widget CDN (Azure Static Website; confirm suffix via primaryEndpoints.web)
param widgetPublicHost = 'leoaiwidgetcdnval.z33.web.core.windows.net'
param cookieSecure = 'true'
param sessionTtlHours = '12'

// SNOMED terminology server (set to your NHS SNOMED endpoint or leave blank to use local TRUD data)
param snomedTerminologyServer = ''

// Public URL of the UI for this environment.
// Update this when the ACA custom domain for validation is confirmed.
param frontendUrl = 'https://atlas-val.healthcarecopilot.ai'

param mailFromAddress = 'leo.support@healthcarecopilot.ai'

// Validation shares the production knowledge graph Aura instance (neo4j+s://ecca11a1...).
param knowledgeGraphEnvironment = 'prod'

// Optional: bind UI custom domain in Bicep (hostname only + managed cert resource ID).
param uiCustomHostname = ''
param uiManagedCertificateId = ''
