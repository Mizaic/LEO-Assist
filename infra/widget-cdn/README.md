# LEO widget CDN -- Azure Storage Static Website

Atlas trace: DO-3B62F38E (DI-3C06AFD0).

This directory deploys the widget on **Azure Storage Static Website**.
The widget CDN does **not** use Cloudflare (no Worker, no edge cache
purge). Cloudflare may still front other Healthcare Copilot apps; that
is separate from this origin.

The public widget URL is **NEVER hardcoded** in application code; it
lives in three places:

| Surface             | Where to set                                              |
| -----               | ----                                                      |
| Local dev / scripts | `secrets/.env.config` -> `WIDGET_PUBLIC_HOST`             |
| Azure infra         | `infra/bicep/parameters/{env}.bicepparam` -> `widgetPublicHost` (auto-written by `deploy-widget-cdn.ps1`) |
| GitHub Actions      | per-environment secret `WIDGET_PUBLIC_HOST`               |

All three MUST be the Azure Static Website hostname from
`primaryEndpoints.web` (not a separate branded alias unless that alias
is configured as an Azure custom domain on the same storage account).

| Env  | Example `WIDGET_PUBLIC_HOST` (suffix varies per account) |
| ---- | ---- |
| dev  | `leoaiwidgetcdndev.z33.web.core.windows.net` |
| val  | `leoaiwidgetcdnval.z33.web.core.windows.net` |
| prod | `leoaiwidgetcdnprod.z33.web.core.windows.net` |

Resolve the live value after provisioning:

```
az storage account show -n leoaiwidgetcdn{env} \
  --query primaryEndpoints.web -o tsv
```

`widget-release.yml` fails if `WIDGET_PUBLIC_HOST` does not match that
hostname.

## Topology (dev, val, prod -- identical)

```
Embedding host page
        |
        |  <script src="https://${WIDGET_PUBLIC_HOST}/v1/leo-widget.js">
        v
Azure Storage Static Website (HTTPS, TLS 1.2+)
  leoaiwidgetcdn{env}.z33.web.core.windows.net
```

## Security controls (Azure)

| Control | Implementation |
| ---- | ---- |
| Isolated storage account | No patient-data blobs; widget assets only |
| HTTPS only | `supportsHttpsTrafficOnly: true` |
| TLS 1.2+ | `minimumTlsVersion: TLS1_2` |
| No shared keys | `allowSharedKeyAccess: false`; deploy via OIDC + RBAC |
| Blob versioning | 30-day soft delete + versioning for rollback |
| Minimal public surface | CI uploads only `/v1/`, `/iframe/`, `/demo/`, `404.html` |
| Unknown paths | Static website `404.html`; smoke test asserts 404 on `/index.html` |
| Cache headers | Immutable bundle (`max-age=31536000`); manifest/advisory `max-age=60` |

## What lives at the origin

| Path                  | Mutability  | What it is                                 |
| -----                 | -----       | -----                                      |
| `/v1/leo-widget.js`   | immutable   | Web-component bundle (built from `services/widget-sdk`). |
| `/v1/manifest.json`   | mutable     | `{ major, active }` -- CSO controls active hash. |
| `/v1/advisory.json`   | mutable     | Active CSO safety advisory or empty body.   |
| `/iframe/index.html`  | per release | Hardened iframe entry document.            |
| `/iframe/shell.js`    | per release | Hardened iframe entry script.              |
| `/demo/index.html`    | per release | Integrator test card (synthetic SBAR, both variants). |
| `/404.html`           | per release | Static website error document.             |

`/demo/` is the hosted end-to-end smoke page for integrators. It uses
stub data only (no live assessments). Append `?demo=1` to the iframe
shell URL for the iframe-only demo mode.

`/v1/leo-widget.js` is the only path the embedding host's
`<script src=...>` references. Auto-update within a major works
because the bundle fetches `/v1/manifest.json` on load (see
`services/widget-sdk/src/release/loader.ts`).

CSO rollback is "PUT a different `active` hash into `/v1/manifest.json`"
with `Cache-Control: public, max-age=60, must-revalidate`.

## One-time setup (per environment)

