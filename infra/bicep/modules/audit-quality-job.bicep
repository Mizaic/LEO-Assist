// -- Audit Quality Container App Job ------------------------------------------
// Azure Container Apps Job that runs the weekly audit quality check.
// Schedule: 02:00 UTC every Monday (cron "0 2 * * 1").
//
// Mounts an Azure Files share for the SQLite checkpoint file so the run can
// be safely resumed if interrupted. Secrets are pulled from Key Vault via
// the managed identity.
//
// Design traceability: Loop 1 (audit quality) -- see plan v3.2 Sprint 3.

param location string = resourceGroup().location
param environment string
param managedIdentityId string
param managedIdentityClientId string
param acrLoginServer string
param containerAppsEnvironmentId string
param kvUri string
param storageAccountName string
param storageAccountKey string
param imageTag string = 'placeholder'

var usePlaceholder = imageTag == 'placeholder'
var image = usePlaceholder
  ? 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
  : '${acrLoginServer}/core-api:${imageTag}'

var registryConfig = usePlaceholder ? [] : [{
  server: acrLoginServer
  identity: managedIdentityId
}]

var storageShareName = 'audit-checkpoint'
var storageMountPath = '/mnt/audit-checkpoint'

resource auditQualityJob 'Microsoft.App/jobs@2023-05-01' = {
  name: 'audit-quality-${environment}'
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
      replicaTimeout: 10800        // 3 hours maximum run time
      replicaRetryLimit: 1
      scheduleTriggerConfig: {
        cronExpression: '0 2 * * 1'  // 02:00 UTC every Monday
        parallelism: 1
        replicaCompletionCount: 1
      }
      registries: registryConfig
      secrets: [
        {
          name: 'neo4j-uri'
          keyVaultUrl: '${kvUri}/secrets/NEO4J-URI'
          identity: managedIdentityId
        }
        {
          name: 'neo4j-password'
          keyVaultUrl: '${kvUri}/secrets/NEO4J-PASSWORD'
          identity: managedIdentityId
        }
        {
          name: 'aws-access-key-id'
          keyVaultUrl: '${kvUri}/secrets/AWS-ACCESS-KEY-ID'
          identity: managedIdentityId
        }
        {
          name: 'aws-secret-access-key'
          keyVaultUrl: '${kvUri}/secrets/AWS-SECRET-ACCESS-KEY'
          identity: managedIdentityId
        }
        {
          name: 'storage-account-key'
          value: storageAccountKey
        }
      ]
    }
    template: {
      volumes: [
        {
          name: 'audit-checkpoint-vol'
          storageType: 'AzureFile'
          storageName: 'audit-checkpoint-storage'
        }
      ]
      containers: [
        {
          name: 'audit-quality'
          image: image
          resources: {
            cpu: '2.0'
            memory: '4Gi'
          }
          command: [
            'python'
            'scripts/investigations/audit_encounter_coding.py'
            '--yes'
            '--workers'
            '5'
            '--tier'
            'big'
            '--since-days'
            '7'
            '--triggered-by'
            'schedule'
            '--output'
            '/mnt/audit-checkpoint/encounter_audit'
          ]
          volumeMounts: [
            {
              volumeName: 'audit-checkpoint-vol'
              mountPath: storageMountPath
            }
          ]
          env: [
            {
              name: 'AZURE_CLIENT_ID'
              value: managedIdentityClientId
            }
            {
              name: 'AZURE_KEYVAULT_URL'
              value: kvUri
            }
            {
              name: 'NEO4J_URI'
              secretRef: 'neo4j-uri'
            }
            {
              name: 'NEO4J_PASSWORD'
              secretRef: 'neo4j-password'
            }
            {
              name: 'AWS_ACCESS_KEY_ID'
              secretRef: 'aws-access-key-id'
            }
            {
              name: 'AWS_SECRET_ACCESS_KEY'
              secretRef: 'aws-secret-access-key'
            }
            {
              name: 'AWS_DEFAULT_REGION'
              value: 'eu-west-2'
            }
          ]
        }
      ]
    }
  }
}

resource auditCheckpointStorage 'Microsoft.App/managedEnvironmentsStorages@2023-05-01' = {
  parent: auditQualityJob
  name: 'audit-checkpoint-storage'
  properties: {
    azureFile: {
      accountName: storageAccountName
      accountKey: storageAccountKey
      shareName: storageShareName
      accessMode: 'ReadWrite'
    }
  }
}

output jobName string = auditQualityJob.name
output jobId string = auditQualityJob.id
