using '../widget-cdn.bicep'

// Atlas trace: DO-3B62F38E (DI-3C06AFD0)
//
// Widget CDN is Azure Storage Static Website only (no Cloudflare).
// Set widgetPublicHost to primaryEndpoints.web after provisioning.

param environment = 'val'
param pinnedMajor = 'v1'
param widgetPublicHost = 'leoaiwidgetcdnval.z33.web.core.windows.net'
param githubActionsPrincipalId = '617679ab-c524-46e2-b6e8-a620754bc942'
