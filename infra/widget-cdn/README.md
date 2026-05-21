# LEO widget CDN -- Azure Storage origin

Atlas trace: DO-3B62F38E (DI-3C06AFD0).

This directory deploys the widget Static Website origin on Azure Storage.
The public widget URL is **NEVER hardcoded**; it lives in three places:

| Surface             | Where to set                                              |
| -----               | ----                                                      |
| Local dev / scripts | `secrets/.env.config` -> `WIDGET_PUBLIC_HOST`             |
| Azure infra         | `infra/widget-cdn/parameters/{env}.bicepparam` -> `widgetPublicHost` |
| GitHub Actions      | per-environment secret `WIDGET_PUBLIC_HOST`               |

The current per-environment values are:

| Env  | `WIDGET_PUBLIC_HOST`                                  | Edge |
| ---- | ----                                                  | ---- |
| dev  | `leoaiwidgetcdndev.z33.web.core.windows.net`        | Azure origin only (no custom domain) |
| val  | `widget.leo-ai-val.healthcarecopilot.ai`            | Optional Cloudflare custom domain |
| prod | `widget.leo-ai-audit.healthcarecopilot.ai`          | Optional Cloudflare custom domain |

If hosting moves, change the value in those three places only -- no
code change is needed.

## Topology

### Dev (direct Azure origin)

```
Embedding host page
        |
        |  <script src="https://leoaiwidgetcdndev.z33.web.core.windows.net/v1/leo-widget.js">
        v
Azure Storage Static Website
   leoaiwidgetcdndev.z33.web.core.windows.net
```

No Cloudflare DNS, Worker, or custom domain is required for dev.
Azure serves HTTPS on the storage web endpoint directly.

### Val / prod (optional Cloudflare custom domain)

When `WIDGET_PUBLIC_HOST` is a custom domain (not the storage web
hostname), the deploy workflow uses a Cloudflare Worker to fetch Azure
with the correct Host header. See section 3 below.

```
Embedding host page
        |
        |  <script src="https://${WIDGET_PUBLIC_HOST}/v1/leo-widget.js">
        v
Cloudflare Worker route on WIDGET_PUBLIC_HOST/*
        v
Azure Storage Static Website (leoaiwidgetcdn{env}.z33.web.core.windows.net)
```

## What lives at the origin

| Path                  | Mutability  | What it is                                 |
| -----                 | -----       | -----                                      |
| `/v1/leo-widget.js`   | immutable   | Web-component bundle (built from `services/widget-sdk`). |
| `/v1/manifest.json`   | mutable     | `{ major, active }` -- CSO controls active hash. |
| `/v1/advisory.json`   | mutable     | Active CSO safety advisory or empty body.   |
| `/iframe/index.html`  | per release | Hardened iframe entry document.            |
| `/iframe/shell.js`    | per release | Hardened iframe entry script.              |
| `/demo/index.html`    | per release | Integrator test card (synthetic SBAR, both variants). |

`/demo/` is the hosted end-to-end smoke page for integrators. It uses
stub data only (no live assessments). Append `?demo=1` to the iframe
shell URL for the iframe-only demo mode.

`/v1/leo-widget.js` is the only path the embedding host's
`<script src=...>` references. Cloudflare caches it for 1 year
(it is content-hashed implicitly by the immutability of the major
version line). Auto-update within a major works because the bundle
itself fetches `/v1/manifest.json` on load and switches if the
active hash changed (see `services/widget-sdk/src/release/loader.ts`).

CSO rollback is just "PUT a different `active` hash into
`/v1/manifest.json`". Cloudflare's edge TTL respects the origin's
`Cache-Control: public, max-age=60, must-revalidate`, so the
rollback propagates globally within 60 seconds.

## One-time setup (per environment)

### 1. Provision the Azure origin

```
az group create -n leo-widget-cdn-prod -l uksouth

az deployment group create \
  --resource-group leo-widget-cdn-prod \
  --template-file infra/widget-cdn/widget-cdn.bicep \
  --parameters infra/widget-cdn/parameters/prod.bicepparam
```

Then enable Static Website hosting (the bicep type does not yet
expose this flag):

```
az storage blob service-properties update \
  --account-name leoaiwidgetcdnprod \
  --static-website \
  --index-document index.html \
  --404-document   404.html
```

Note the `primaryEndpoints.web` URL it prints
(`https://leoaiwidgetcdn{env}.z33.web.core.windows.net/`). For dev,
set `WIDGET_PUBLIC_HOST` to that hostname (without `https://`).

### 2. Dev: set `WIDGET_PUBLIC_HOST` to the Azure origin

```
WIDGET_PUBLIC_HOST=leoaiwidgetcdndev.z33.web.core.windows.net
```

Verify:

