// -- Azure OpenAI -----------------------------------------------------------
// Resource created manually in portal; Bicep references it as existing
// to write the API key to Key Vault and expose outputs.
param environment string
param kvName string
param azureOpenAiBigModel string
param azureOpenAiSmallModel string

var aoaiName = 'leoai-${environment}-aoai'

resource aoai 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = {
  name: aoaiName
}

// Write API key into Key Vault so services can read it at startup
resource kv 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: kvName
}

resource aoaiKeySecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  name: 'azure-openai-api-key'
  parent: kv
  properties: {
    value: aoai.listKeys().key1
  }
}

output aoaiEndpoint string = aoai.properties.endpoint
output aoaiBigDeploymentName string = azureOpenAiBigModel
output aoaiSmallDeploymentName string = azureOpenAiSmallModel
