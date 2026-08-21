// -- LEO AI Core - per-environment orchestrator ----------------------------
// Usage:
//   az deployment group create \
//     --resource-group leo-ai-{env} \
//     --template-file infra/bicep/main.bicep \
//     --parameters infra/bicep/parameters/{env}.bicepparam
targetScope = 'resourceGroup'

param environment string
param location string = resourceGroup().location
param imageTag string = 'latest'

// Non-secret config (safe to store in version control)
param neo4jUser string
param neo4jKnowledgeUser string
param awsDefaultRegion string
param azureOpenAiBigModel string
param azureOpenAiSmallModel string
param azureOpenAiApiVersion string
param azureOpenAiEndpoint string
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
param snomedTerminologyServer string = ''
// The public URL of the UI (e.g. https://leo-dev.healthcarecopilot.ai).
// Controls OAuth post-login redirects, the auth callback URI sent to Entra,
// and the sign-in link in invite emails. Must match an Entra redirect URI.
param frontendUrl string
// Optional: bind UI custom domain in Bicep so CD redeploys do not clear portal bindings.
// Set both, or leave both empty (hostname only, no scheme). Certificate = managed cert
// resource ID under the Container Apps environment.
param uiCustomHostname string = ''
param uiManagedCertificateId string = ''

// UI custom domain on the `ui` Container App (DNS + cert must exist; cert on the ACA environment).
param uiCustomDomainHost string = ''
param uiIngressCertificateName string = ''
param uiIngressCertificateIsManaged bool = false

// Azure Static Website hostname for the LEO widget CDN (no Cloudflare).
// Must match widgetPublicHost in infra/bicep/parameters/{env}.bicepparam
// (populated by deploy-widget-cdn.ps1 / sync-widget-cdn-params.ps1).
// and the GitHub WIDGET_PUBLIC_HOST secret.
param widgetPublicHost string = ''

// Graph API sender mailbox for invite and notification emails.
param mailFromAddress string

// Deploy Container Apps (requires Key Vault secrets to exist first).
// Set false for phase-1 bootstrap; deploy.ps1 -Bootstrap runs migrate-secrets between phases.
param deployContainerApps bool = true

// Knowledge graph tier label; defaults to environment. Set val and prod to the
// same value when Validation and Production share one Aura knowledge graph.
param knowledgeGraphEnvironment string = environment

// Shared resources (may live in a different subscription from the env stack)
param acrSubscriptionId string = subscription().subscriptionId
param acrResourceGroup string = 'leo-ai'
param acrName string = 'leoaicr'
param storageAccountSubscriptionId string = subscription().subscriptionId
param storageAccountResourceGroup string = 'leo-ai'
param storageAccountName string = 'leoaimodels'

// -- User-assigned managed identity (one per environment) ------------------
var identityName = 'leoai-${environment}-id'
resource managedIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: identityName
  location: location
}

// -- ACR Pull role on shared ACR (cross-RG module) -------------------------
module acrPullRole 'modules/acr-role.bicep' = {
  name: 'acr-pull-role'
  scope: resourceGroup(acrSubscriptionId, acrResourceGroup)
  params: {
    acrName: acrName
    principalId: managedIdentity.properties.principalId
  }
}

// -- Storage Blob Data Contributor on leoaimodels (cross-RG module) --------
module blobRole 'modules/blob-role.bicep' = {
  name: 'blob-contrib-role'
  scope: resourceGroup(storageAccountSubscriptionId, storageAccountResourceGroup)
  params: {
    storageAccountName: storageAccountName
    principalId: managedIdentity.properties.principalId
  }
}

// -- NER model artifact container (cross-RG module) ------------------------
module modelStoreBlobContainer 'modules/blob-container.bicep' = {
  name: 'model-store-container'
  scope: resourceGroup(storageAccountSubscriptionId, storageAccountResourceGroup)
  params: {
    storageAccountName: storageAccountName
    containerName: modelStoreContainer
  }
}

