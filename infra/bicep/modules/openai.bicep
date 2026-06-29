// -- Azure OpenAI (Cognitive Services account) ------------------------------
// Shared OpenAI account (mizaicai-aoai) with default RAI policies.
// Does not include model deployments or testRaiExternalSafetyProvider.
param location string = resourceGroup().location
param skuName string = 'S0'
param publicNetworkAccess string = 'Enabled'
// param defenderForAiState string = 'Disabled'
// param raiSeverityThreshold string = 'Medium'
param aoaiName string = 'mizaic-cds-oai'


// var standardContentFilters = [
//   {
//     name: 'Hate'
//     severityThreshold: raiSeverityThreshold
//     blocking: true
//     enabled: true
//     source: 'Prompt'
//     action: 'NONE'
//   }
//   {
//     name: 'Hate'
//     severityThreshold: raiSeverityThreshold
//     blocking: true
//     enabled: true
//     source: 'Completion'
//     action: 'NONE'
//   }
//   {
//     name: 'Sexual'
//     severityThreshold: raiSeverityThreshold
//     blocking: true
//     enabled: true
//     source: 'Prompt'
//     action: 'NONE'
//   }
//   {
//     name: 'Sexual'
//     severityThreshold: raiSeverityThreshold
//     blocking: true
//     enabled: true
//     source: 'Completion'
//     action: 'NONE'
//   }
//   {
//     name: 'Violence'
//     severityThreshold: raiSeverityThreshold
//     blocking: true
//     enabled: true
//     source: 'Prompt'
//     action: 'NONE'
//   }
//   {
//     name: 'Violence'
//     severityThreshold: raiSeverityThreshold
//     blocking: true
//     enabled: true
//     source: 'Completion'
//     action: 'NONE'
//   }
//   {
//     name: 'Selfharm'
//     severityThreshold: raiSeverityThreshold
//     blocking: true
//     enabled: true
//     source: 'Prompt'
//     action: 'NONE'
//   }
//   {
//     name: 'Selfharm'
//     severityThreshold: raiSeverityThreshold
//     blocking: true
//     enabled: true
//     source: 'Completion'
//     action: 'NONE'
//   }
// ]

// var defaultV2ExtraFilters = [
//   {
//     name: 'Jailbreak'
//     blocking: true
//     enabled: true
//     source: 'Prompt'
//     action: 'NONE'
//   }
//   {
//     name: 'Protected Material Text'
//     blocking: true
//     enabled: true
//     source: 'Completion'
//     action: 'NONE'
//   }
//   {
//     name: 'Protected Material Code'
//     blocking: false
//     enabled: true
//     source: 'Completion'
//     action: 'NONE'
//   }
// ]

resource aoaiAccount 'Microsoft.CognitiveServices/accounts@2026-03-01' = {
  name: aoaiName
  location: location
  sku: {
    name: skuName
  }
  kind: 'OpenAI'
  properties: {
    apiProperties: {}
    customSubDomainName: aoaiName
    networkAcls: {
      defaultAction: 'Allow'
      virtualNetworkRules: []
      ipRules: []
    }
    allowProjectManagement: false
    publicNetworkAccess: publicNetworkAccess
    storedCompletionsDisabled: false
  }
}

// resource defenderForAi 'Microsoft.CognitiveServices/accounts/defenderForAISettings@2026-03-01' = {
//   parent: aoaiAccount
//   name: 'Default'
//   properties: {
//     state: defenderForAiState
//   }
// }

// resource raiPolicyDefault 'Microsoft.CognitiveServices/accounts/raiPolicies@2026-03-01' = {
//   parent: aoaiAccount
//   name: 'Microsoft.Default'
//   properties: {
//     mode: 'Blocking'
//     contentFilters: standardContentFilters
//   }
// }

// resource raiPolicyDefaultV2 'Microsoft.CognitiveServices/accounts/raiPolicies@2026-03-01' = {
//   parent: aoaiAccount
//   name: 'Microsoft.DefaultV2'
//   properties: {
//     mode: 'Blocking'
//     contentFilters: concat(standardContentFilters, defaultV2ExtraFilters)
//   }
// }

output endpoint string = 'https://${aoaiName}.openai.azure.com/'
output accountName string = aoaiAccount.name
output accountId string = aoaiAccount.id
