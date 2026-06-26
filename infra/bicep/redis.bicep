// -- LEO AI Core - Azure Managed Redis (standalone deploy) ------------------
// Usage:
//   pwsh ./infra/scripts/deploy-redis.ps1 -Environment dev
//   az deployment group create \
//     --resource-group leo-ai-dev \
//     --template-file infra/bicep/redis.bicep \
//     --parameters infra/bicep/parameters/redis/dev.bicepparam
//
// Provision before the main stack (deploy.ps1). Redis Enterprise takes
// 20-30 min on first create. Connection string goes to Key Vault via
// migrate-secrets.ps1 (REDIS_URL -> redis-url).

targetScope = 'resourceGroup'

param environment string
param location string = resourceGroup().location
param redisSkuName string = 'Balanced_B0'
param redisHighAvailability string = 'Disabled'

module redis 'modules/redis.bicep' = {
  name: 'redis'
  params: {
    environment: environment
    location: location
    skuName: redisSkuName
    highAvailability: redisHighAvailability
  }
}

output redisHostname string = redis.outputs.redisHostname
output redisPort int = redis.outputs.redisPort
output redisName string = redis.outputs.redisName
output redisId string = redis.outputs.redisId
