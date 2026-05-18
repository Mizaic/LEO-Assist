// -- LEO widget CDN origin ------------------------------------------------
//
// Atlas trace
//   DO: DO-3B62F38E (auto-update + CSO rollback + advisory channel)
//   DI: DI-3C06AFD0
//   Look up via: get_design_control(dc_type="design-output", dc_id="DO-3B62F38E")
//
// Architecture
//   Cloudflare DNS + edge cache (param widgetPublicHost; e.g.
//   widget.leo-ai-audit.healthcarecopilot.ai)
//        |  HTTPS, origin pull
//        v
//   Azure Storage Account (this resource), Static Website hosting
//     - $web/v1/leo-widget.js   (immutable per release)
//     - $web/v1/manifest.json   (mutable; CSO-controlled active hash)
//     - $web/v1/advisory.json   (mutable; CSO-published)
//     - $web/iframe/index.html  (hardened iframe entry document)
//     - $web/iframe/shell.js    (iframe entry script)
//
// Why a separate storage account
//   Public, anonymous read for widget assets must NEVER share an
//   account with patient-data blobs. Allowed network ACL is left
//   permissive (origin must be reachable by Cloudflare's IP ranges)
//   but the account holds no PII / PD by construction.
//
// Why static website (not Azure CDN / Front Door)
//   Cloudflare is the customer-facing CDN. The Azure side is just
//   the origin: Storage Static Website is the smallest blast-radius
//   surface that satisfies the requirement and supports rapid CSO
//   rollback (PUT a different blob, Cloudflare must-revalidate
//   picks it up within max-age=60).

targetScope = 'resourceGroup'

@description('Environment name used in the storage account name (dev, val, prod).')
param environment string

@description('Azure region.')
param location string = resourceGroup().location

@description('Pinned major version directory (e.g. v1).')
param pinnedMajor string = 'v1'

// The customer-facing FQDN that Cloudflare proxies to this origin.
// Set per environment in the bicepparam files. Used for output only;
// nothing in this module bakes the hostname into a resource. Hosting
// can move (different DNS host, different CDN, second origin) by
// changing this one parameter.
@description('Public widget FQDN (Cloudflare-proxied). e.g. widget.leo-ai-audit.healthcarecopilot.ai')
param widgetPublicHost string

// -- Storage account (origin) ---------------------------------------------
// Naming: leoaiwidgetcdn{env} (must be globally unique, 3-24 chars,
// lowercase, no dashes).
var accountName = toLower('leoaiwidgetcdn${environment}')

resource originAccount 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: accountName
  location: location
  sku: {
    name: 'Standard_GRS'
  }
  kind: 'StorageV2'
  properties: {
    accessTier: 'Hot'
    allowBlobPublicAccess: true
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    publicNetworkAccess: 'Enabled'
    networkAcls: {
      defaultAction: 'Allow'
      bypass: 'AzureServices'
    }
    allowSharedKeyAccess: true
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: originAccount
  name: 'default'
  properties: {
    cors: {
      corsRules: [
        {
          allowedOrigins: ['*']
          allowedMethods: ['GET', 'HEAD', 'OPTIONS']
          allowedHeaders: ['*']
          exposedHeaders: ['*']
          maxAgeInSeconds: 3600
        }
      ]
    }
    deleteRetentionPolicy: {
      enabled: true
      days: 30
    }
    isVersioningEnabled: true
  }
}

// $web is the magic container that backs Static Website hosting.
// Static website hosting itself is enabled out-of-band via:
//   az storage blob service-properties update
//     --account-name leoaiwidgetcdn{env}
//     --static-website
//     --index-document index.html
//     --404-document   404.html
// because the bicep type does not yet expose the staticWebsite flag.
resource webContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: '$web'
  properties: {
    publicAccess: 'Blob'
  }
}

// -- Outputs --------------------------------------------------------------
output originAccountName string = originAccount.name
output originPrimaryEndpoint string = originAccount.properties.primaryEndpoints.web
output pinnedMajorPath string = '${pinnedMajor}/'
output widgetPublicHost string = widgetPublicHost
output widgetPublicBundleUrl string = 'https://${widgetPublicHost}/${pinnedMajor}/leo-widget.js'
output widgetPublicManifestUrl string = 'https://${widgetPublicHost}/${pinnedMajor}/manifest.json'
output widgetPublicAdvisoryUrl string = 'https://${widgetPublicHost}/${pinnedMajor}/advisory.json'
output widgetPublicIframeUrl string = 'https://${widgetPublicHost}/iframe/index.html'
