// -- Key Vault per environment ----------------------------------------------
param location string = resourceGroup().location
param environment string
param managedIdentityPrincipalId string

var kvName = 'mizaicai-${environment}-kv'

resource kv 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: kvName
  location: location
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    publicNetworkAccess: 'Enabled'
  }
}

// Key Vault Secrets User role ID (built-in)
var kvSecretsUserRoleId = '4633458b-17de-408a-b874-0445c86b69e6'

resource kvRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(kv.id, managedIdentityPrincipalId, kvSecretsUserRoleId)
  scope: kv
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      kvSecretsUserRoleId
    )
    principalId: managedIdentityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

output kvId string = kv.id
output kvName string = kv.name
output kvUri string = kv.properties.vaultUri
