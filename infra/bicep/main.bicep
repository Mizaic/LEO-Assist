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

// Shared resources live in the leo-ai platform RG
param acrResourceGroup string = 'leo-ai'
param acrName string = 'leoaicr'
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
  scope: resourceGroup(acrResourceGroup)
  params: {
    acrName: acrName
    principalId: managedIdentity.properties.principalId
  }
}

// -- Storage Blob Data Contributor on leoaimodels (cross-RG module) --------
module blobRole 'modules/blob-role.bicep' = {
  name: 'blob-contrib-role'
  scope: resourceGroup(storageAccountResourceGroup)
  params: {
    storageAccountName: storageAccountName
    principalId: managedIdentity.properties.principalId
  }
}

// -- Read ACR login server for Container Apps (existing reference) ----------
resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: acrName
  scope: resourceGroup(acrResourceGroup)
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

// -- Azure Managed Redis ---------------------------------------------------
module redis 'modules/redis.bicep' = {
  name: 'redis'
  params: {
    environment: environment
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
// Azure OpenAI endpoint + key come from secrets/.env via migrate-secrets.ps1.
module containerApps 'modules/container-apps.bicep' = {
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
  }
}

output coreApiFqdn string = containerApps.outputs.coreApiFqdn
output uiFqdn string = containerApps.outputs.uiFqdn
output kvUri string = keyvault.outputs.kvUri
output sbNamespaceFqdn string = servicebus.outputs.sbNamespaceFqdn
