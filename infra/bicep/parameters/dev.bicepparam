using '../main.bicep'

param environment = 'dev'
param imageTag = 'latest'

// Neo4j
param neo4jUser = 'neo4j'
param neo4jKnowledgeUser = 'neo4j'

// AWS Bedrock (model ARNs stored in Key Vault as aws-big-model / aws-small-model / aws-max-model)
param awsDefaultRegion = 'eu-west-2'

// Azure OpenAI - endpoint hosted in EU, key migrated via migrate-secrets.ps1
param azureOpenAiEndpoint = 'https://eu-ai-models.openai.azure.com/'
param azureOpenAiBigModel = 'gpt-5.2-chat'
param azureOpenAiSmallModel = 'gpt-5-mini'
param azureOpenAiApiVersion = '2024-12-01-preview'

// Coding extractor
param codingExtractorBackend = 'llm'
param codingExtractorStrict = 'false'

// Model store (references existing leoaimodels storage account)
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
param allowedOrigins = 'https://atlas-dev.healthcarecopilot.ai,http://localhost:3000'
param cookieSecure = 'true'
param sessionTtlHours = '12'

// SNOMED terminology server (set to your NHS SNOMED endpoint or leave blank to use local TRUD data)
param snomedTerminologyServer = ''

// Public URL of the UI for this environment.
// - Must match an Entra app registration redirect URI (add /auth/callback suffix).
// - Controls OAuth post-login redirects, the auth callback sent to Entra,
//   and the sign-in link in invite emails.
param frontendUrl = 'https://atlas-dev.healthcarecopilot.ai'
