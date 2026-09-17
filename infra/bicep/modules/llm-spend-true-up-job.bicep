// Daily LLM spend true-up job. 0.5 vCPU / 1 GiB. Cron 07:00 UTC.
// Atlas: DI-3E297B23

param location string = resourceGroup().location
param environment string
param managedIdentityId string
param managedIdentityClientId string
param acrLoginServer string
param containerAppsEnvironmentId string
param kvUri string
param imageTag string = 'placeholder'
param mailAlertsFromAddress string = ''
param mailAlertsToAddresses string = ''
param azureOpenAiResourceId string = ''
param azureSubscriptionId string = subscription().subscriptionId

var usePlaceholder = imageTag == 'placeholder'
var image = usePlaceholder
  ? 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
  : '${acrLoginServer}/core-api:${imageTag}'

var registryConfig = usePlaceholder ? [] : [{
  server: acrLoginServer
  identity: managedIdentityId
}]

resource spendTrueUpJob 'Microsoft.App/jobs@2023-05-01' = {
  name: 'llm-spend-true-up-${environment}'
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${managedIdentityId}': {}
    }
  }
  properties: {
    environmentId: containerAppsEnvironmentId
    configuration: {
      triggerType: 'Schedule'
      replicaTimeout: 600
      replicaRetryLimit: 1
      scheduleTriggerConfig: {
        cronExpression: '0 7 * * *'
        parallelism: 1
        replicaCompletionCount: 1
      }
      registries: registryConfig
      secrets: [
        {
          name: 'neo4j-patient-uri'
          keyVaultUrl: '${kvUri}secrets/neo4j-patient-uri'
          identity: managedIdentityId
        }
        {
          name: 'neo4j-patient-password'
          keyVaultUrl: '${kvUri}secrets/neo4j-patient-password'
          identity: managedIdentityId
        }
        {
          name: 'mail-graph-tenant-id'
          keyVaultUrl: '${kvUri}secrets/mail-graph-tenant-id'
          identity: managedIdentityId
        }
        {
          name: 'mail-graph-client-id'
          keyVaultUrl: '${kvUri}secrets/mail-graph-client-id'
          identity: managedIdentityId
        }
        {
          name: 'mail-graph-client-secret'
          keyVaultUrl: '${kvUri}secrets/mail-graph-client-secret'
          identity: managedIdentityId
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'llm-spend-true-up'
          image: image
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          command: ['/venv/bin/python']
          args: ['-m', 'libs.llm_spend_true_up']
          env: [
            { name: 'AZURE_CLIENT_ID', value: managedIdentityClientId }
            { name: 'AZURE_SUBSCRIPTION_ID', value: azureSubscriptionId }
            { name: 'AZURE_OPENAI_RESOURCE_ID', value: azureOpenAiResourceId }
            { name: 'LEO_ENVIRONMENT', value: environment }
            { name: 'NEO4J_URI', secretRef: 'neo4j-patient-uri' }
            { name: 'NEO4J_PASSWORD', secretRef: 'neo4j-patient-password' }
            { name: 'MAIL_GRAPH_TENANT_ID', secretRef: 'mail-graph-tenant-id' }
            { name: 'MAIL_GRAPH_CLIENT_ID', secretRef: 'mail-graph-client-id' }
            { name: 'MAIL_GRAPH_CLIENT_SECRET', secretRef: 'mail-graph-client-secret' }
            { name: 'MAIL_ALERTS_FROM_ADDRESS', value: mailAlertsFromAddress }
            { name: 'MAIL_ALERTS_TO_ADDRESSES', value: mailAlertsToAddresses }
          ]
        }
      ]
    }
  }
}

output jobName string = spendTrueUpJob.name
