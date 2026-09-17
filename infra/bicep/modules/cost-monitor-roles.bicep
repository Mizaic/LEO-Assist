// Read-only Azure billing and metrics for the ACA managed identity.
// Atlas: DI-3E297B23
// Monitoring Reader + Cost Management Reader at subscription scope.

targetScope = 'subscription'

param principalId string

var monitoringReader = '43d0d8ad-25c7-4714-9337-8ba259a9fe05'
var costManagementReader = '72fafb9e-0643-461f-98f3-4fa3d8e2c0c3'

resource monitoringRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(subscription().id, principalId, monitoringReader)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', monitoringReader)
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

resource costRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(subscription().id, principalId, costManagementReader)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', costManagementReader)
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}
