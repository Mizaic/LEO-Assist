using '../main.bicep'

param environment = 'prod'
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
param codingExtractorStrict = 'true'

// Model store
param modelStoreContainer = 'ner-models'
param modelStoreModelName = 'medspacy_clinical_ner'

// HITL thresholds (tighter in production)
param hitlLowConfidenceThreshold = '0.6'
param hitlPeerReviewRate = '0.10'
param codingMode = 'hitl'
param modelMinPrecision = '0.85'
param modelMinRecall = '0.80'

// Service Bus
param sbMaxLockRenewalSeconds = '14400'

// Security (longer sessions for clinical users; widget Static Website for /sdk/*)
param allowedOrigins = 'https://leo-ai-audit.healthcarecopilot.ai,https://leoaiwidgetcdnprod.z33.web.core.windows.net'

// LEO widget CDN (Azure Static Website; confirm suffix via primaryEndpoints.web)
param widgetPublicHost = 'leoaiwidgetcdnprod.z33.web.core.windows.net'
param cookieSecure = 'true'
param sessionTtlHours = '24'

// SNOMED terminology server (NHS production endpoint)
param snomedTerminologyServer = 'https://ontology.nhs.uk/production1/fhir'

// Public URL of the UI for this environment.
param frontendUrl = 'https://leo-ai-audit.healthcarecopilot.ai'

param mailFromAddress = 'leo.support@healthcarecopilot.ai'

// Production knowledge graph tier (shared with validation).
param knowledgeGraphEnvironment = 'prod'

// Optional: bind UI custom domain in Bicep (hostname only + managed cert resource ID).
param uiCustomHostname = ''
param uiManagedCertificateId = ''
