using '../main.bicep'

param environment = 'dev'
param imageTag = 'latest'
param acrResourceGroup = 'leo-common-rg'
param acrName = 'mizaicleoacr'
param storageAccountResourceGroup = 'leo-test-rg'
param storageAccountName = 'leoteststoresa'

// Neo4j
param neo4jUser = 'neo4j'
param neo4jKnowledgeUser = 'neo4j'

// AWS Bedrock (model ARNs stored in Key Vault as aws-big-model / aws-small-model / aws-max-model)
param awsDefaultRegion = 'eu-west-2'

// Azure OpenAI - shared account via deploy-openai.ps1; endpoint synced to bicepparam
param azureOpenAiEndpoint = 'https://mizaic-cds-oai.openai.azure.com/'
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

// Security (custom domain first; keep ACA hostname for direct access; local dev)
// Widget Static Website origin is added by deploy-widget-cdn.ps1 / sync-widget-cdn-params.ps1.
param allowedOrigins = 'https://leo-ai-audit.healthcarecopilot.ai,https://ui.proudriver-82c5b80a.uksouth.azurecontainerapps.io,https://atlas-dev.healthcarecopilot.ai,https://leoaiwidgetcdndev.z33.web.core.windows.net,http://localhost:3000'

// LEO widget CDN (auto-synced from deploy-widget-cdn.ps1; required before deploy.ps1)
param widgetPublicHost = 'leoaiwidgetcdndev.z33.web.core.windows.net'
param cookieSecure = 'true'
param sessionTtlHours = '12'

// SNOMED terminology server (set to your NHS SNOMED endpoint or leave blank to use local TRUD data)
param snomedTerminologyServer = ''

// Public URL of the UI for this environment.
// - Must match an Entra app registration redirect URI (add /auth/callback suffix).
// - Controls OAuth post-login redirects, the auth callback sent to Entra,
//   and the sign-in link in invite emails.
param frontendUrl = 'https://leo-ai-audit.healthcarecopilot.ai'

// Graph API sender mailbox (corporate tenant via MAIL_GRAPH_*; dev may share prod mailbox)
param mailFromAddress = 'leo.support@mizaic.com'

// ACA Custom domains: hostname + environment certificate name (portal: Networking -> Custom domains).
// Leave empty to not use a custom domain, and instead publish the frontendUrl via an Application Gateway (via a deployment script)
param uiCustomDomainHost = ''
param uiIngressCertificateName = ''
param uiIngressCertificateIsManaged = false

// Optional: keep UI custom domain binding when GitHub Actions runs Bicep (see cd-deploy.yml).
// Hostname only (no https). Certificate ID from Portal (Container Apps env -> Certificates)
// or: az containerapp show -g leo-ai-dev -n ui --query properties.configuration.ingress.customDomains
// Leave empty until the managed certificate resource ID is filled in.
param uiCustomHostname = ''
param uiManagedCertificateId = ''
