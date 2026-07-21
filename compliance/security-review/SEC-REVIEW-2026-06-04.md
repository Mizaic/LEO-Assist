# SEC-REVIEW-2026-06-04 -- Security and Privacy Standards Review of LEO-AI-CORE

| Field | Value |
|---|---|
| Document ID | SEC-REVIEW-2026-06-04 |
| Status | Draft -- advisory; all findings require human owner acceptance |
| Date | 2026-06-04 |
| Reviewer | Security and Privacy Review (agent-assisted, evidence-led) |
| Product | LEO-AI-CORE (PROD-LEO-CLINICAL-DECISION-SUPPORT-20260515-118182E4), IEC 62304 Class B CDS |
| Scope | services/api, services/ui, libs/*, infra config; compliance/policy/* baseline |
| Method | Static code review with file:line evidence. No live patient data accessed. No application code changed. |

> This is a REVIEW. No application source was modified. Every finding below is
> advisory until a named owner accepts it. Where a claim could not be confirmed
> from code alone, it is marked "could not verify" (see Section 5).

---

## 1. Executive summary

LEO-AI-CORE has a deliberate, reasonably mature security baseline for a
pre-production clinical decision support product: server-side OAuth with
cryptographic JWT verification, a Redis-backed session model with HttpOnly
Secure cookies, a multi-tenant allowlist, an XHR-based CSRF guard, parameterised
Neo4j queries, a prompt-injection guard for the LLM boundary, and a documented
de-identification path for cloned test data. Secrets are mapped to Azure Key
Vault rather than committed to the repo.

The platform is, however, **not yet ready to pass NHS DTAC v2 (mandatory from
6 April 2026) or to submit the NHS DSPT v8 (deadline 30 June 2026)**. The
governing compliance documents (DTAC statement, penetration-test summary,
Cyber Essentials, DSPT) are all drafts with unfilled placeholders, and **no
penetration test has been performed**. On the code side, the most material
issue is an architectural authorization gap: the Next.js proxy attaches the
internal service secret to terminology and worker API calls **without first
checking that the browser request belongs to an authenticated user**, so the
knowledge-graph write endpoints can be reached by an unauthenticated caller who
can reach the UI host. Secondary issues include multi-factor authentication
being off by default and failing open, application-layer rate limiting being
configured but never applied (including on the login endpoints), special-
category clinical text fragments being written to application logs, and patient-
record access not being security-audit-logged.

**Plain-English implication for patients:** today, the system protects the
clinical record reasonably well at the front door, but two doors are weaker than
they should be. One internal "staff pass" door can be pushed open without
signing in (it lets someone change the clinical word-list the tool uses, not the
patient record itself). And the extra "second check" at sign-in (a code as well
as a password) is switched off by default. Neither has been shown to have been
misused, and a qualified person still reviews every AI suggestion before it
reaches a patient record. These should be fixed before the product is used with
real NHS data.

**Overall risk rating: MEDIUM-HIGH (pre-production).** No Critical
unauthenticated patient-data exposure was found. The rating is driven by one
High access-control finding, several Medium auth/logging findings, and the fact
that the mandatory NHS assurance evidence (DTAC v2, DSPT v8, pen test, Cyber
Essentials) is incomplete. The rating should not drop below Medium until the
DTAC/DSPT evidence is completed and an independent penetration test is passed.

---

## 2. Standards coverage

Status key: Met / Partial / Not met / N/A. "Partial" means controls exist but
have material gaps or unverified evidence.

| Standard (version) | Status | Key gaps | Evidence |
|---|---|---|---|
| NHS DTAC v2 (mandatory 6 Apr 2026) | Partial | DTAC statement is a draft with placeholders across all 5 domains; DCB0129 declaration pending; no pen test; Cyber Essentials pending | `compliance/policy/DC-DTAC-001-dtac-compliance-statement.md:33-37,108-125,168-180` |
| DSIT/NCSC Software Security Code of Practice | Partial | C3 of DTAC v2 now requires explicit conformance; not evidenced in repo; secure-by-default gaps (MFA off, rate limit unapplied) | `services/api/app/routers/auth.py:399-413`; `services/api/app/main.py:43-46,344-345` |
| NHS DSPT v8 (deadline 30 Jun 2026) | Not met | Not submitted; MFA evidence item (CE+ no longer equivalent) not satisfied -- MFA off by default and fail-open; access audit incomplete | `DC-DTAC-001:83-90`; `auth.py:215-235,399-413`; `libs/audit/security_log.py:269-296` |
| OWASP ASVS 5.0.0 (target L2, L3 where warranted) | Partial | Gaps in V6 (MFA), V7 (server-side idle/absolute TTL), V8 (proxy authz bypass), V10 (OIDC nonce binding), V16 (data.access logging, PHI in logs) | see Section 3 findings |
| OWASP Top 10 (pen-test baseline) | Partial | A01 Broken Access Control (F1, F6), A09 Logging/Monitoring (F5, F7), A05 Misconfig (F4, F10); no annual pen test executed | `DC-PT-001-penetration-testing-summary.md:42-52` |
| UK GDPR + DPA 2018 (Art 25, 35, RoPA, minimisation, transfers) | Partial | DPIA in draft awaiting DPO sign-off; special-category text logged (Art 5(1)(c) minimisation); LLM transfer relies on DPA/TRA | `DC-DTAC-001:84`; `libs/llm_client/prompt_safety.py:107-111`; `compliance/policy/DC-TRA-001-transfer-risk-assessment.md` |
| NHS National Data Opt-Out (DC-NDOO-001) | Could not verify | NDOO applicability and enforcement not assessed against code in this pass | `compliance/policy/DC-NDOO-001-national-data-opt-out.md` |
| Cyber Essentials / CE Plus (DTAC floor) | Not met | Pending certification; roadmap target 2026-09-30 | `DC-PT-001:111-133`; `DC-DTAC-001:116-125` |

---

## 3. Findings

Severity reflects exploitability and impact in a pre-production clinical
context. CVSS-style notes are indicative, not formally scored.

### F1 (HIGH) -- Next.js proxy attaches the internal service secret without verifying the user session

- **Severity:** High. CVSS-style: AV:N/AC:L/PR:N/UI:N/S:C/C:L/I:H/A:L (network,
  no privilege, integrity impact to the clinical knowledge base).
- **Standards:** OWASP A01 Broken Access Control; ASVS V8.* (Authorization),
  V13 (Configuration); DTAC C3 Technical Security.
- **Evidence:**
  - The Next proxy injects `SERVICE_AUTH_SECRET` as a Bearer token for
    service-auth routes with no session/identity check:
    `services/ui/src/proxy.ts:166-180` (`serviceAuthRewrite`),
    `services/ui/src/proxy.ts:183` (`termApiRewrite = serviceAuthRewrite`),
    `services/ui/src/proxy.ts:220-227` (all `/api/terminology/` and
    `serviceAuth` rules use it).
  - The proxy entry point performs no authentication; it only rewrites:
    `services/ui/src/proxy.ts:185-231`.
  - Upstream terminology mutations trust the service token alone:
    `services/terminology_api/app/routers/valueset.py:53-61`,
    `conceptmap.py:57-66`, `writeback.py:41`, `surface_forms.py:115-260`,
    `guidelines.py:229-426` (all `Depends(verify_service_token)` only).
  - The token check accepts any caller presenting the shared secret:
    `libs/auth/service_auth.py:37-60`.
- **Impact:** An unauthenticated caller who can reach the UI origin can drive
  writes to the knowledge graph (ValueSet/ConceptMap/terminology writeback,
  guideline compile) and reach `serviceAuth` worker routes
  (`/api/training-worker/`, `/api/pipeline/test-run`). This is an integrity and
  patient-safety concern: the SNOMED/terminology layer feeds clinical coding
  proposals. It is not a direct patient-data (PHI) breach, because the
  terminology graph is not the patient record. Surface-form mutations are
  already re-routed through core-api session auth
  (`services/ui/src/proxy.ts:205-213`), which shows the safe pattern; the other
  terminology mutations are not.
- **Remediation:** Enforce an authenticated, role-checked session in the Next
  proxy (or at the edge, e.g. Cloudflare Access) before any `serviceAuth`
  rewrite, OR add a session/role dependency on the terminology/worker mutating
  endpoints in addition to `verify_service_token`. Prefer defence-in-depth:
  both. Mirror the surface-forms re-route through core-api for the remaining
  terminology writes.
- **Suggested owner:** Technical Lead (backend) with CISO sign-off.

### F2 (MEDIUM-HIGH) -- MFA is disabled by default and fails open

- **Severity:** Medium-High. Authentication strength control absent by default.
- **Standards:** ASVS V6.5 (MFA); DSPT v8 item 4.5.3 (per brief: CE Plus no
  longer equivalent for MFA); DTAC v2 C3 (MFA expanded to admin/remote access).
- **Evidence:**
  - Default `require_mfa=False` and a Neo4j-unreachable fallback that also sets
    `require_mfa=False`: `services/api/app/routers/auth.py:215-235`.
  - MFA is only enforced when `require_mfa` is true, by inspecting the `amr`
    claim: `services/api/app/routers/auth.py:399-413`. If config read fails, the
    backstop is skipped.
- **Impact:** If Conditional Access is not configured in Entra and the Neo4j
  config row is missing or unreachable, password-only logins are accepted. DSPT
  v8 specifically removed CE Plus equivalence for the MFA evidence item, so this
  must be demonstrably on.
- **Remediation:** Fail closed on MFA: default `require_mfa=True`, and on config
  read failure require MFA rather than skipping. Document the Entra Conditional
  Access policy as the primary control and keep the `amr` check as the backstop.
- **Suggested owner:** IT Admin / Identity owner + DPO.

### F3 (MEDIUM) -- OIDC nonce and state are not bound to the session

- **Severity:** Medium. Login CSRF / authorization-code replay exposure.
- **Standards:** ASVS V10.* (OAuth/OIDC), V6.8.4 (verify IdP-returned claims).
- **Evidence:**
  - `/login` sets a random `leo_oauth_nonce` cookie and sends a `nonce` to
    Entra: `services/api/app/routers/auth.py:255-281`.
  - `/callback` only checks that the cookie is **present**; it never compares it
    to the `nonce` claim in the verified `id_token`, and `state` is used as the
    post-login redirect path rather than a CSRF token bound to the session:
    `services/api/app/routers/auth.py:301-307,343-343,470-473`.
- **Impact:** The nonce/state pair does not prevent an attacker-supplied
  authorization code from being redeemed in a victim's browser context (login
  CSRF / session fixation class). The presence-only check is weaker than a
  value match.
- **Remediation:** Compare the `id_token` `nonce` claim to the cookie value and
  reject on mismatch; bind `state` to a server-stored, single-use value and
  validate it. Keep `state`-as-redirect separate from the CSRF token.
- **Suggested owner:** Technical Lead (auth).

### F4 (MEDIUM) -- Application-layer rate limiting is configured but never applied

- **Severity:** Medium. Brute-force / resource-exhaustion exposure on auth and
  all APIs.
- **Standards:** ASVS V6.2 (anti-automation on auth), V11 business logic;
  OWASP A07; DTAC C3.
- **Evidence:**
  - `slowapi` limiter and handler are registered:
    `services/api/app/main.py:43-46,344-345`.
  - No `@limiter.limit`/decorator or `SlowAPIMiddleware` is applied to any
    router; `/auth/login` and `/auth/callback` have no limit:
    `services/api/app/routers/auth.py:247,285` (no decorator).
- **Impact:** The default limit object exists but does not throttle requests
  because limits are not attached. Login and token endpoints are unthrottled at
  the application layer. The deployment doc expects Cloudflare rules, which
  cannot be verified from code.
- **Remediation:** Apply explicit limits to auth endpoints (e.g. 5-10/min/IP)
  and a sane default to mutating routes, or add `SlowAPIMiddleware`. Document and
  verify the edge WAF rules as the primary control.
- **Suggested owner:** Technical Lead + Platform/Infra.

### F5 (MEDIUM) -- Special-category clinical text fragments are written to application logs

- **Severity:** Medium. UK GDPR Art 5(1)(c) minimisation; special-category data
  in logs.
- **Standards:** UK GDPR Art 5/9; ASVS V16 (do not log sensitive data); DTAC C2.
- **Evidence:**
  - First 80 chars of raw clinical text logged on injection match:
    `libs/llm_client/prompt_safety.py:107-111`.
  - Entity text logged at INFO/WARNING via `%r`:
    `libs/llm_client/disorder_verifier.py:198-204` (and :187-191),
    `libs/llm_client/escalation.py:183-186,338-340,607-608`.
  - Entity text at DEBUG: `services/api/app/services/label_verifier.py:788-790`.
- **Impact:** Clinical phrases (potentially identifying in free text) flow into
  standard application logs, which typically have longer retention and broader
  access than the patient store. Increases breach blast radius.
- **Remediation:** Log lengths, hashes, or entity IDs instead of raw text;
  redact before logging; gate any raw-text logging behind an explicit
  non-production debug flag. Confirm log retention and access controls in the
  RoPA.
- **Suggested owner:** Backend leads (LLM client) + DPO.

### F6 (MEDIUM) -- Dataset export uses legacy header-based scope with a dev-bypass and no role gate

- **Severity:** Medium. Patient-derived data egress with weak authorization.
- **Standards:** OWASP A01; ASVS V8; UK GDPR Art 25/5 (minimisation, access
  control on exports).
- **Evidence:**
  - Export router depends on the legacy `get_caller_scope` (X-Leo-Session
    header), not the session-cookie dependency the project rule mandates, and
    applies no admin/role check on dataset export:
    `services/api/app/routers/exports.py:21,32-57`.
  - `get_caller_scope` contains an env-flag bypass returning unrestricted admin:
    `libs/auth/org_scope.py:395-423` (`LEO_LOCAL_DEV_BYPASS`).
- **Impact:** Dataset/MedSpaCy training exports (derived from patient data) are
  available to any caller the legacy dependency authenticates, with no role
  restriction, and an environment-flag bypass could elevate an anonymous caller
  to admin if ever set in a deployed environment.
- **Remediation:** Switch exports to `app.deps.require_admin` (session cookie),
  add explicit role and org-scoping, and ensure `LEO_LOCAL_DEV_BYPASS` can never
  be set outside local (assert on startup in non-local environments).
- **Suggested owner:** Backend lead + DPO.

### F7 (MEDIUM) -- Patient-record access and authorization denials are not security-audit-logged

- **Severity:** Medium. Detection/forensics gap; also a DSPT/DTAC requirement.
- **Standards:** ASVS V16; DTAC C2/C3; DSPT (access audit); UK GDPR Art 5(2)
  accountability.
- **Evidence:**
  - Auth events are wired (`libs/audit/security_log.py:63-89`, called from
    `auth.py`), but `data.access`, `data.modification`, `authz.denied`, and
    `authz.admin_action` are defined and never called from application code:
    `libs/audit/security_log.py:242-296`.
  - `require_admin` raises 403 without emitting `authz.denied`:
    `services/api/app/deps.py:101-107`.
  - Acknowledged as open in the threat model (TM-LOG-001, TM-AUTH-001):
    `compliance/policy/DC-PT-001-penetration-testing-summary.md:84-87`.
- **Impact:** No tamper-evident trail of who read or changed which patient
  record, and no record of access-control denials. Limits breach investigation
  and is a likely DSPT/DTAC finding.
- **Remediation:** Emit `data.access` on patient-record reads/exports,
  `authz.denied` in the admin/scope dependencies, and `authz.admin_action` on
  admin mutations. Forward `security.audit` to immutable storage.
- **Suggested owner:** Backend lead + DPO/IG.

### F8 (MEDIUM) -- Token verification uses python-jose (known CVEs) and the dependency is mis-recorded in the SOUP list

- **Severity:** Medium. Supply-chain / SOUP-control gap.
- **Standards:** IEC 62304 8.1.2 (SOUP); DTAC C3; OWASP A06; ASVS V9 (tokens).
- **Evidence:**
  - `auth.py` verifies the ID token with python-jose:
    `services/api/app/routers/auth.py:23` (`from jose import jwt, JWTError`).
  - Dependency floor allows known-vulnerable releases:
    `requirements.txt:55` (`python-jose[cryptography]>=3.3`). python-jose 3.3.0
    is affected by CVE-2024-33663 (algorithm confusion) and CVE-2024-33664 (JWE
    DoS).
  - The SOUP list records PyJWT, not python-jose, for JWT handling:
    `compliance/policy/DC-SOUP-001-soup-list.md:59` -- the actual auth-boundary
    library is undocumented.
- **Impact:** A safety-relevant auth-boundary library is not under SOUP control
  and its version floor permits vulnerable builds. Algorithm-confusion risk is
  partially mitigated because decode restricts `algorithms=["RS256"]`
  (`auth.py:194`), but this should not be the only control.
- **Remediation:** Pin python-jose to a fixed, patched version (>=3.4.0), add it
  to the SOUP list with risk class and monitoring, and add a CVE scan (pip-audit)
  to CI. Consider standardising on a single JWT library.
- **Suggested owner:** Engineering / Quality Manager (SOUP owner).

### F9 (MEDIUM) -- Idle timeout is advisory only; sessions have a long absolute TTL

- **Severity:** Medium. Session lifetime control weaker than stated.
- **Standards:** ASVS V7.* (session timeout/idle); DTAC C3.
- **Evidence:**
  - Default session TTL is 7 days (168h), set as an absolute Redis TTL:
    `services/api/app/services/session_store.py:70-71`.
  - `idle_timeout_minutes` is stored and returned to the frontend but there is no
    server-side sliding idle enforcement; the value is advisory to the UI:
    `services/api/app/routers/auth.py:215-235,565` and
    `services/ui/src/lib/serverSession.ts:62`.
- **Impact:** A stolen session cookie remains valid for up to the absolute TTL
  regardless of inactivity, because idle expiry is not enforced server-side.
- **Remediation:** Enforce idle timeout server-side (e.g. store last-activity and
  reject/rotate after the idle window), shorten the default absolute TTL for
  clinical roles, and rotate the session id on privilege change.
- **Suggested owner:** Technical Lead (auth).

### F10 (LOW-MEDIUM) -- FHIR API CORS defaults to wildcard with credentials; secondary services lack security headers

- **Severity:** Low-Medium. Misconfiguration; depends on whether FHIR API is
  internet-facing.
- **Standards:** ASVS V3/V13; OWASP A05.
- **Evidence:**
  - FHIR API CORS falls back to `["*"]` with `allow_credentials=True`:
    `services/fhir_api/app/main.py:97-106`.
  - Security headers (CSP/HSTS/etc.) are only set on core-api
    (`services/api/app/main.py:410-427`); terminology/analytics/fhir/training-
    worker apps do not set them.
- **Impact:** A wildcard credentialed CORS policy is unsafe if the FHIR API is
  reachable cross-origin; missing headers reduce defence-in-depth on secondary
  services.
- **Remediation:** Remove the `*` fallback (fail closed to an explicit
  allowlist), and apply the core-api security-header middleware to all services.
- **Suggested owner:** Backend leads per service.

### F11 (LOW) -- No security headers emitted by the Next.js application

- **Severity:** Low (assuming edge/Cloudflare adds them; unverified).
- **Standards:** ASVS V3 (Web Frontend Security); DTAC C3.
- **Evidence:** No `headers()` config or CSP/HSTS in `services/ui/next.config.mjs`
  or UI middleware; the deployment doc expects Cloudflare to add them
  (`compliance/policy/DC-DEP-001-deployment-configuration.md:116-124`).
- **Impact:** If the edge is misconfigured, the browser app ships without CSP,
  HSTS, or frame protections.
- **Remediation:** Add a `headers()` config (CSP, HSTS, X-Frame-Options,
  X-Content-Type-Options, Referrer-Policy) in the Next app as defence-in-depth;
  do not rely solely on the edge.
- **Suggested owner:** Frontend lead + Platform.

### F12 (LOW) -- Verbose OAuth token-exchange error logging

- **Severity:** Low. Potential sensitive detail in logs.
- **Standards:** ASVS V16; UK GDPR minimisation.
- **Evidence:** On token-exchange failure the upstream response body is logged
  (`r.text[:200]`): `services/api/app/routers/auth.py:325`.
- **Impact:** Entra error bodies may include correlation/context data; low risk
  but unnecessary.
- **Remediation:** Log status code and a correlation id only; drop the body.
- **Suggested owner:** Technical Lead (auth).

### F13 (LOW/INFO) -- E2E auth-bypass payload grants platform admin, guarded only by env vars

- **Severity:** Low/Info. No production impact if NODE_ENV is correct.
- **Standards:** ASVS V13 (config separation); OWASP A05.
- **Evidence:** `E2E_SESSION_PAYLOAD` returns `isPlatformAdmin: true` and is
  activated by `isE2eAuthMode()` which requires `NODE_ENV !== "production"` and
  `NEXT_PUBLIC_E2E_MODE === "true"`: `services/ui/src/lib/e2eSession.ts:1-28`.
  It only fakes the UI session shape; backend endpoints still require a real
  session cookie.
- **Impact:** A single misconfigured environment variable would surface a fake
  admin UI session. Backend authz is unaffected.
- **Remediation:** Add a startup assertion that E2E mode can never be enabled in
  production, and keep `NEXT_PUBLIC_E2E_MODE` out of all deployed env files.
- **Suggested owner:** Frontend lead + Platform.

### F14 (INFO) -- ID token issuer not validated (by design)

- **Severity:** Info. Compensating controls present.
- **Standards:** ASVS V10.4.
- **Evidence:** `verify_iss=False` in decode options:
  `services/api/app/routers/auth.py:189`. Mitigated by RS256 signature
  verification against the common JWKS, audience check, v1 issuer rejection,
  and the `tid` tenant allowlist: `auth.py:161-212,354-377`.
- **Recommendation:** Acceptable for multi-tenant Entra. Document the rationale
  in the threat model so reviewers do not flag it as a defect.

### F15 (INFO) -- Core-api CORS uses wildcard methods/headers

- **Severity:** Info. Origins are an explicit allowlist; only methods/headers are
  `*`.
- **Evidence:** `services/api/app/main.py:351-363`.
- **Recommendation:** Constrain `allow_methods`/`allow_headers` to the set
  actually used; low priority since origins are restricted.

### F16 (LOW) -- Dev Neo4j credentials in docker-compose

- **Severity:** Low (dev only; loopback-bound).
- **Evidence:** `docker-compose.yml:15-16,73-78` (e.g. `neo4j/patient-dev`),
  ports bound to loopback. Production secrets come from Key Vault
  (`libs/keyvault/loader.py:44-87`).
- **Recommendation:** Keep as-is for local dev but add a startup guard that
  refuses known dev passwords when `ENVIRONMENT != local`.
- **Suggested owner:** Platform.

### F17 (MEDIUM, governance) -- Mandatory NHS assurance evidence is incomplete

- **Severity:** Medium (procurement/compliance blocker, not a code defect).
- **Standards:** DTAC v2 (all domains); DSPT v8; pen test; Cyber Essentials.
- **Evidence:** Draft status and placeholders throughout
  `compliance/policy/DC-DTAC-001-dtac-compliance-statement.md:6-8,33-37,168-180`;
  no pen test executed `DC-PT-001-penetration-testing-summary.md:42-52`; DSPT not
  submitted `DC-DTAC-001:83-90`.
- **Remediation:** Complete the DTAC v2 form (new Feb-2026 version), submit DSPT
  v8 before 30 Jun 2026, execute the CREST pen test, and obtain Cyber Essentials.
- **Suggested owner:** DPO + Clinical Safety Officer + Engineering.

---

## 4. Prioritised remediation backlog (atomic tasks)

Each task is sized ~1-4h and has acceptance criteria. Tasks are independent
unless noted. They do not change behaviour beyond the stated fix.

### Sprint 1 -- access control and authentication (highest priority)

**T1 (F1) -- Gate terminology/worker mutations behind user auth.**
- Acceptance: Mutating terminology endpoints (ValueSet/ConceptMap/writeback/
  guidelines) and `serviceAuth` worker routes reject requests that lack a valid
  authenticated session/role, even when the service secret is present. A test
  proves an unauthenticated request through the Next proxy returns 401/403.
- Notes: Prefer re-routing remaining terminology writes through core-api session
  auth (mirror `proxy.ts:205-213`) and/or add a session dependency upstream.

**T2 (F2) -- Make MFA fail closed.**
- Acceptance: Default `require_mfa=True`; on config-read failure the login path
  requires MFA (does not skip). Unit test covers the Neo4j-unreachable branch
  and asserts a password-only login is rejected.

**T3 (F3) -- Validate OIDC nonce and bind state.**
- Acceptance: `/callback` compares the `id_token` `nonce` claim to the cookie
  and rejects mismatches; `state` CSRF value is server-stored and single-use.
  Tests cover mismatch and replay.

**T4 (F6) -- Harden dataset export authz.**
- Acceptance: `exports.py` uses `require_admin` (session cookie), enforces role
  and org-scoping, and a startup assertion forbids `LEO_LOCAL_DEV_BYPASS`
  outside local. Test proves a non-admin is denied.

### Sprint 2 -- logging, monitoring, session

**T5 (F5) -- Stop logging raw clinical text.**
- Acceptance: `prompt_safety.py`, `disorder_verifier.py`, `escalation.py`,
  `label_verifier.py` log lengths/hashes/IDs, not raw entity/clinical text;
  raw-text logging is behind a non-production debug flag. Grep test asserts no
  `%r` of clinical text at INFO/WARNING.

**T6 (F7) -- Wire data-access and authz audit events.**
- Acceptance: `data.access` emitted on patient-record reads/exports;
  `authz.denied` emitted in admin/scope dependencies; `authz.admin_action` on
  admin mutations. Tests assert emission.

**T7 (F4) -- Apply rate limits to auth and mutating routes.**
- Acceptance: `/auth/login` and `/auth/callback` carry an explicit per-IP limit;
  a default limit applies to mutations. Test asserts a 429 after threshold.

**T8 (F9) -- Enforce server-side idle timeout.**
- Acceptance: Sessions store last-activity; requests after the idle window are
  rejected/rotated; default absolute TTL reduced for clinical roles. Test covers
  idle expiry.

### Sprint 3 -- supply chain, config, headers

**T9 (F8) -- Pin and document python-jose; add CVE scan.**
- Acceptance: `python-jose` pinned >=3.4.0, added to the SOUP list with risk
  class and monitoring; `pip-audit` runs in CI and fails on High CVEs.

**T10 (F10/F11) -- Apply security headers everywhere; fix FHIR CORS.**
- Acceptance: Security-header middleware applied to all FastAPI services; FHIR
  CORS has no `*` fallback; Next app sets CSP/HSTS/frame headers. Test asserts
  headers on a sample response per service.

**T11 (F12/F13/F15/F16) -- Config hardening cleanup.**
- Acceptance: token-exchange error body no longer logged; startup assertions
  forbid E2E mode and known dev DB passwords outside local; core-api CORS
  methods/headers constrained to those used.

### Governance track (parallel, non-code)

**T12 (F17) -- Complete DTAC v2, submit DSPT v8, schedule pen test, pursue Cyber
Essentials.** Acceptance: DTAC v2 form completed; DSPT v8 submitted before
2026-06-30; CREST pen test booked; Cyber Essentials self-assessment underway.

---

## 5. Could not verify / out of scope

- **Edge/WAF controls (Cloudflare):** DC-DEP-001 states rate limiting and
  browser security headers are applied at the edge. This could not be verified
  from the repository. If true, it partially compensates for F4 and F11, but
  not for F1 (the service-secret injection happens after the edge).
- **National Data Opt-Out enforcement (DC-NDOO-001):** NDOO applicability and
  any code-level enforcement were not assessed in this pass.
- **Infrastructure security:** Azure Container Apps network segmentation, mTLS,
  Key Vault access policies, TLS termination, and Neo4j Aura configuration are
  organisation/infra concerns not visible in the repo.
- **Organisation-level Cyber Essentials / CE Plus, DSPT submission, and
  penetration-test execution:** these are process activities, not code.
- **Runtime DAST / dependency CVE confirmation:** no live scanning was performed;
  CVE references for python-jose are from public advisories and the version
  floor, not a runtime scan.
- **LLM provider-side controls:** AWS Bedrock / Azure OpenAI internal handling of
  special-category data relies on the DPA (DC-DPA-002) and Transfer Risk
  Assessment (DC-TRA-001); not independently verified here. Note that clinical
  text sent for coding is, by design, not de-identified (de-identification at
  `services/api/app/services/test_patient_redactor.py` applies to the test-data
  clone flow, not the live LLM boundary); this transfer must remain covered by
  the DPA/TRA and data-minimisation review.
- **Patient-data context:** per repo rules, no live patient data was queried; no
  patient identifiers, NHS numbers, secrets, or tokens appear in this report.

---

## 6. Atlas Risk / VT artefacts

No Atlas design-control artefacts were created during this review. Findings are
advisory until a named owner accepts them, and the brief instructs that new
safety-relevant controls be created via the Atlas MCP only after acceptance (and
that Class C controls be escalated rather than invented).

Two findings are safety-relevant and, on owner acceptance, warrant Atlas
artefacts (to be created through `user-atlas-design-controls` against
PROD-LEO-CLINICAL-DECISION-SUPPORT-20260515-118182E4, all Class B with the human-review gate
intact):

- **Proposed Risk (from F1):** "Unauthenticated write to clinical terminology
  graph via proxy service-secret injection." Hazard: corruption of SNOMED/
  terminology that feeds coding proposals; mitigated by the existing mandatory
  human review of every proposal (keeps it Class B). Link a verification test
  that proves an unauthenticated proxied terminology mutation is rejected.
- **Proposed Risk (from F2):** "Password-only authentication accepted when MFA
  config is unavailable." Hazard: weaker identity assurance for clinical users.
  Link a VT proving MFA fails closed.

These should be created with the full UN -> DI -> DO -> Risk -> VT chain once a
human owner accepts the findings. Existing related items in the threat model and
pen-test summary (TM-LOG-001, TM-AUTH-001, GAP-012) should be cross-referenced.

---

## 7. Method and provenance

- Standards verified against current published guidance on 2026-06-04: NHS DTAC
  v2 (NHS England, updated form 24 Feb 2026, mandatory 6 Apr 2026; five domains;
  C3 Technical Security now requires the DSIT/NCSC Software Security Code of
  Practice; MFA expanded to admin/remote access) and OWASP ASVS 5.0.0 (released
  30 May 2025; 17 chapters; V6 Authentication, V7 Session, V8 Authorization,
  V9 Self-Contained Tokens, V10 OAuth/OIDC, V14 Data Protection, V16 Logging).
  DSPT v8 specifics (item 4.5.3, CE Plus equivalence removal) are taken from the
  review brief and not independently re-confirmed here.
- Code evidence was gathered by static review (Read/Grep/Glob). File:line
  references reflect the repository state at review time.
- No application source was modified. No live patient data was accessed.



