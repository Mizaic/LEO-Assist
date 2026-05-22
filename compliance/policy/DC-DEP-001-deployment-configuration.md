# Deployment Configuration Specification

| Field            | Value                                               |
| ---------------- | --------------------------------------------------- |
| Document ID      | DC-DEP-001                                          |
| Version          | 1.1.0                                               |
| Status           | Draft                                               |
| Date             | 2026-03-03                                          |
| Standard         | IEC 81001-5-1:2021 (5.3), NHS DSPT                  |
| Classification   | QMS -- Design Controls                              |
| Trace            | DC-TM-SEC-002 (threat model), DI-LEO-AI-052         |

---

## 1  Purpose

This document specifies the required configuration for deploying the
platform into a new environment. It covers identity provider (Azure AD /
Microsoft Entra ID) app registration, edge proxy (Cloudflare), TLS, and
environment-specific parameters that affect security posture.

Deployers MUST verify each item before the environment is connected to
production data or real clinical records.

---

## 2  Azure AD / Microsoft Entra ID App Registration

### 2.1  Registration Properties

| Property                          | Required Value           | Rationale                                                                                  |
| --------------------------------- | ------------------------ | ------------------------------------------------------------------------------------------ |
| `displayName`                     | Per environment          | Clear naming -- e.g. "Mizaic Atlas", "Mizaic Atlas (Dev)"                                   |
| `signInAudience`                  | `AzureADMultipleOrgs`    | Multi-tenant SaaS; customer tenants authenticate against their own Entra directory          |
| `accessTokenAcceptedVersion`      | **2**                    | v1 tokens use `sts.windows.net` issuer and lack reliable `aud` validation; the API explicitly rejects v1 tokens |
| `enableAccessTokenIssuance`       | **false**                | Implicit grant is not used; the platform uses authorization code flow                       |
| `enableIdTokenIssuance`           | **false**                | ID tokens are obtained via the token endpoint, not the authorize endpoint                   |

### 2.2  Redirect URIs

Each environment MUST have its own app registration (or at minimum, its
own set of redirect URIs). Localhost URIs MUST NOT appear on registrations
used by non-development environments.

| Environment | Redirect URI pattern                                  | Type |
| ----------- | ----------------------------------------------------- | ---- |
| Production  | `https://<prod-domain>/auth/callback`                 | Web  |
| Validation  | `https://<val-domain>/auth/callback`                  | Web  |
| Development | `https://<dev-domain>/auth/callback`                  | Web  |
| Local dev   | `http://localhost:3000/auth/callback`                  | Web  |

**Anti-patterns to avoid:**

- Mixing `localhost` URIs with production callbacks in a single registration
- Leaving ngrok / tunnel URIs in place after debugging sessions
- Adding `https://jwt.ms` to non-development registrations

### 2.3  API Permissions and Scopes

The platform requests the following scopes during the OAuth authorize step:

| Scope                                                           | Purpose                     |
| --------------------------------------------------------------- | --------------------------- |
| `openid`                                                        | ID token with user identity |
| `profile`                                                       | Display name                |
| `email`                                                         | Email claim                 |
| `api://<client-id>/.default`                                    | API access token            |

The `AZURE_AD_SCOPE` environment variable controls the scope string
(default: `openid profile email api://<client-id>/.default`).

### 2.4  Token Validation

The API performs cryptographic JWT verification on every ID token:

| Check           | Implementation                                                  |
| --------------- | --------------------------------------------------------------- |
| Signature       | RS256 against Azure AD JWKS (`/discovery/v2.0/keys`)            |
| Issuer          | `https://login.microsoftonline.com/{tenant_id}/v2.0`            |
| Audience        | Must equal `AZURE_AD_CLIENT_ID`                                 |
| Expiry          | `exp` and `nbf` both verified                                   |
| v1 rejection    | Tokens with `sts.windows.net` issuer are rejected with `401`    |
| MFA enforcement | Optional -- when `require_mfa=true` in SystemConfig, the `amr` claim must contain `mfa` |

### 2.5  Client Secrets

