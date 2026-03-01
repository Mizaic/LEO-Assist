// -- Storage Blob Data Contributor role assignment (deployed into leo-ai RG) -
// Called from main.bicep as a module with scope: resourceGroup(storageRG)
param storageAccountName string
param principalId string

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-01-01' existing = {
  name: storageAccountName
}

var blobContribRoleId = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'

resource roleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccount.id, principalId, blobContribRoleId)
  scope: storageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', blobContribRoleId)
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}
