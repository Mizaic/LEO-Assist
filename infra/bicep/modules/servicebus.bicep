// -- Azure Service Bus ------------------------------------------------------
param location string = resourceGroup().location
param environment string
param managedIdentityPrincipalId string

var sbNamespaceName = 'leoai-${environment}-bus'

resource sbNamespace 'Microsoft.ServiceBus/namespaces@2022-10-01-preview' = {
  name: sbNamespaceName
  location: location
  sku: {
    name: 'Standard'
    tier: 'Standard'
  }
  properties: {
    minimumTlsVersion: '1.2'
    disableLocalAuth: false
  }
}

resource codingJobsQueue 'Microsoft.ServiceBus/namespaces/queues@2022-10-01-preview' = {
  name: 'coding-jobs'
  parent: sbNamespace
  properties: {
    lockDuration: 'PT5M'
    maxDeliveryCount: 10
    defaultMessageTimeToLive: 'P1D'
  }
}

resource analysisJobsQueue 'Microsoft.ServiceBus/namespaces/queues@2022-10-01-preview' = {
  name: 'analysis-jobs'
  parent: sbNamespace
  properties: {
    lockDuration: 'PT5M'
    maxDeliveryCount: 10
    defaultMessageTimeToLive: 'P1D'
  }
}

// Primary queue for services/pipeline_worker (see PIPELINE_QUEUE_NAME, default pipeline-jobs)
resource pipelineJobsQueue 'Microsoft.ServiceBus/namespaces/queues@2022-10-01-preview' = {
  name: 'pipeline-jobs'
  parent: sbNamespace
  properties: {
    lockDuration: 'PT5M'
    maxDeliveryCount: 10
    defaultMessageTimeToLive: 'P1D'
  }
}

// Azure Service Bus Data Owner role (built-in)
var sbDataOwnerRoleId = '090c5cfd-751d-490a-894a-3ce6f1109419'

resource sbRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(sbNamespace.id, managedIdentityPrincipalId, sbDataOwnerRoleId)
  scope: sbNamespace
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      sbDataOwnerRoleId
    )
    principalId: managedIdentityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

output sbNamespaceFqdn string = '${sbNamespaceName}.servicebus.windows.net'
output sbNamespaceId string = sbNamespace.id