| Requirement                    | Detail                                                         |
| ------------------------------ | -------------------------------------------------------------- |
| Storage                        | Azure Key Vault (secret name: `azure-ad-client-secret`)        |
| Rotation                       | Every 6 months; track expiry dates in calendar                 |
| Naming convention              | `<env>-<purpose>` (e.g. `prod-api`, `val-api`)                |
| Expired secrets                | Remove promptly -- expired secrets remain attack surface       |
| Number of active secrets       | Maximum 2 per registration (current + next for zero-downtime rotation) |

### 2.6  Current Production Registration

| Property                     | Value                                          |
| ---------------------------- | ---------------------------------------------- |
| Display name                 | Mizaic Atlas                                   |
| Application (client) ID     | `c97f7ad9-845f-420c-ae3f-fa5c5d815bcd`         |
| Sign-in audience             | AzureADMultipleOrgs                            |
| Token version                | 2                                              |
| Implicit access token        | **false** (disabled 2026-03-03)                |
| Implicit ID token            | false                                          |
| Production redirect URI      | `https://leo-ai-audit.healthcarecopilot.ai/auth/callback` |

---

## 3  Cloudflare Edge Configuration

The `healthcarecopilot.ai` zone is proxied through Cloudflare, providing
edge security before traffic reaches Azure Container Apps.

### 3.1  Verified Configuration (2026-03-03)

| Header / Feature               | Observed Value                                      | Status |
| ------------------------------- | --------------------------------------------------- | ------ |
| `Server`                        | `cloudflare`                                        | OK     |
| `Strict-Transport-Security`     | `max-age=15552000` (180 days)                       | OK     |
| `X-Content-Type-Options`        | `nosniff`                                           | OK     |
| `Referrer-Policy`               | `strict-origin-when-cross-origin`                   | OK     |
| `Permissions-Policy`            | `camera=(), microphone=(self), geolocation=(), interest-cohort=()` | OK |
| CF-RAY                          | Present (London POP: LHR)                           | OK     |
| DDoS protection                 | Included with all Cloudflare plans                  | OK     |

### 3.2  Deployment Checklist

The following items MUST be verified via the Cloudflare dashboard for
each new environment:

- [ ] DNS record is orange-cloud (proxied), not grey (DNS-only)
- [ ] SSL/TLS mode is **Full (Strict)** -- not Flexible or Full
- [ ] HSTS is enabled with `max-age >= 15552000` and `includeSubDomains`
- [ ] WAF managed ruleset is enabled (Cloudflare Managed Rules)
- [ ] OWASP Core Rule Set (CRS) is enabled at Paranoia Level 1+
- [ ] Rate limiting rules are configured:
  - `/auth/login`: max 10 requests/minute per IP
  - `/auth/callback`: max 20 requests/minute per IP
  - `/api/*`: max 100 requests/minute per IP (aligns with application-layer `slowapi`)
- [ ] Bot Fight Mode or Super Bot Fight Mode is enabled
- [ ] Browser Integrity Check is enabled
- [ ] Hotlink Protection is enabled
- [ ] Email Address Obfuscation is enabled
- [ ] Cloudflare plan tier is documented for NHS DSPT evidence

### 3.3  TLS Requirements

| Requirement          | Value                                                           |
| -------------------- | --------------------------------------------------------------- |
| Minimum TLS version  | 1.2                                                             |
| Cipher suites        | Cloudflare default (ECDHE-based, no CBC)                        |
| Certificate          | Cloudflare Universal SSL or Advanced Certificate Manager        |
| Origin certificate   | Azure-managed TLS on Container App custom domain                |

---

## 4  Environment Parameters (Bicep)

The following security-relevant parameters are set per environment in
`infra/bicep/parameters/<env>.bicepparam`:

| Parameter           | Production                                  | Validation                                | Development                                                |
| ------------------- | ------------------------------------------- | ----------------------------------------- | ---------------------------------------------------------- |
| `allowedOrigins`    | `https://leo-ai-audit.healthcarecopilot.ai,https://leoaiwidgetcdnprod.z33.web.core.windows.net` | `https://atlas-val.healthcarecopilot.ai,https://leoaiwidgetcdnval.z33.web.core.windows.net` | `https://leo-ai-audit.healthcarecopilot.ai,...,https://leoaiwidgetcdndev.z33.web.core.windows.net,http://localhost:3000` |
| `WIDGET_PUBLIC_HOST`| `leoaiwidgetcdnprod.z33.web.core.windows.net` | `leoaiwidgetcdnval.z33.web.core.windows.net` | `leoaiwidgetcdndev.z33.web.core.windows.net` |
| `cookieSecure`      | `true`                                      | `true`                                    | `true`                                                     |
| `sessionTtlHours`   | `24`                                        | `12`                                      | `12`                                                       |
| `frontendUrl`       | `https://leo-ai-audit.healthcarecopilot.ai` | `https://atlas-val.healthcarecopilot.ai`  | `https://atlas-dev.healthcarecopilot.ai`                   |

### 4.1  Security Parameter Rules

| Rule                                                | Rationale                                                    |
| --------------------------------------------------- | ------------------------------------------------------------ |
| `cookieSecure` MUST be `true` in all environments   | Prevents session cookie transmission over HTTP               |
| `allowedOrigins` MUST NOT contain `*`               | Wildcard CORS allows any origin to make authenticated requests |
| `allowedOrigins` MUST NOT contain `localhost` in prod/val | Prevents local attacker from exploiting CORS                |
| `sessionTtlHours` MUST be ≤ 168 (7 days)           | NHS DSPT requirement for session expiry                      |
| `frontendUrl` MUST match an Azure AD redirect URI   | OAuth callback will fail otherwise                           |

---

## 5  Secrets Management

### 5.1  Required Secrets (Azure Key Vault)

Secret names use kebab-case in Key Vault. The canonical mapping is defined in
`libs/keyvault/loader.py` (`SECRET_MAP`) and pushed by
`infra/scripts/migrate-secrets.ps1` from `secrets/.env`.

