# @mizaic/leo-widget

LEO-by-Mizaic embeddable SBAR surface. One source tree, two distribution
variants (Shadow-DOM web component and hardened iframe), shared trust
boundary semantics, locked LEO-by-Mizaic branding, mandatory telemetry,
QMS-controlled auto-update.

## Atlas trace

| Artefact   | dcId         | Notes                                              |
| -----      | ------       | ------                                             |
| User Need  | UN-64F0E9C3  | Embeddable AI surface across the Mizaic portfolio  |
| Design Inputs | DI-85C95E53, DI-A1206416, DI-85944331, DI-5F121122, DI-3C06AFD0, DI-2FBDAC7D | Distribution, auth, branding, telemetry, auto-update, governance |
| Risk       | R-4965BCD2   | AI handover summary used without clinician review  |
| Product    | PROD-LEO-CLINICAL-DECISION-SUPPORT-20260515-118182E4 | UKCA Class I, IEC 62304 Class B max          |

Look anything up via:

```
get_design_control(dc_type="design-input", dc_id="DI-85C95E53")
```

## Distribution

The same source tree under `src/` produces two artefacts:

- `dist/v1/leo-widget.js` - ES module, registers `<leo-sbar>` custom
  element with a closed Shadow DOM. NPM package `@mizaic/leo-widget`
  re-exports the same module.
- `dist/iframe/...` - hardened iframe variant served from the
  LEO-controlled CDN origin pinned by `WIDGET_PUBLIC_HOST` (see
  `infra/widget-cdn/README.md`). Per environment:
  - dev:  `https://leoaiwidgetcdndev.z33.web.core.windows.net`
  - val:  `https://leoaiwidgetcdnval.z33.web.core.windows.net`
  - prod: `https://leoaiwidgetcdnprod.z33.web.core.windows.net`

Build commands:

```
npm run build       # web-component / NPM bundle
npm run build:iframe
npm run build:all
```

## Host integration - web component variant

Replace `${WIDGET_PUBLIC_HOST}` with the FQDN for your environment
(see the table under "Distribution").

```html
<script type="module" src="https://${WIDGET_PUBLIC_HOST}/v1/leo-widget.js"></script>
<leo-sbar
  assessment-id="ass-2WW-001"
  widget-token="JWT_FROM_HOST_PROXY"
  proxy-origin="https://your-host-product.example.com">
</leo-sbar>
<script>
  document.querySelector("leo-sbar").addEventListener("leo:loaded", (e) => {
    console.log("LEO loaded", e.detail);
  });
</script>
```

## Host integration - hardened iframe variant

```html
<iframe
  title="LEO SBAR"
  src="https://${WIDGET_PUBLIC_HOST}/iframe/index.html?assessment-id=ass-2WW-001&widget-token=JWT_FROM_HOST_PROXY"
  sandbox="allow-scripts">
</iframe>
<script>
  window.addEventListener("message", (e) => {
    if (e.data && e.data.source === "leo-widget" && e.data.type === "leo:loaded") {
      console.log("LEO loaded", e.data.detail);
    }
  });
</script>
```

## Embed contract

| Parameter        | Web component attribute | Iframe URL param |
| ----             | ----                    | ----             |
| Assessment       | `assessment-id`         | `assessment-id`  |
| Widget token     | `widget-token`          | `widget-token`   |
| Proxy origin     | `proxy-origin`          | `proxy-origin`   |
| Safety advisory  | `advisory`              | `advisory`       |

Lifecycle events are identical. Web-component variant emits
`CustomEvent` on the element; iframe variant posts `{ source:
"leo-widget", type, detail }` to `window.parent`.

| Event                        | Detail shape                                     |
| ----                         | ----                                             |
| `leo:loaded`                 | `{ assessmentId }`                               |
| `leo:error`                  | `{ assessmentId, errorMessage }`                 |
| `leo:disclosure-opened`      | `{ assessmentId, stage }`                        |
| `leo:disclosure-closed`      | `{ assessmentId, stage }`                        |
| `leo:source-clicked`         | `{ assessmentId, stage, sourceId }`              |

