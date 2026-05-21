using '../widget-cdn.bicep'

// Atlas trace: DO-3B62F38E (DI-3C06AFD0)
//
// Dev serves the widget directly from the Azure Static Website origin
// (no custom domain or Cloudflare edge). Update WIDGET_PUBLIC_HOST
// in GitHub dev secrets to match this hostname.

param environment = 'dev'
param pinnedMajor = 'v1'
param widgetPublicHost = 'leoaiwidgetcdndev.z33.web.core.windows.net'
// leo-ai-github-deploy (OIDC for Healthcare-Copilot/LEO-AI-CORE:environment:dev)
param githubActionsPrincipalId = '617679ab-c524-46e2-b6e8-a620754bc942'
