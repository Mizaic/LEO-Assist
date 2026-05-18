using '../widget-cdn.bicep'

// Atlas trace: DO-3B62F38E (DI-3C06AFD0)
//
// Hosting can move by changing widgetPublicHost. Update the
// Cloudflare DNS record + the WIDGET_PUBLIC_HOST GitHub secret to
// match.

param environment = 'dev'
param pinnedMajor = 'v1'
param widgetPublicHost = 'widget.leo-ai-dev.healthcarecopilot.ai'