## Testing

```
npm run test:no-coverage          # jest
npm run e2e                       # Playwright (boots demo server)
```

### CDN integrator demo (after deploy)

Each environment exposes a hosted test card with synthetic SBAR data only:

| Env  | URL |
| ---- | --- |
| dev  | `https://leoaiwidgetcdndev.z33.web.core.windows.net/demo/` |
| val  | `https://leoaiwidgetcdnval.z33.web.core.windows.net/demo/` |
| prod | `https://leoaiwidgetcdnprod.z33.web.core.windows.net/demo/` |

The page exercises both distribution variants (web component + iframe)
without a host proxy or live assessment data. Iframe-only demo mode:
`/iframe/index.html?demo=1&assessment-id=ass-2WW-demo&widget-token=demo-stub-token`.

Build locally:

```
npm run build:demo-cdn
```

The Playwright suite covers DI-85C95E53 acceptance criteria 2, 3, 4
against the demo host page (`demo/host-pages/dual-variant.html`),
which deliberately applies hostile host CSS and a hostile host JS
mutation script to verify the trust boundary holds.

## Slice status (MVP, 2026-04-20)

| DI            | Status   | DO           | VTs (4 each)                                       |
| ----          | ----     | ----         | ----                                               |
| DI-85C95E53   | shipped  | DO-B8D9FBC8  | VT-D7D81210, VT-A802FBA3, VT-50EE589C, VT-265DACC1 |
| DI-A1206416   | shipped  | DO-5C88CA8F  | VT-4081E44C, VT-D7751269, VT-7EF430DD, VT-8CADA244 |
| DI-85944331   | shipped  | DO-7F469209  | VT-011DF831, VT-623578BE, VT-AD41127B, VT-F6F5681E |
| DI-5F121122   | shipped  | DO-23DDE984  | VT-D6C11E1B, VT-1D9CF994, VT-5D887E30, VT-7FF54A1B |
| DI-3C06AFD0   | shipped  | DO-3B62F38E  | VT-0886D436, VT-14819B16, VT-0D241AA2, VT-FFFE45AD |
| DI-2FBDAC7D   | shipped  | DO-5A298ABC  | VT-E2AED8E8, VT-3D434ACC, VT-71530F5D, VT-1A2A16AD |

All 24 VTs are linked `VERIFIES` to their DI and `TESTS` to their DO,
and each carries a recorded `pass` run from a local execution. Run
`get_design_control(dc_type="design-input", dc_id=...)` to inspect
the chain in Atlas.

## Slice 3 - locked branding + reactive light/dark (DI-85944331)

`src/branding/tokens.ts` is the single source of truth for the LEO
brand: logo SVG, palette, typography, spacing, motion. Both `BRAND`
and `STAGE_THEME` are `Object.freeze`'d at runtime so a host that
manages to import the module still cannot mutate the palette.

`src/branding/stylesheet.ts` compiles a single CSS string used by
both variants. Reactive light/dark mode is implemented via a
`@media (prefers-color-scheme: dark)` block sourced from
`BRAND.dark` (no remount).

The custom element exposes ZERO public API for changing typography,
palette, or disclosure-trigger styling: `LeoSbarElement.observedAttributes`
is enumerated by `brand-lock.test.ts` and asserted to contain no
attribute matching `/color|font|typo|palette|disclosure|theme/i`.
The Playwright `brand-immutability.spec.ts` injects hostile host
CSS targeting widget-internal selectors and asserts that the
iframe-internal `.leo-mark`, `.leo-product`, and
`.leo-disclosure-toggle` retain the locked LEO styles.

## Slice 4 - mandatory disclosure-engagement telemetry (DI-5F121122)

