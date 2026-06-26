// -- Azure Managed Redis (Microsoft.Cache/redisEnterprise) ------------------
// Balanced_B0 default matches dev sizing. Provision time is typically 20-30 min.
param location string = resourceGroup().location
param environment string
param skuName string = 'Balanced_B0'
param highAvailability string = 'Disabled'
param publicNetworkAccess string = 'Enabled'

var redisName = 'mizaicai-${environment}-redis'

resource redisEnterprise 'Microsoft.Cache/redisEnterprise@2025-07-01' = {
  name: redisName
  location: location
  sku: {
    name: skuName
  }
  properties: {
    minimumTlsVersion: '1.2'
    highAvailability: highAvailability
    publicNetworkAccess: publicNetworkAccess
  }
}

resource redisDatabase 'Microsoft.Cache/redisEnterprise/databases@2025-07-01' = {
  parent: redisEnterprise
  name: 'default'
  properties: {
    clientProtocol: 'Encrypted'
    port: 10000
    clusteringPolicy: 'NoCluster'
    evictionPolicy: 'NoEviction'
    persistence: {
      aofEnabled: false
      rdbEnabled: false
    }
    deferUpgrade: 'NotDeferred'
    accessKeysAuthentication: 'Enabled'
  }
}

output redisHostname string = redisEnterprise.properties.hostName
output redisPort int = redisDatabase.properties.port
output redisName string = redisEnterprise.name
output redisId string = redisEnterprise.id