| Secret Name                         | Env var                              | Purpose                              | Source                      |
| ----------------------------------- | ------------------------------------ | ------------------------------------ | --------------------------- |
| `azure-ad-client-id`                | `AZURE_AD_CLIENT_ID`                 | OAuth client ID                      | Entra app registration      |
| `azure-ad-client-secret`            | `AZURE_AD_CLIENT_SECRET`             | OAuth token exchange                 | Entra app registration      |
| `azure-ad-tenant-id`                | `AZURE_AD_TENANT_ID`                 | Entra tenant                         | Entra directory             |
| `neo4j-patient-uri`                 | `NEO4J_URI`                          | Patient graph connection             | Neo4j admin                 |
| `neo4j-patient-password`            | `NEO4J_PASSWORD`                     | Patient graph password               | Neo4j admin                 |
| `neo4j-knowledge-uri`               | `KNOWLEDGE_GRAPH_NEO4J_URI`          | Knowledge graph connection           | Neo4j admin                 |
| `neo4j-knowledge-password`          | `KNOWLEDGE_GRAPH_NEO4J_PASSWORD`     | Knowledge graph password             | Neo4j admin                 |
| `neo4j-guideline-uri`               | `GUIDELINE_NEO4J_URI`                | Guideline graph connection (optional)| Neo4j admin                 |
| `neo4j-guideline-password`          | `GUIDELINE_NEO4J_PASSWORD`           | Guideline graph password (optional)  | Neo4j admin                 |
| `redis-url`                         | `REDIS_URL`                          | Redis connection string (TLS)        | Redis Enterprise admin        |
| `azure-openai-api-key`              | `AZURE_OPENAI_API_KEY`               | Azure OpenAI LLM access              | Azure OpenAI resource       |
| `azure-openai-endpoint`             | `AZURE_OPENAI_ENDPOINT`              | Azure OpenAI endpoint URL            | Azure OpenAI resource       |
| `azure-storage-connection-string`   | `AZURE_STORAGE_CONNECTION_STRING`    | Blob model store                     | Storage account admin       |
| `azure-service-bus-connection-string` | `AZURE_SERVICE_BUS_CONNECTION_STRING` | Service Bus queues                 | Service Bus admin           |
| `aws-access-key-id`                 | `AWS_ACCESS_KEY_ID`                  | AWS Bedrock LLM access               | AWS IAM                     |
| `aws-secret-access-key`             | `AWS_SECRET_ACCESS_KEY`              | AWS Bedrock LLM access               | AWS IAM                     |
| `aws-big-model`                     | `AWS_BIG_MODEL`                      | Bedrock model ID (big tier)          | AWS IAM / ops config        |
| `aws-small-model`                   | `AWS_SMALL_MODEL`                    | Bedrock model ID (small tier)        | AWS IAM / ops config        |
| `aws-max-model`                     | `AWS_MAX_MODEL`                      | Bedrock model ID (max tier)          | AWS IAM / ops config        |
| `snomed-api-key`                    | `SNOMED_API_KEY`                     | NHS SNOMED terminology API           | NHS Terminology Server      |
| `umls-api-key`                      | `UMLS_API_KEY`                       | UMLS terminology API                 | NLM UMLS                    |
| `nhs-trud-api-key`                  | `NHS_TRUD_API_KEY`                   | NHS TRUD terminology sync            | NHS TRUD portal             |
| `nice-api-key`                      | `NICE_API_KEY`                       | NICE Syndication API (guideline ingest) | NICE developer portal   |
| `analytics-api-app-id`              | `ANALYTICS_API_APP_ID`               | Inter-service auth (analytics API)   | Entra app registration      |
| `fhir-api-app-id`                   | `FHIR_API_APP_ID`                    | Inter-service auth (FHIR API)        | Entra app registration      |
| `model-inference-app-id`            | `MODEL_INFERENCE_APP_ID`             | Inter-service auth (model inference) | Entra app registration      |
| `terminology-api-app-id`            | `TERMINOLOGY_API_APP_ID`             | Inter-service auth (terminology API) | Entra app registration      |
| `auth-secret`                       | `AUTH_SECRET`                        | Session signing                      | Generated / ops             |
| `service-auth-secret`               | `SERVICE_AUTH_SECRET`                | Inter-service HMAC authentication    | Generated via `migrate-secrets.ps1` |
| `sdk-host-shared-secret`            | `SDK_HOST_SHARED_SECRET`             | Widget token exchange (host backend) | Generated / ops             |
| `sdk-widget-token-secret`           | `SDK_WIDGET_TOKEN_SECRET`            | Widget JWT signing                   | Generated / ops             |

### 5.2  Secret Hygiene

- Secrets are injected into Container Apps as Key Vault references (not
  plaintext env vars) via the `container-apps.bicep` module.
- `migrate-secrets.ps1` generates `SERVICE_AUTH_SECRET` automatically if
  absent, using `[System.Security.Cryptography.RandomNumberGenerator]`.
- Secrets MUST NOT appear in `.env` files committed to source control.
  The `secrets/` directory is in `.gitignore`.
- Redis is stored as a full TLS connection string in `redis-url`
  (not a bare password). See `infra/bicep/modules/redis.bicep`.

### 5.3  GitHub Actions OIDC (Workload Identity Federation)

GitHub Actions authenticates to Azure without long-lived credentials. Each
workflow context needs a federated credential on the Entra app registration
used for CI/CD.

| Template file                         | Federated credential subject                                      | Used by                          |
| ------------------------------------- | ----------------------------------------------------------------- | -------------------------------- |
| `.federated-cred-main.json`           | `repo:Healthcare-Copilot/LEO-AI-CORE:ref:refs/heads/main`         | CI build (push to main)          |
| `.federated-cred-env-dev.json`        | `repo:Healthcare-Copilot/LEO-AI-CORE:environment:dev`             | CD deploy-dev                    |
| `.federated-cred-env-validation.json` | `repo:Healthcare-Copilot/LEO-AI-CORE:environment:validation`      | CD deploy-val                    |
| `.federated-cred-env-production.json` | `repo:Healthcare-Copilot/LEO-AI-CORE:environment:production`      | CD deploy-prod                   |

