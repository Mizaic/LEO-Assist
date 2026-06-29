You do **not** create a separate service principal for the widget CDN. `deploy-widget-cdn` reuses the **same Entra app registration** as CI/CD (`cd-deploy.yml`, `widget-release.yml`). Bicep only needs that app's **service principal object ID** so it can grant **Storage Blob Data Contributor** on the widget storage account (shared keys are disabled).

## What `githubActionsPrincipalId` is

| ID | Used for |
|----|----------|
| **Client ID** (`appId`) | GitHub secret `AZURE_CLIENT_ID`; `azure/login` in workflows |
| **App registration object ID** | Creating federated credentials (`az ad app federated-credential create --id ...`) |
| **Service principal object ID** | `githubActionsPrincipalId` in bicepparam; RBAC role assignments |

Bicep wires the SP into blob RBAC here:

```106:112:infra/widget-cdn/widget-cdn.bicep
module githubBlobRole '../bicep/modules/blob-role.bicep' = {
  name: 'widget-cdn-github-blob-role'
  params: {
    storageAccountName: originAccount.name
    principalId: githubActionsPrincipalId
  }
}
```

That role lets `widget-release.yml` upload to `$web` with `--auth-mode login` after OIDC login.

---

## If CI/CD OIDC is not set up yet (greenfield)

### 1. Create the Entra app registration

```bash
az ad app create --display-name "LEO GitHub Actions"
```

Note the **Application (client) ID** from the output.

### 2. Create federated credentials

Edit the `subject` in each `.federated-cred-*.json` if your org/repo is not `Miazic/LEO-AI-CORE`, then:

```bash
# App registration OBJECT ID (not client ID)
APP_OBJECT_ID=$(az ad app show --id <CLIENT_ID> --query id -o tsv)

az ad app federated-credential create --id "$APP_OBJECT_ID" --parameters @.federated-cred-main.json
az ad app federated-credential create --id "$APP_OBJECT_ID" --parameters @.federated-cred-env-dev.json
az ad app federated-credential create --id "$APP_OBJECT_ID" --parameters @.federated-cred-env-validation.json
az ad app federated-credential create --id "$APP_OBJECT_ID" --parameters @.federated-cred-env-production.json
```

`widget-release.yml` uses GitHub environments `dev`, `validation`, and `production` -- the same three env federated creds as CD.

Full checklist: `infra/github-oidc/README.md` and DC-INST-001 Track F.

### 3. Grant Azure RBAC on the subscription

The SP needs permission to deploy infrastructure and push images:

| Role | Scope |
|------|--------|
| **Contributor** | `leo-ai-dev`, `leo-ai-val`, `leo-ai-prod`, `leo-widget-cdn-dev`, `leo-widget-cdn-val`, `leo-widget-cdn-prod` |
| **AcrPush** | Container registry `leoaicr` |

```bash
SP_OBJECT_ID=$(az ad sp show --id <CLIENT_ID> --query id -o tsv)

az role assignment create --assignee-object-id "$SP_OBJECT_ID" --assignee-principal-type ServicePrincipal \
  --role Contributor --scope /subscriptions/<SUB_ID>/resourceGroups/leo-widget-cdn-val
# Repeat for other RGs and AcrPush on leoaicr
```

**Storage Blob Data Contributor** on the widget account is granted by Bicep at deploy time -- you do not assign it manually.

### 4. Put the service principal object ID in bicepparam

```bash
az ad sp show --id <CLIENT_ID> --query id -o tsv
```

Set that value in `infra/widget-cdn/parameters/val.bicepparam`:

```bicep
param githubActionsPrincipalId = '<that-guid>'
```

Repeat per environment file (`dev`, `val`, `prod`) if you deploy each separately. The SP is usually the same across envs; only the storage account name changes.

### 5. Configure GitHub

Create environments: `dev`, `validation`, `production` (names must match federated credential subjects).

Secrets per environment:

| Secret | Value |
|--------|--------|
| `AZURE_CLIENT_ID` | App client ID |
| `AZURE_TENANT_ID` | Entra tenant ID |
| `AZURE_SUBSCRIPTION_ID` | Target subscription |
| `AZURE_WIDGET_STORAGE_ACCOUNT` | e.g. `leoaiwidgetcdnval` (after deploy) |
| `WIDGET_PUBLIC_HOST` | e.g. `leoaiwidgetcdnval.z33.web.core.windows.net` (after deploy) |

---

## If CI/CD OIDC already exists

You only need step 4:

```bash
az ad sp show --id <AZURE_CLIENT_ID from GitHub> --query id -o tsv
```

Update `githubActionsPrincipalId` in `infra/widget-cdn/parameters/val.bicepparam`, then run:

```powershell
.\infra\scripts\deploy-widget-cdn.ps1 -Environment val
```

---

## Order of operations for val

1. Set `githubActionsPrincipalId` in `infra/widget-cdn/parameters/val.bicepparam` (can be before or as part of Track F).
2. Run `deploy-widget-cdn.ps1` (creates storage + blob RBAC for the SP).
3. Set `AZURE_WIDGET_STORAGE_ACCOUNT` and `WIDGET_PUBLIC_HOST` in the GitHub **validation** environment (script prints these).
4. Run **Widget release** workflow with `environment=validation`.

If `githubActionsPrincipalId` is still `REPLACE-WITH-YOUR-SP-OBJECT-ID`, deploy still runs but `deploy-widget-cdn.ps1` warns you, and `widget-release.yml` will fail on blob upload until Bicep has assigned the correct principal.

After deploying the Widget CDN, populate the following Environment Secrets in the GitHub LEO-AI-CORE repository, under the Mizaic organisation.

|Secret|	Value|
|AZURE_CLIENT_ID|App client ID|
|AZURE_TENANT_ID|Entra tenant ID|
|AZURE_SUBSCRIPTION_ID|Target subscription|
|AZURE_WIDGET_STORAGE_ACCOUNT|e.g. leoaiwidgetcdnval (after deploy)|
|WIDGET_PUBLIC_HOST|e.g. leoaiwidgetcdnval.z33.web.core.windows.net (after deploy)|

