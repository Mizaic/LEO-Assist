What you need to do in Azure
Corporate tenant (mizaic.com):

Create mailbox e.g. leo.support@mizaic.com
Create app registration LEO Mail Service
Run: MAIL_GRAPH_APP_ID=<client-id> ./scripts/entra_mail_graph_perms.sh
Admin-consent + create client secret
Per environment Key Vault: Add to secrets/.env, then:

.\infra\scripts\migrate-secrets.ps1 -Environment val
MAIL_GRAPH_TENANT_ID=<corporate-tenant-guid>
MAIL_GRAPH_CLIENT_ID=<mail-app-client-id>
MAIL_GRAPH_CLIENT_SECRET=<mail-app-secret>
Redeploy core-api (deploy.ps1) so the new secret refs are wired.