Run **before** `deploy.ps1` for the same environment. On greenfield, this
step populates `widgetPublicHost` and the widget CORS origin in
`infra/bicep/parameters/{env}.bicepparam`.

### 1. Provision the Azure origin

```powershell
.\infra\scripts\deploy-widget-cdn.ps1 -Environment dev
```

To re-sync hostname into bicepparam files after an account move:

```powershell
.\infra\scripts\sync-widget-cdn-params.ps1 -Environment dev
```

Equivalent CLI:

```
az group create -n leo-widget-cdn-dev -l uksouth

az deployment group create \
  --resource-group leo-widget-cdn-dev \
  --template-file infra/widget-cdn/widget-cdn.bicep \
  --parameters infra/widget-cdn/parameters/dev.bicepparam
```

Static website hosting and bicepparam sync are handled by
`deploy-widget-cdn.ps1` (`index.html` / `404.html`, RBAC auth).

Copy `WIDGET_PUBLIC_HOST` into GitHub secrets and `secrets/.env.config`.

### 2. Set GitHub Actions secrets

Required for every environment:

```
AZURE_WIDGET_STORAGE_ACCOUNT = leoaiwidgetcdndev
WIDGET_PUBLIC_HOST           = leoaiwidgetcdndev.z33.web.core.windows.net
```

`AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` already
exist (shared with `cd-deploy.yml`). Cloudflare secrets are **not**
used by `widget-release.yml`.

Verify:

```
curl -sI https://leoaiwidgetcdndev.z33.web.core.windows.net/v1/leo-widget.js
curl -sI https://leoaiwidgetcdndev.z33.web.core.windows.net/demo/
```

## Continuous deploy (CI to CDN)

The widget bundle ships from `.github/workflows/widget-release.yml`.
Uploads go to the `$web` container with explicit cache headers; the
workflow smoke-checks allowed paths and confirms unknown paths return
404.

Immutable bundle updates are visible immediately (no edge purge).
`manifest.json` / `advisory.json` honour `max-age=60` at the origin.

## CSO rollback runbook

1. Identify the previous good build hash from `manifest.json` history
   (blob versioning enabled).
2. Update the manifest (LEO API or blob upload) with the previous
   `active` hash.
3. Confirm via `curl https://${WIDGET_PUBLIC_HOST}/v1/manifest.json`.
4. If the bundle blob is corrupt, restore via blob versioning, then
   re-run `widget-release.yml`.

## Moving hosting

1. Stand up the new storage account / static website.
2. Run `sync-widget-cdn-params.ps1 -Environment {env}` (or redeploy via `deploy-widget-cdn.ps1`).
3. Update `WIDGET_PUBLIC_HOST` in GitHub and `secrets/.env.config`.
4. Re-run `widget-release.yml`.

## Legacy Cloudflare artefacts (not used for widget CDN)

These files are retained for reference only. Do not configure Workers
or cache rules for the widget origin unless product policy changes.

- `infra/widget-cdn/cloudflare-cache-rules.json`
- `infra/widget-cdn/cloudflare-worker/widget-proxy.js`
- `scripts/deploy_widget_cloudflare_worker.py`

## Where the code lives

| Surface              | File                                                    |
| -----                | -----                                                   |
| Manifest endpoint    | `services/api/app/routers/sdk_release.py`               |
| Advisory endpoint    | `services/api/app/routers/sdk_release.py`               |
| Loader (widget)      | `services/widget-sdk/src/release/loader.ts`             |
| Advisory client      | `services/widget-sdk/src/release/advisory.ts`           |
| Pre-release gate     | `scripts/widget_release_gate.py`                        |
| CI build/deploy      | `.github/workflows/widget-release.yml`                  |
| Deploy script        | `infra/scripts/deploy-widget-cdn.ps1`                   |
| Param sync script    | `infra/scripts/sync-widget-cdn-params.ps1`              |
| Origin bicep         | `infra/widget-cdn/widget-cdn.bicep`                     |
| Bicep params (env)   | `infra/widget-cdn/parameters/{env}.bicepparam`          |
| 404 document         | `infra/widget-cdn/static-website/404.html`              |
| Local dev env var    | `secrets/.env.config` -> `WIDGET_PUBLIC_HOST`           |