```
curl -sI https://leoaiwidgetcdndev.z33.web.core.windows.net/v1/leo-widget.js
curl -sI https://leoaiwidgetcdndev.z33.web.core.windows.net/demo/
```

No Cloudflare setup is required. The widget-release workflow detects
`WIDGET_PUBLIC_HOST` matching the storage web hostname and skips all
Cloudflare steps automatically.

### 3. Val / prod only: optional Cloudflare custom domain

Skip this section for dev. Use it when `WIDGET_PUBLIC_HOST` is a
branded hostname under `healthcarecopilot.ai`.

#### 3a. Create the Cloudflare DNS record

In the Cloudflare zone that owns `WIDGET_PUBLIC_HOST` (for the
production value `widget.leo-ai-audit.healthcarecopilot.ai`, that
is the `healthcarecopilot.ai` zone), add a CNAME:

```
type:    CNAME
name:    widget.leo-ai-audit                # the leftmost labels of WIDGET_PUBLIC_HOST
target:  leoaiwidgetcdnprod.z6.web.core.windows.net
proxied: yes (orange cloud)
```

#### 3b. Deploy the Cloudflare Worker proxy (Free tier)

Origin Rules that rewrite the Host header require a paid Cloudflare plan.
On Free tier, use a **Cloudflare Worker** instead. The worker runs on
`WIDGET_PUBLIC_HOST/*`, fetches Azure Static Website with the correct
storage web endpoint Host header, and caches responses at the edge.

The deploy workflow applies this automatically via
`scripts/deploy_widget_cloudflare_worker.py`. Required API token
permissions:

- Account > Workers Scripts > Edit
- Zone > Workers Routes > Edit
- Zone > Cache Purge > Purge

Set `CLOUDFLARE_ACCOUNT_ID` in the GitHub environment secrets alongside
`CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ZONE_ID`.

Manual setup (dashboard):

1. Workers & Pages > Create > paste
   `infra/widget-cdn/cloudflare-worker/widget-proxy.js`
2. Settings > Variables > add plain-text `ORIGIN_HOST` =
   `leoaiwidgetcdndev.z33.web.core.windows.net` (your storage web host)
3. Triggers > Add route:
   `widget.leo-ai-audit.healthcarecopilot.ai/*` (your `WIDGET_PUBLIC_HOST`)

Or run locally:

```
export CLOUDFLARE_API_TOKEN=...
export CLOUDFLARE_ACCOUNT_ID=...
export CLOUDFLARE_ZONE_ID=...
export WIDGET_PUBLIC_HOST=widget.leo-ai-audit.healthcarecopilot.ai
export AZURE_WIDGET_ORIGIN_HOST=leoaiwidgetcdnprod.z33.web.core.windows.net
export WIDGET_ENVIRONMENT=prod
python scripts/deploy_widget_cloudflare_worker.py
```

Keep the DNS record from section 2 (proxied CNAME is fine). The worker
route handles traffic before Cloudflare would pull from Azure directly.

Cloudflare > SSL/TLS > Edge Certificates: ensure
`Always Use HTTPS` is on and Min TLS = 1.2. SSL mode = Full
(strict) is fine once the worker is in place.

Without the worker route, a proxied custom domain returns HTTP 400/403
even when the Azure origin serves the blobs correctly.

#### 3c. Apply cache rules (optional)

The complete set of cache rules lives in `cloudflare-cache-rules.json`
and is host-agnostic (rules match on `http.request.uri.path`, not on
host). Apply them once per zone that hosts a widget FQDN:

1. Open Cloudflare dashboard > the zone that owns `WIDGET_PUBLIC_HOST`
   > Rules > Cache Rules.
2. For each rule in `rules`, click `Create rule`, paste in the
   `description`, the `expression`, the `action_parameters`, save.

For automation:

```
curl -X PUT \
  -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
  -H "Content-Type: application/json" \
  "https://api.cloudflare.com/client/v4/zones/${CLOUDFLARE_ZONE_ID}/rulesets/phases/http_request_cache_settings/entrypoint" \
  -d @cloudflare-cache-rules.json
```

The four rules together implement:

- `/v1/leo-widget.js` and `/iframe/*`: cache 1 year edge, 1 day
  browser. Updates ride the major-version line via the manifest
  poll.
- `/v1/manifest.json` and `/v1/advisory.json`: respect origin
  `Cache-Control` (which `services/api/app/routers/sdk_release.py`
  sets to `public, max-age=60, must-revalidate`). 60s is the
  documented CSO rollback / advisory propagation window.
- Anything outside `/v1/` or `/iframe/` bypasses cache so a
  misconfigured origin never accidentally caches sensitive data.

### 4. Set the GitHub Actions secrets

Required for every environment:

```
AZURE_WIDGET_STORAGE_ACCOUNT = leoaiwidgetcdndev   # or val/prod account name
WIDGET_PUBLIC_HOST           = leoaiwidgetcdndev.z33.web.core.windows.net  # dev: storage web hostname
```

