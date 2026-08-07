using '../main.bicep'

param environment = 'val'
param imageTag = 'latest'
param acrResourceGroup = 'leo-common-rg'
param acrName = 'mizaicleoacr'
// Cross-subscription: set acrSubscriptionId to the platform subscription GUID, or pass
// -AcrSubscriptionId to deploy.ps1. Same tenant required.
//   az group show -n leo-common-rg --subscription '<platform-sub>' --query id -o tsv
param acrSubscriptionId = 'b794024d-800e-452a-89a2-f8cb32af94db'
param storageAccountResourceGroup = 'leo-test-rg'
param storageAccountName = 'leoteststoresa'
// Cross-subscription: set storageAccountSubscriptionId if leo-test-rg is not in the val sub.
// param storageAccountSubscriptionId = '<platform-subscription-guid>'

// Neo4j
param neo4jUser = 'neo4j'
param neo4jKnowledgeUser = 'neo4j'

// AWS Bedrock (model ARNs stored in Key Vault as aws-big-model / aws-small-model / aws-max-model)
// Bedrock LLM calls are disabled by default via AWS_LLM_ENABLED=false in container-apps.bicep.
// Set AWS_LLM_ENABLED=true in ACA only when actively maintaining AWS credentials.
param awsDefaultRegion = 'eu-west-2'

// Azure OpenAI - shared account via deploy-openai.ps1; endpoint synced to bicepparam
param azureOpenAiEndpoint = 'https://mizaic-cds-oai.openai.azure.com/'
param azureOpenAiBigModel = 'gpt-5.4'
param azureOpenAiSmallModel = 'gpt-5.4-nano'
param azureOpenAiApiVersion = '2025-04-01-preview'

// Coding extractor
param codingExtractorBackend = 'llm'
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

// Security (widget origin added by deploy-widget-cdn.ps1 / sync-widget-cdn-params.ps1)
param allowedOrigins = 'https://leo-ai-audit-val.mizaic.cloud,https://leoaiwidgetcdnval.z33.web.core.windows.net'

// LEO widget CDN (auto-synced from deploy-widget-cdn.ps1; required before deploy.ps1)
param widgetPublicHost = 'leoaiwidgetcdnval.z33.web.core.windows.net'
param cookieSecure = 'true'
param sessionTtlHours = '12'

// SNOMED terminology server (set to your NHS SNOMED endpoint or leave blank to use local TRUD data)
param snomedTerminologyServer = ''

// Public URL of the UI for this environment.
// Update this when the ACA custom domain for validation is confirmed.
param frontendUrl = 'https://leo-ai-audit-val.mizaic.cloud'

// Graph API sender mailbox (@mizaic.com; corporate tenant via MAIL_GRAPH_* secrets)
param mailFromAddress = 'leo.support@mizaic.com'

// ACA Custom domains: hostname + environment certificate name (portal: Networking -> Custom domains).
// Leave empty to not use a custom domain, and instead publish the frontendUrl via an Application Gateway (via a deployment script)
param uiCustomDomainHost = ''
param uiIngressCertificateName = ''
param uiIngressCertificateIsManaged = false

// Validation shares the production knowledge graph Aura instance (neo4j+s://ecca11a1...).
param knowledgeGraphEnvironment = 'prod'

// Optional: bind UI custom domain in Bicep (hostname only + managed cert resource ID).
param uiCustomHostname = ''
param uiManagedCertificateId = ''
