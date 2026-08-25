using '../main.bicep'

param environment = 'prod'
param imageTag = 'latest'
param acrResourceGroup = 'leo-common-rg'
param acrName = 'mizaicleoacr'
param storageAccountResourceGroup = 'leo-ai'
param storageAccountName = 'leoaimodels'
// Neo4j
param neo4jUser = 'neo4j'
param neo4jKnowledgeUser = 'neo4j'

// AWS Bedrock (model ARNs stored in Key Vault as aws-big-model / aws-small-model / aws-max-model)
param awsDefaultRegion = 'eu-west-2'

// Azure OpenAI - match live leo-ai-prod Container Apps (read 2026-08-25).
// Most apps: gpt-5.2-chat / gpt-5-mini. pipeline-worker: gpt-5.4 / gpt-5.4-nano.
// PIPELINE_MODEL_PROVIDER is aws, but AWS_LLM_ENABLED stays false in the module
// so calls still go to Azure (same as the live apps).
param azureOpenAiEndpoint = 'https://mizaic-cds-oai.openai.azure.com/'
param azureOpenAiBigModel = 'gpt-5.2-chat'
param azureOpenAiSmallModel = 'gpt-5-mini'
param azureOpenAiApiVersion = '2024-12-01-preview'
param pipelineModelProvider = 'aws'
param azureOpenAiWorkerBigModel = 'gpt-5.4'
param azureOpenAiWorkerSmallModel = 'gpt-5.4-nano'
param azureUseReasoningSmall = 'true'
param azureUseReasoningBig = 'false'
param azureReasoningEffortSmall = 'low'

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

// Security (widget origin added by deploy-widget-cdn.ps1 / sync-widget-cdn-params.ps1)
param allowedOrigins = 'https://leo-ai-audit.mizaic.cloud,https://leoaiwidgetcdnprod.z33.web.core.windows.net'

// LEO widget CDN (auto-synced from deploy-widget-cdn.ps1; required before deploy.ps1)
param widgetPublicHost = 'leoaiwidgetcdnprod.z33.web.core.windows.net'
param cookieSecure = 'true'
param sessionTtlHours = '24'

// SNOMED terminology server (NHS production endpoint)
param snomedTerminologyServer = 'https://ontology.nhs.uk/production1/fhir'

// Public URL of the UI for this environment.
param frontendUrl = 'https://leo-ai-audit.mizaic.cloud'

// Graph API sender mailbox (@mizaic.com; corporate tenant via MAIL_GRAPH_* secrets)
param mailFromAddress = 'leo.support@mizaic.com'

// Production knowledge graph tier (shared with validation).
// ACA Custom domains: hostname + environment certificate name (portal: Networking -> Custom domains).
// Leave empty to not use a custom domain, and instead publish the frontendUrl via an Application Gateway (via a deployment script)
param uiCustomDomainHost = ''
param uiIngressCertificateName = ''
param uiIngressCertificateIsManaged = false
param knowledgeGraphEnvironment = 'prod'

// Optional: bind UI custom domain in Bicep (hostname only + managed cert resource ID).
param uiCustomHostname = ''
param uiManagedCertificateId = ''
