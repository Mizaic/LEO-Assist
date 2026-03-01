using '../main.bicep'

param environment = 'dev'
param imageTag = 'latest'

// Neo4j
param neo4jUser = 'neo4j'
param neo4jKnowledgeUser = 'neo4j'

// Azure AD
param azureAdTenantId = ''   // fill in: az account show --query tenantId -o tsv

// AWS Bedrock
param awsBedrockModel = 'arn:aws:bedrock:eu-west-2:204065380870:inference-profile/eu.anthropic.claude-sonnet-4-5-20250929-v1:0'
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
param modelMinPrecision = '0.80'

// Service Bus
param sbMaxLockRenewalSeconds = '14400'

// Security
param allowedOrigins = 'https://ui.dev.leoai.example.com,http://localhost:3000'
param cookieSecure = 'true'
param sessionTtlHours = '12'
