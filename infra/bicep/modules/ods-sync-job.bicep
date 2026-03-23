// -- ODS Nightly Sync Job -------------------------------------------------------
// Azure Container Apps Job that runs the ODS FHIR sync nightly at 02:00 UTC.
// Trigger: Schedule (cron). Uses the same managed identity as the other ACA apps.
//
// Risk design: R-LEO-AI-038 through R-LEO-AI-045
// Verification: VT-LEO-AI-048

param location string = resourceGroup().location
param environment string
param managedIdentityId string
param managedIdentityClientId string
param acrLoginServer string
param containerAppsEnvironmentId string
param kvUri string
param imageTag string = 'placeholder'

var usePlaceholder = imageTag == 'placeholder'
var image = usePlaceholder
  ? 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
  : '${acrLoginServer}/ods-sync:${imageTag}'

var registryConfig = usePlaceholder ? [] : [{
  server: acrLoginServer
  identity: managedIdentityId
}]

resource odsSyncJob 'Microsoft.App/jobs@2023-05-01' = {
  name: 'ods-sync-${environment}'
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
      replicaTimeout: 7200        // 2 hours maximum run time
      replicaRetryLimit: 1        // retry once on non-zero exit
      scheduleTriggerConfig: {
        cronExpression: '0 2 * * *'   // 02:00 UTC nightly
        parallelism: 1
        replicaCompletionCount: 1
      }
      registries: registryConfig
    }
    template: {
      containers: [
        {
          name: 'ods-sync'
          image: image
          resources: {
            cpu: '0.5'
            memory: '1Gi'
          }
          env: [
            {
              name: 'AZURE_KEYVAULT_URL'
              value: kvUri
            }
            {
              name: 'AZURE_CLIENT_ID'
              value: managedIdentityClientId
            }
            {
              name: 'ODS_SYNC_CIRCUIT_THRESHOLD'
              value: '5'
            }
            {
              name: 'ODS_SYNC_DELAY_MS'
              value: '1000'
            }
            {
              name: 'ODS_SYNC_MAX_RETRIES'
              value: '3'
            }
            {
              name: 'ODS_SYNC_BATCH_SIZE'
              value: '500'
            }
            {
              name: 'FHIR_API_URL'
              secretRef: 'fhir-api-url'
            }
            {
              name: 'NEO4J_PATIENT_URI'
              secretRef: 'neo4j-patient-uri'
            }
            {
              name: 'NEO4J_PATIENT_USER'
              secretRef: 'neo4j-patient-user'
            }
            {
              name: 'NEO4J_PATIENT_PASSWORD'
              secretRef: 'neo4j-patient-password'
            }
          ]
        }
      ]
    }
  }
}

output jobName string = odsSyncJob.name
output jobId string = odsSyncJob.id
