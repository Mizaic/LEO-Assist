# LEO widget CDN -- Cloudflare in front of Azure Storage

Atlas trace: DO-3B62F38E (DI-3C06AFD0).

This directory deploys the production-grade origin and explains the
edge configuration for the LEO widget CDN. The customer-facing FQDN
is **NEVER hardcoded**; it lives in three places only:

| Surface             | Where to set                                              |
| -----               | ----                                                      |
| Local dev / scripts | `secrets/.env.config` -> `WIDGET_PUBLIC_HOST`             |
| Azure infra         | `infra/widget-cdn/parameters/{env}.bicepparam` -> `widgetPublicHost` |
| GitHub Actions      | per-environment secret `WIDGET_PUBLIC_HOST`               |

The current per-environment values are:

| Env  | FQDN                                                |
| ---- | ----                                                |
| dev  | `widget.leo-ai-dev.healthcarecopilot.ai`            |
| val  | `widget.leo-ai-val.healthcarecopilot.ai`            |
| prod | `widget.leo-ai-audit.healthcarecopilot.ai`          |

If hosting moves (a different CDN, a different DNS host, a different
Azure region), change the value in those three places only -- no
code change is needed.

## Topology

```
Embedding host page
        |
        |  <script src="https://${WIDGET_PUBLIC_HOST}/v1/leo-widget.js">
        v
Cloudflare edge
   (zone: parent of WIDGET_PUBLIC_HOST,
    e.g. healthcarecopilot.ai)
        |  origin pull, HTTPS, Host header rewritten
        v
Azure Storage Static Website
   leoaiwidgetcdn{env}.z6.web.core.windows.net  (origin only, never
                                                  hit by browsers)
```

Cloudflare gives us global edge caching, DDoS protection, free TLS
on the customer hostname, and the rule engine that lets us split
TTL behaviour between the immutable bundle and the mutable
manifest/advisory. Azure Storage Static Website gives us the
smallest possible blast-radius origin: a public-read storage account
that holds zero PII by construction.

## What lives at the origin

| Path                  | Mutability  | What it is                                 |
| -----                 | -----       | -----                                      |
| `/v1/leo-widget.js`   | immutable   | Web-component bundle (built from `services/widget-sdk`). |
| `/v1/manifest.json`   | mutable     | `{ major, active }` -- CSO controls active hash. |
| `/v1/advisory.json`   | mutable     | Active CSO safety advisory or empty body.   |
| `/iframe/index.html`  | per release | Hardened iframe entry document.            |
| `/iframe/shell.js`    | per release | Hardened iframe entry script.              |

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
(`https://leoaiwidgetcdn{env}.z6.web.core.windows.net/`). That is
the **origin** Cloudflare will pull from.

### 2. Create the Cloudflare DNS record

In the Cloudflare zone that owns `WIDGET_PUBLIC_HOST` (for the
production value `widget.leo-ai-audit.healthcarecopilot.ai`, that
is the `healthcarecopilot.ai` zone), add a CNAME:

```
type:    CNAME
name:    widget.leo-ai-audit                # the leftmost labels of WIDGET_PUBLIC_HOST
target:  leoaiwidgetcdnprod.z6.web.core.windows.net
proxied: yes (orange cloud)
```

### 3. Configure the origin in Cloudflare

Cloudflare > SSL/TLS > Edge Certificates: ensure
`Always Use HTTPS` is on and Min TLS = 1.2. SSL mode = Full
(strict), because Storage Static Website serves a valid certificate.

### 4. Apply cache rules

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

### 5. Set the GitHub Actions secrets

For the deploy workflow (`.github/workflows/widget-release.yml`),
set per-environment secrets in the GitHub repo:

```
WIDGET_PUBLIC_HOST           = widget.leo-ai-audit.healthcarecopilot.ai
AZURE_WIDGET_STORAGE_ACCOUNT = leoaiwidgetcdnprod
CLOUDFLARE_API_TOKEN         = <token with Cache Purge: zone>
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
| Local dev env var    | `secrets/.env.config` -> `WIDGET_PUBLIC_HOST`           |
