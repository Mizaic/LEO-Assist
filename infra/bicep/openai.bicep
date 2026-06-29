// -- LEO AI Core - Azure OpenAI account (standalone deploy) -----------------
// Usage:
//   pwsh ./infra/scripts/deploy-openai.ps1
//   az deployment group create \
//     --resource-group leo-ai \
//     --template-file infra/bicep/openai.bicep \
//     --parameters infra/bicep/parameters/openai/shared.bicepparam
//
// Provision once into leo-prod-rg (shared with dev, val, and prod).
// azureOpenAiEndpoint in env bicepparam files is written by
// sync-openai-endpoint.ps1 (run from deploy-openai.ps1).

targetScope = 'resourceGroup'

param location string = resourceGroup().location
param skuName string = 'S0'
param openAiAccountName string = 'mizaic-cds-oai'
param publicNetworkAccess string = 'Enabled'

module openai 'modules/openai.bicep' = {
  name: openAiAccountName
  params: {
    location: location
    skuName: skuName
    publicNetworkAccess: publicNetworkAccess
    aoaiName: openAiAccountName
  }
}

output aoaiEndpoint string = openai.outputs.endpoint
output aoaiAccountName string = openai.outputs.accountName
output aoaiAccountId string = openai.outputs.accountId
