// -- Azure OpenAI (Cognitive Services account) ------------------------------
// Shared OpenAI account (mizaic-cds-oai) plus the live model deployments on
// leo-prod-rg (read 2026-08-25; gpt-5.6-sol and gpt-5.6-luna added 2026-10-09).
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

resource gpt54 'Microsoft.CognitiveServices/accounts/deployments@2026-03-01' = {
  parent: aoaiAccount
  name: 'gpt-5.4'
  sku: {
    name: 'GlobalStandard'
    capacity: 1000
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-5.4'
      version: '2026-03-05'
    }
    raiPolicyName: 'Microsoft.DefaultV2'
    versionUpgradeOption: 'OnceNewDefaultVersionAvailable'
  }
}

resource gpt5Mini 'Microsoft.CognitiveServices/accounts/deployments@2026-03-01' = {
  parent: aoaiAccount
  name: 'gpt-5-mini'
  sku: {
    name: 'GlobalStandard'
    capacity: 1000
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-5-mini'
      version: '2025-08-07'
    }
    raiPolicyName: 'Microsoft.DefaultV2'
    versionUpgradeOption: 'OnceNewDefaultVersionAvailable'
  }
}

resource gpt54Mini 'Microsoft.CognitiveServices/accounts/deployments@2026-03-01' = {
  parent: aoaiAccount
  name: 'gpt-5.4-mini'
  sku: {
    name: 'GlobalStandard'
    capacity: 1000
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-5.4-mini'
      version: '2026-03-17'
    }
    raiPolicyName: 'Microsoft.DefaultV2'
    versionUpgradeOption: 'OnceNewDefaultVersionAvailable'
  }
}

resource gpt54Nano 'Microsoft.CognitiveServices/accounts/deployments@2026-03-01' = {
  parent: aoaiAccount
  name: 'gpt-5.4-nano'
  sku: {
    name: 'GlobalStandard'
    capacity: 5000
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-5.4-nano'
      version: '2026-03-17'
    }
    raiPolicyName: 'Microsoft.DefaultV2'
    versionUpgradeOption: 'OnceNewDefaultVersionAvailable'
  }
}

resource gpt56Sol 'Microsoft.CognitiveServices/accounts/deployments@2026-03-01' = {
  parent: aoaiAccount
  name: 'gpt-5.6-sol'
  sku: {
    name: 'GlobalStandard'
    capacity: 4000
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-5.6-sol'
      version: '2026-07-09'
    }
    raiPolicyName: 'Microsoft.DefaultV2'
    versionUpgradeOption: 'OnceNewDefaultVersionAvailable'
  }
}

resource gpt56Luna 'Microsoft.CognitiveServices/accounts/deployments@2026-03-01' = {
  parent: aoaiAccount
  name: 'gpt-5.6-luna'
  sku: {
    name: 'GlobalStandard'
    capacity: 4000
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-5.6-luna'
      version: '2026-07-09'
    }
    raiPolicyName: 'Microsoft.DefaultV2'
    versionUpgradeOption: 'OnceNewDefaultVersionAvailable'
  }
}

output endpoint string = 'https://${aoaiName}.openai.azure.com/'
output accountName string = aoaiAccount.name
output accountId string = aoaiAccount.id
