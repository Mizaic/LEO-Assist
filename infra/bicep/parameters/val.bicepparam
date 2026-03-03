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

// Security
param allowedOrigins = 'https://atlas-val.healthcarecopilot.ai'
param cookieSecure = 'true'
param sessionTtlHours = '12'

// SNOMED terminology server (set to your NHS SNOMED endpoint or leave blank to use local TRUD data)
param snomedTerminologyServer = ''

// Public URL of the UI for this environment.
// Update this when the ACA custom domain for validation is confirmed.
param frontendUrl = 'https://atlas-val.healthcarecopilot.ai'
