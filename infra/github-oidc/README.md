# GitHub Actions OIDC setup

GitHub Actions authenticates to Azure using Workload Identity Federation (OIDC).
No client secrets are stored in GitHub for Azure login.

## Prerequisites

- Entra ID app registration for CI/CD (Contributor on target RGs, AcrPush on `leoaicr`)
- GitHub repository admin access
- Azure CLI logged in (`az login`)

## Federated credential templates

Templates live at the repo root. **Greenfield installs:** edit the `subject`
field in each JSON file to match your GitHub org and repository before applying
(e.g. replace `Healthcare-Copilot/LEO-AI-CORE` with `YourOrg/YourRepo`).

| File | Subject | Workflow |
| ---- | ------- | -------- |
| `.federated-cred-main.json` | `repo:Miazic/LEO-AI-CORE:ref:refs/heads/main` | CI - Build and Push Images |
| `.federated-cred-env-dev.json` | `repo:Miazic/LEO-AI-CORE:environment:dev` | CD deploy-dev |
| `.federated-cred-env-validation.json` | `repo:Miazic/LEO-AI-CORE:environment:validation` | CD deploy-val |
| `.federated-cred-env-production.json` | `repo:Miazic/LEO-AI-CORE:environment:production` | CD deploy-prod |

## Apply credentials

Replace `{app-object-id}` with the Entra app registration **object ID** (not client ID):

```bash
APP_OBJECT_ID="{app-object-id}"

az ad app federated-credential create \
  --id "$APP_OBJECT_ID" \
  --parameters @.federated-cred-main.json

az ad app federated-credential create \
  --id "$APP_OBJECT_ID" \
  --parameters @.federated-cred-env-dev.json

az ad app federated-credential create \
  --id "$APP_OBJECT_ID" \
  --parameters @.federated-cred-env-validation.json

az ad app federated-credential create \
  --id "$APP_OBJECT_ID" \
  --parameters @.federated-cred-env-production.json
```

## GitHub Environments

Create three environments in the GitHub repo (Settings -> Environments):

| Environment name | CD job | Notes |
| ---------------- | ------ | ----- |
| `dev` | deploy-dev | Auto-deploys after CI on main |
| `validation` | deploy-val | Manual workflow_dispatch only |
| `production` | deploy-prod | Manual workflow_dispatch only |

Names must match exactly -- the federated credential `subject` includes the
environment name.

## GitHub secrets

Set on each environment (and `AZURE_CLIENT_ID` at repo level for CI test job):

| Secret | Value |
| ------ | ----- |
| `AZURE_CLIENT_ID` | App registration client ID |
| `AZURE_TENANT_ID` | Entra tenant ID |
| `AZURE_SUBSCRIPTION_ID` | Azure subscription ID |

Widget release workflow also needs (per environment):

| Secret | Value |
| ------ | ----- |
| `AZURE_WIDGET_STORAGE_ACCOUNT` | e.g. `leoaiwidgetcdndev` |
| `WIDGET_PUBLIC_HOST` | e.g. `leoaiwidgetcdndev.z33.web.core.windows.net` |

## Workflow permissions

All workflows require:

```yaml
permissions:
  id-token: write
  contents: read
```

CI uses `azure/login@v2` with `audience: api://AzureADTokenExchange`.
CD and widget-release omit the audience (Azure AD default applies).

See also: `compliance/policy/DC-DEP-001-deployment-configuration.md` Section 5.3.
