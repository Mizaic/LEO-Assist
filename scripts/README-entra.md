# Entra setup scripts

This folder contains helper scripts for the LEO Entra ID app
registrations. There are two distinct concerns:

1. **Internal service apps** -- one app reg per backend API (terminology,
   model-inference, FHIR, analytics) that LEO's managed identity calls.
   See `entra_setup.sh` / `entra_setup.ps1`.
2. **User-login app** -- the multi-tenant app reg whose appId is stored
   in Key Vault as `azure-ad-client-id` (env var `AZURE_AD_CLIENT_ID`).
   This is what users sign in with via OAuth authorization-code flow,
   and what the `/admin/portal` Entra extension uses for delegated
   Microsoft Graph calls (see DI-31F4C232 and DI-6CF7FCE0).

This README covers concern (2).

## When to run `entra_user_login_graph_perms.sh`

Run once, the first time you stand up the user-login app reg, and then
again any time the LEO admin portal needs additional Graph scopes. The
script is idempotent.

```bash
USER_LOGIN_APP_ID=<guid of the user-login app> \
REDIRECT_URI=https://leoai.example.com/api/auth/callback \
./entra_user_login_graph_perms.sh
```

## Scopes added

The script adds five **delegated** scopes (i.e. always run on-behalf-of
the signed-in admin -- LEO never holds application-only Graph
permissions):

| Scope | Purpose |
|-------|---------|
| `Domain.Read.All` | List the verified domains in a customer's tenant. |
| `User.Read.All` | Search the customer's directory by name or email. |
| `Group.Read.All` | Browse the customer's security groups. |
| `Group.ReadWrite.All` | Create new security groups for LEO roles. |
| `GroupMember.ReadWrite.All` | Add or remove users from groups. |

## Per-tenant admin consent

Each **customer tenant** (not LEO's own tenant) must grant consent
themselves. The script prints the consent URL with a `{tenant_id}`
placeholder; replace this with the customer's Entra tenant id (the
`tid` claim from any signed-in user from that tenant).

Example consent URL:

```
https://login.microsoftonline.com/{tenant_id}/v2.0/adminconsent
  ?client_id=<USER_LOGIN_APP_ID>
  &redirect_uri=https://leoai.example.com/api/auth/callback
  &scope=https://graph.microsoft.com/Domain.Read.All
        %20https://graph.microsoft.com/User.Read.All
        %20https://graph.microsoft.com/Group.Read.All
        %20https://graph.microsoft.com/Group.ReadWrite.All
        %20https://graph.microsoft.com/GroupMember.ReadWrite.All
```

The /admin/portal page surfaces this URL automatically for the signed-in
admin's tenant via `GET /api/admin/entra/capability` -- the
`admin_consent_url` field. The Entra integration tab links to it.

## Manual / Neo4j-only mode

If a customer chooses **not** to grant consent (or the OBO call fails
for any other reason), the admin portal degrades gracefully into the
manual mode described by DI-5A18A227: organisations, groups, and users
are managed entirely in Neo4j, and Entra is still used only for sign-in
authorisation. No Graph calls are made for that tenant.