`src/telemetry/sink.ts` exports `TelemetrySink`. The analytics URL
is captured into a non-writable property at construction; there is
no `setEndpoint`, `mute`, `disable`, or `optOut` method on the
prototype. Each event carries a per-instance `widget_instance_id`
and a monotonic `event_id` so the server-side dedup at
`POST /sdk/telemetry` can tolerate retries.

When `fetch` rejects, the sink keeps the event in a bounded
in-memory queue (max 200), retries with exponential backoff
(`1s -> 2s -> 4s -> 8s -> 30s`), fires `onDegraded(true)` so the
host can show a passive indicator, and never throws into the SBAR
render path. When the network recovers the queue drains and
`onDegraded(false)` fires.

Server side: `services/api/app/routers/sdk_telemetry.py` exposes
`POST /sdk/telemetry`. It deduplicates on
`(widget_instance_id, event_id)` and returns `200 status='deduped'`
when a duplicate arrives.

The dedup backend is multi-replica safe via Azure Managed Redis
(env `REDIS_URL`). Each new event is claimed atomically with
`SET key NX EX 86400`; any replica that arrives second gets `None`
back from Redis and reports `deduped`. When `REDIS_URL` is unset
(local dev / CI) or the Redis connection is transiently unhealthy,
the router falls back to a bounded in-process LRU
(`_LRU_CAPACITY = 50_000`) so a network blip never causes the API
to drop telemetry.

## Slice 5 - QMS auto-update + CSO rollback + advisory channel (DI-3C06AFD0)

`src/release/loader.ts` exposes `fetchActiveBuild({ manifestUrl,
pinnedMajor })`. It refuses to load any build whose major does not
match the host-pinned major, and refuses if the active hash itself
does not start with the pinned major. CSO rollback is achieved by
publishing a different `active` hash inside the same major; the
loader picks it up on the next poll.

`src/release/advisory.ts` exposes `AdvisoryClient`. It polls
`/v1/advisory.json` on init and every 60s. When `active=true` it
renders a `.leo-advisory` banner inside the supplied trust-boundary
container with `role="alert"` and `aria-live="polite"`. There is
no `hide`, `dismiss`, `disable`, or `suppress` method on the
prototype.

Server side: `services/api/app/routers/sdk_release.py` serves
`GET /v1/manifest.json` and `GET /v1/advisory.json` from the
Mizaic-controlled origin with `Cache-Control: public, max-age=60,
must-revalidate` (so a CSO rollback propagates within the
documented 5-minute window).

Pre-release gate: `scripts/widget_release_gate.py` reads a JSON
input describing each disclosure VT's status and refuses to print
`PROMOTE` (and exits non-zero) unless all four disclosure VTs
(`VT-AD41127B`, `VT-F6F5681E`, `VT-50EE589C`, `VT-265DACC1`) are
green. Wire this into the release pipeline as the last step before
upload to the CDN.

## Slice 6 - host governance acknowledgement (DI-2FBDAC7D)

A Mizaic-portfolio product cannot embed the LEO widget in
production until LEO holds all four mandatory artefacts on file:

1. SaaS Embedding Agreement
2. Data Processing Agreement
3. DCB0129 supplier safety case reference
4. IFU acknowledgement (with version)

The IFU itself lives at `compliance/policy/leo-widget-ifu.md`
(currently `v1.0.0`) and lists the host's mandatory obligations
(DCB0160 deployment safety case, CSP allowlist, telemetry
preservation, error surfacing, advisory response window).

The register is implemented in
`services/api/app/services/host_governance.py` and exposed via
`services/api/app/routers/sdk_governance.py`:

- `POST /sdk/governance/hosts` - register a host
- `POST /sdk/governance/hosts/{host_id}/artefacts` - record evidence
- `POST /sdk/governance/hosts/{host_id}/ifu` - record an IFU ack
- `GET  /sdk/governance/register` - full register for the quarterly
  Clinical Safety Committee review

