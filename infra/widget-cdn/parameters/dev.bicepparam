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
// leo-ai-github-deploy (OIDC for Healthcare-Copilot/LEO-AI-CORE:environment:dev)
param githubActionsPrincipalId = '617679ab-c524-46e2-b6e8-a620754bc942'
