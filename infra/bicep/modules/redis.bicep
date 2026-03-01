// -- Azure Managed Redis (Balanced_B0) -------------------------------------
// Resource created via portal/CLI; Bicep references it as existing
// to expose hostname/port outputs for deploy.ps1 key retrieval.
param environment string

var redisName = 'leoai-${environment}-redis'

resource redisEnterprise 'Microsoft.Cache/redisEnterprise@2025-07-01' existing = {
  name: redisName
}

output redisHostname string = redisEnterprise.properties.hostName
output redisPort int = 10000
output redisName string = redisEnterprise.name