The CRITICAL gate is at `services/api/app/routers/sdk_auth.py`:
`POST /sdk/auth/exchange` calls `host_governance.is_production_ready(
host_id)` and returns `403 detail='host_not_onboarded'` if the
host's record is incomplete. No widget token is minted for a host
that has not completed onboarding.

## Demo host examples

Two illustrative host integrations live under `host-examples/`:

- `host-examples/react-host/index.html` - mounts `<leo-sbar>` as a
  Shadow-DOM web component (the typical Next.js / React host case).
- `host-examples/iframe-host/index.html` - mounts the hardened
  iframe variant with `sandbox="allow-scripts"`.

Both pages run under the same `npm run demo` Vite server:

- `http://localhost:5173/host-examples/react-host/index.html`
- `http://localhost:5173/host-examples/iframe-host/index.html`
- `http://localhost:5173/demo/host-pages/dual-variant.html` -- the
  hostile-host fixture used by Playwright.

## Slice 2 - widget-token auth (DI-A1206416)

The widget never holds long-lived LEO credentials and never calls
the LEO API directly from the browser. The flow is:

1. Host product user signs in to the host product (the host
   product's existing auth - LEO has no opinion on it).
2. Host product backend calls `POST /sdk/auth/exchange` on the LEO
   API, presenting the shared `X-Mizaic-Host-Secret` header. The
   request body names the host user, tenant, assessment, and role.
   LEO returns a JWT scoped to that single assessment, audience
   `leo-widget`, TTL 900 seconds.
3. Host product backend hands the JWT to the host product front-end
   (one-shot, in-page, never persisted server-to-browser).
4. Host page mounts `<leo-sbar widget-token="..." proxy-origin="...">`
   (or the iframe equivalent).
5. The widget reads the JWT into a `WidgetTokenHolder` (in-memory
   only, no `localStorage` / `sessionStorage` / `document.cookie`),
   refuses any token whose `aud` is not `leo-widget` or whose
   remaining TTL exceeds 900s.
6. The widget calls `GET <proxy-origin>/sdk/sbar/<assessment-id>`
   with the bearer token. The fetcher refuses any URL whose origin
   is not in the configured proxy-origin allowlist.
7. The LEO API verifies the JWT and returns 403 if the token's
   `assessment_id` claim does not match the path.

Server-side artefacts:

- `libs/sdk_auth/widget_token.py` - mint + verify (HS256, aud
  `leo-widget`, hard 900s ceiling).
- `services/api/app/routers/sdk_auth.py` - the two endpoints.
- Required env vars: `SDK_HOST_SHARED_SECRET`,
  `SDK_WIDGET_TOKEN_SECRET`. The exchange endpoint also rejects
  any request that includes a browser `Origin` header (browsers
  always send it on POST; server-to-server callers do not).

Widget-side artefacts:

- `services/widget-sdk/src/auth/widget_token.ts` - in-memory
  `WidgetTokenHolder`, parses the JWT payload (signature is the
  server's job) and applies the aud / TTL guard.
- `services/widget-sdk/src/data/fetcher.ts` - origin allowlist
  guard before any `fetch()` call.

## Reuse note

Per the build brief, the SDK should reuse the in-app SBAR rendering
components from `services/ui/src/components/sbar-final/SbarFinalView`.
That component currently depends on Next.js path aliases, MUI,
Emotion, and a Tiptap-based MarkdownEditor. Pulling that stack into a
Class B medical-device widget bundle that ships into third-party
hosts is a supply-chain decision that warrants a separate DI / Risk
review.

For slice 1 the SDK reuses the **data contract** (`SbarSection`,
`SbarBackgroundPart`, `SbarStageName`, `STAGE_THEME` semantics) and
re-implements the renderer in vanilla TypeScript inside the trust
boundary. The SDK and `services/ui` therefore agree on the wire
shape but diverge on visual presentation. A future DO will hoist
`SbarFinalView` and `MarkdownEditor` into `@leo/design-system`,
after which the SDK can import the same React component the in-app
view uses. Tracking that follow-up as part of the DO record under
DI-85C95E53.