// -- Read ACR login server for Container Apps (existing reference) ----------
resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: acrName
  scope: resourceGroup(acrSubscriptionId, acrResourceGroup)
}

// -- Key Vault -------------------------------------------------------------
module keyvault 'modules/keyvault.bicep' = {
  name: 'keyvault'
  params: {
    environment: environment
    location: location
    managedIdentityPrincipalId: managedIdentity.properties.principalId
  }
}

// -- Service Bus -----------------------------------------------------------
module servicebus 'modules/servicebus.bicep' = {
  name: 'servicebus'
  params: {
    environment: environment
    location: location
    managedIdentityPrincipalId: managedIdentity.properties.principalId
  }
}

// -- Container Apps --------------------------------------------------------
// Redis and OpenAI are deployed separately (deploy-redis.ps1, deploy-openai.ps1).
// azureOpenAiEndpoint points at the shared OpenAI account (deploy-openai.ps1);
// key via migrate-secrets.ps1.
module containerApps 'modules/container-apps.bicep' = if (deployContainerApps) {
  name: 'container-apps'
  params: {
    environment: environment
    location: location
    managedIdentityId: managedIdentity.id
    managedIdentityClientId: managedIdentity.properties.clientId
    acrLoginServer: acr.properties.loginServer
    kvUri: keyvault.outputs.kvUri
    sbNamespaceFqdn: servicebus.outputs.sbNamespaceFqdn
    aoaiEndpoint: azureOpenAiEndpoint
    imageTag: imageTag
    neo4jUser: neo4jUser
    neo4jKnowledgeUser: neo4jKnowledgeUser
    awsDefaultRegion: awsDefaultRegion
    azureOpenAiBigModel: azureOpenAiBigModel
    azureOpenAiSmallModel: azureOpenAiSmallModel
    azureOpenAiApiVersion: azureOpenAiApiVersion
    codingExtractorBackend: codingExtractorBackend
    codingExtractorStrict: codingExtractorStrict
    storageAccountName: storageAccountName
    modelStoreContainer: modelStoreContainer
    modelStoreModelName: modelStoreModelName
    hitlLowConfidenceThreshold: hitlLowConfidenceThreshold
    hitlPeerReviewRate: hitlPeerReviewRate
    codingMode: codingMode
    modelMinPrecision: modelMinPrecision
    modelMinRecall: modelMinRecall
    sbMaxLockRenewalSeconds: sbMaxLockRenewalSeconds
    allowedOrigins: allowedOrigins
    cookieSecure: cookieSecure
    sessionTtlHours: sessionTtlHours
    snomedTerminologyServer: snomedTerminologyServer
    frontendUrl: frontendUrl
    uiCustomDomainHost: uiCustomDomainHost
    uiIngressCertificateName: uiIngressCertificateName
    uiIngressCertificateIsManaged: uiIngressCertificateIsManaged
    uiCustomHostname: uiCustomHostname
    uiManagedCertificateId: uiManagedCertificateId
    widgetPublicHost: widgetPublicHost
    mailFromAddress: mailFromAddress
    knowledgeGraphEnvironment: knowledgeGraphEnvironment
  }
}

output coreApiFqdn string = deployContainerApps ? containerApps.outputs.coreApiFqdn : ''
output uiFqdn string = deployContainerApps ? containerApps.outputs.uiFqdn : ''
output acaDefaultDomain string = deployContainerApps ? containerApps.outputs.acaDefaultDomain : ''
output deployContainerApps bool = deployContainerApps
output kvUri string = keyvault.outputs.kvUri
output sbNamespaceFqdn string = servicebus.outputs.sbNamespaceFqdn
output aoaiEndpoint string = azureOpenAiEndpoint
output storageAccountUrl string = 'https://${storageAccountName}.blob.${az.environment().suffixes.storage}'
