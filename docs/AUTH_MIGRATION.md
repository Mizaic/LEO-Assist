# Auth Migration: NextAuth → Python Backend

Auth has been moved from Next.js (NextAuth) to the Python backend. Tokens stay server-side; the frontend uses a session cookie only.

## Architecture

```
Browser (3000)              Frontend (3000)              Backend (8000)           Azure AD
   |                              |                              |                    |
   |-- Sign in ------------------>|-- Redirect to /auth/login --->|-- Redirect to Azure AD
   |<-- 302 to Azure AD ---------------------------------------------------------->|
   |                              |                              |                    |
   |<-- 302 to /auth/callback?code=... (Azure AD redirects to frontend) ----------|
   |-- GET /auth/callback?code=-->|-- 302 to backend /auth/callback?code=... ------>|
   |                              |                              |-- Exchange code -> Azure AD
   |                              |                              |-- Store in Redis  |
   |<-- Set-Cookie: leo_session <--|<-- 302 to /dashboard <-------|-- Redirect to 3000
   |                              |                              |                    |
   |-- API calls (Cookie) ------->|------------------------------>|-- Proxy with token |
```

## Setup

### 1. Azure AD App Registration

1. Add this redirect URI to **Redirect URIs**:
   - `http://localhost:3000/auth/callback` (Azure AD redirects here; frontend forwards to backend)

2. In **Manifest**, set `accessTokenAcceptedVersion` to `2` so tokens use the v2.0 issuer (`login.microsoftonline.com/.../v2.0`) instead of v1.0 (`sts.windows.net`). This keeps tokens smaller and consistent.

### 2. Environment Variables

In `secrets/.env`:

```env
# Optional: defaults to FRONTEND_URL/auth/callback
AUTH_REDIRECT_URI=http://localhost:3000/auth/callback
FRONTEND_URL=http://localhost:3000
NEXT_PUBLIC_API_BASE=http://localhost:8000
FHIR_API_SCOPE=api://c97f7ad9-845f-420c-ae3f-fa5c5d815bcd/.default
```

### 3. Start Services

Use `scripts/start_primary_care.ps1` so all env vars are loaded. The Core API (8000) must run before the UI.

## Flow

1. **Sign in**: User clicks "Sign in" → redirect to `http://localhost:8000/auth/login?next_url=/dashboard`
2. **OAuth**: Backend redirects to Azure AD; user signs in
3. **Callback**: Azure redirects to `http://localhost:3000/auth/callback` with code; frontend redirects to backend to complete
4. **Session**: Backend exchanges code for tokens, stores in Redis, sets `leo_session` cookie, redirects to frontend
5. **API calls**: Frontend calls `http://localhost:8000/api/proxy/fhir/*` and `.../analytics/*` with `credentials: 'include'`; backend adds Bearer token and proxies

## Removed

- NextAuth, SessionProvider
- `lib/auth.ts`, `lib/redis.ts`, `lib/redis-adapter.ts`
- `types/next-auth.d.ts`
- `ioredis`, `next-auth` npm packages