Apply each credential once per Entra app registration:

```bash
az ad app federated-credential create \
  --id {app-registration-object-id} \
  --parameters @.federated-cred-env-dev.json
```

GitHub Environment names MUST match the workflow `environment:` field exactly:
`dev`, `validation`, `production` (not `val` or `prod`).

See `infra/github-oidc/README.md` for the full setup checklist.

---

## 6  De-identification (NER Model)

| Parameter               | Required Value       | Rationale                                              |
| ----------------------- | -------------------- | ------------------------------------------------------ |
| `DEIDENTIFY_NER_MODEL`  | `en_core_web_lg`     | Large model catches 19/20 multicultural names vs 10/20 for `en_core_web_sm` |

The small model (`en_core_web_sm`) has demonstrated multicultural bias,
misclassifying South Asian, Irish, Polish, Arabic, Nigerian, Korean,
Turkish, and Hungarian names as GPE, ORG, NORP, or PRODUCT entities.
See `tests/test_deid_completeness.py::TestNerSmallModelBias` for evidence.

---

## 7  New Environment Deployment Checklist

Use this checklist when deploying the platform to a new environment.

### 7.1  Azure AD / Entra ID

- [ ] Create a **separate** app registration for this environment
- [ ] Set `accessTokenAcceptedVersion` to **2** in the app manifest
- [ ] Disable implicit grant (`enableAccessTokenIssuance: false`, `enableIdTokenIssuance: false`)
- [ ] Add only the production redirect URI for this environment (no localhost)
- [ ] Create a client secret, name it `<env>-api`, store in Key Vault
- [ ] Grant `openid`, `profile`, `email` delegated permissions
- [ ] Set `AZURE_AD_CLIENT_ID`, `AZURE_AD_TENANT_ID`, `AZURE_AD_CLIENT_SECRET` in Key Vault
- [ ] Verify login flow end-to-end; confirm v2.0 issuer in token

### 7.2  Cloudflare

- [ ] Create DNS record as orange-cloud (proxied)
- [ ] Verify SSL/TLS mode is Full (Strict)
- [ ] Enable HSTS with recommended settings
- [ ] Enable WAF managed rulesets
- [ ] Configure rate limiting rules per Section 3.2
- [ ] Verify security headers appear in HTTP response

### 7.3  Infrastructure

- [ ] Run `migrate-secrets.ps1` to populate Key Vault (all secrets in Section 5.1)
- [ ] Create GitHub OIDC federated credentials from Section 5.3 templates
- [ ] Set GitHub Environment secrets: `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`
- [ ] Set `DEIDENTIFY_NER_MODEL=en_core_web_lg`
- [ ] Verify `cookieSecure=true` in Bicep parameters
- [ ] Verify `allowedOrigins` contains only the new environment's domain
- [ ] Verify `frontendUrl` matches the Azure AD redirect URI
- [ ] Run `tests/test_infra_security.py` against the new parameter file

### 7.4  Post-Deployment Verification

- [ ] Login redirects to Azure AD v2.0 endpoint
- [ ] Session cookie has `Secure`, `HttpOnly`, `SameSite=Lax` attributes
- [ ] `/auth/session` returns user claims after login
- [ ] v1.0 tokens are rejected (test with a v1-configured app if possible)
- [ ] Rate limiting is active (send > threshold requests, expect 429)
- [ ] CORS rejects requests from unlisted origins

---

## 8  Revision History

| Version | Date       | Author            | Changes                           |
| ------- | ---------- | ----------------- | --------------------------------- |
| 1.1.0   | 2026-05-22 | Platform team     | Align KV secret names with `migrate-secrets.ps1` / `loader.py`; add OIDC federated credential templates; document Redis URL format |
| 1.0.0   | 2026-03-03 | Security sweep    | Initial version from threat model findings |

---

*This document is referenced by DC-TM-SEC-002 (threat model) and should
be reviewed whenever the authentication architecture, edge proxy, or
deployment topology changes.*
