using '../widget-cdn.bicep'

// Atlas trace: DO-3B62F38E (DI-3C06AFD0)
//
// Widget CDN is Azure Storage Static Website only (no Cloudflare).
// widgetPublicHost is written to infra/bicep/parameters/{env}.bicepparam by
// sync-widget-cdn-params.ps1 (run automatically from deploy-widget-cdn.ps1).

param environment = 'dev'
param pinnedMajor = 'v1'
// REPLACE: object ID of the GitHub Actions OIDC service principal in your Entra tenant.
// Get it with: az ad sp show --id <AZURE_CLIENT_ID from GitHub secrets> --query id -o tsv
param githubActionsPrincipalId = '3838a745-3003-4ed8-b226-a4f1562bb959'
