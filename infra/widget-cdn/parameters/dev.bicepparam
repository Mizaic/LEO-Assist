using '../widget-cdn.bicep'

// Atlas trace: DO-3B62F38E (DI-3C06AFD0)
//
// Widget CDN is Azure Storage Static Website only (no Cloudflare).
// Set widgetPublicHost and WIDGET_PUBLIC_HOST to the storage web
// hostname from: az storage account show -n leoaiwidgetcdndev
//   --query primaryEndpoints.web -o tsv

param environment = 'dev'
param pinnedMajor = 'v1'
param widgetPublicHost = 'leoaiwidgetcdndev.z33.web.core.windows.net'
// REPLACE: object ID of the GitHub Actions OIDC service principal in your Entra tenant.
// Get it with: az ad sp show --id <AZURE_CLIENT_ID from GitHub secrets> --query id -o tsv
param githubActionsPrincipalId = 'REPLACE-WITH-YOUR-SP-OBJECT-ID'