Optional (only when `WIDGET_PUBLIC_HOST` is a Cloudflare custom domain):

```
CLOUDFLARE_API_TOKEN         = <token: Workers Scripts Edit + Workers Routes Edit + Cache Purge>
CLOUDFLARE_ACCOUNT_ID        = <Cloudflare account id>
CLOUDFLARE_ZONE_ID           = <zone id of healthcarecopilot.ai>
```

`AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`
already exist (shared with `cd-deploy.yml`).

## Continuous deploy (CI to CDN)

The widget bundle ships from `.github/workflows/widget-release.yml`.
The deploy step is:

```
az storage blob upload-batch \
  --account-name $AZURE_WIDGET_STORAGE_ACCOUNT \
  --destination '$web' \
  --source services/widget-sdk/dist/v1 \
  --destination-path v1/ \
  --overwrite

az storage blob upload-batch \
  --account-name $AZURE_WIDGET_STORAGE_ACCOUNT \
  --destination '$web' \
  --source services/widget-sdk/dist/iframe \
  --destination-path iframe/ \
  --overwrite
```

After upload the workflow purges the immutable paths from
Cloudflare so the new bundle goes live immediately:

```
curl -X POST \
  -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
  -H "Content-Type: application/json" \
  "https://api.cloudflare.com/client/v4/zones/${CLOUDFLARE_ZONE_ID}/purge_cache" \
  -d "{ \"files\": [
        \"https://${WIDGET_PUBLIC_HOST}/v1/leo-widget.js\",
        \"https://${WIDGET_PUBLIC_HOST}/iframe/index.html\",
        \"https://${WIDGET_PUBLIC_HOST}/iframe/shell.js\"
      ] }"
```

`/v1/manifest.json` and `/v1/advisory.json` are NOT purged on
deploy: they are served from the LEO API
(`services/api/app/routers/sdk_release.py`) and, per the cache
rules, live on Cloudflare for at most 60 seconds.

## CSO rollback runbook

A patch ships, telemetry shows it broke a host. CSO needs the
previous `v1.4.2` build live everywhere within 5 minutes.

1. Identify the previous good build hash from `manifest.json`
   history (Storage account has versioning enabled; previous
   manifests are recoverable).
2. Update the manifest at the LEO API (the API serves
   `/v1/manifest.json` itself; an admin endpoint sets the active
   hash). The Cache-Control header on the response
   guarantees Cloudflare re-pulls within 60 seconds.
3. Confirm via `curl https://${WIDGET_PUBLIC_HOST}/v1/manifest.json`
   that the active hash flipped at the edge.
4. Confirm via the SDK telemetry stream that loaded events with
   the previous hash are flowing again.
5. If the bundle blob itself is corrupt (not just a bad active
   pointer), restore the previous blob via Storage account's
   blob-versioning rollback, then purge the immutable path.

## Moving hosting

If the org switches CDN, DNS, or Azure region:

1. Stand up the new origin / DNS / cache rules following sections 1-4.
2. Update `infra/widget-cdn/parameters/{env}.bicepparam` ->
   `widgetPublicHost` to the new FQDN.
3. Update the `WIDGET_PUBLIC_HOST` GitHub secret in each
   environment.
4. Update `secrets/.env.config` for local dev.
5. Re-run `widget-release.yml` to deploy to the new origin.
6. Cut over by repointing the old DNS record to the new origin.

No source code changes are required.

## Cost

This deployment is sub-pound per month. Bundle is ~30KB gzipped;
Static Website storage is fractions of a penny per GB-month;
egress goes via Cloudflare which is free for static assets in the
free / pro tier and is in-network for the pro/business tiers.

## Where the code lives

| Surface              | File                                                    |
| -----                | -----                                                   |
| Manifest endpoint    | `services/api/app/routers/sdk_release.py`               |
| Advisory endpoint    | `services/api/app/routers/sdk_release.py`               |
| Loader (widget)      | `services/widget-sdk/src/release/loader.ts`             |
| Advisory client      | `services/widget-sdk/src/release/advisory.ts`           |
| Pre-release gate     | `scripts/widget_release_gate.py`                        |
| CI build/deploy      | `.github/workflows/widget-release.yml`                  |
| Origin bicep         | `infra/widget-cdn/widget-cdn.bicep`                     |
| Bicep params (env)   | `infra/widget-cdn/parameters/{env}.bicepparam`          |
| Edge cache rules     | `infra/widget-cdn/cloudflare-cache-rules.json`          |
| Edge worker          | `infra/widget-cdn/cloudflare-worker/widget-proxy.js`    |
| Worker deploy script | `scripts/deploy_widget_cloudflare_worker.py`            |
| Local dev env var    | `secrets/.env.config` -> `WIDGET_PUBLIC_HOST`           |
