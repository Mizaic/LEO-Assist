import type { OperationOutcome } from '@/lib/types/fhir';

function resolveApiBaseUrl(): string {
  const envBase = process.env.NEXT_PUBLIC_API_BASE?.replace(/\/+$/, '');
  if (!envBase) return 'http://localhost:8000';
  if (typeof window === 'undefined') return envBase;

  try {
    const parsed = new URL(envBase);
    const uiHost = window.location.hostname;
    const loopbackHosts = new Set(['localhost', '127.0.0.1']);

    // Keep backend host aligned with current UI host on loopback to avoid SameSite cookie drops.
    if (loopbackHosts.has(parsed.hostname) && loopbackHosts.has(uiHost) && parsed.hostname !== uiHost) {
      parsed.hostname = uiHost;
      return parsed.toString().replace(/\/+$/, '');
    }
  } catch {
    // Fall back to env value if URL parsing fails.
  }

  return envBase;
}

const API_BASE_URL = resolveApiBaseUrl();

const PROXY_BASE = `${API_BASE_URL}/api/proxy`;

let reauthInProgress = false;

async function triggerReauth(): Promise<void> {
  if (typeof window === 'undefined' || reauthInProgress) return;
  reauthInProgress = true;
  try {
    const next = encodeURIComponent(window.location.pathname || '/dashboard');
    window.location.href = `${API_BASE_URL}/auth/login?next_url=${next}`;
  } finally {
    reauthInProgress = false;
  }
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public operationOutcome?: OperationOutcome
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE';
  body?: unknown;
  headers?: Record<string, string>;
  requireAuth?: boolean;
}

export async function apiFetch<T>(
  endpoint: string,
  options: RequestOptions = {}
): Promise<T> {
  const { method = 'GET', body, headers = {}, requireAuth = true } = options;

  const url =
    endpoint.startsWith("/api/proxy")
      ? `${API_BASE_URL}${endpoint}`
      : endpoint.startsWith("/api/")
        ? (typeof window !== "undefined" ? window.location.origin : "") + endpoint
        : `${PROXY_BASE}${endpoint}`;

  const requestHeaders: Record<string, string> = {
    'Content-Type': 'application/fhir+json',
    Accept: 'application/fhir+json',
    ...headers,
  };

  let response: Response;
  try {
    response = await fetch(url, {
      method,
      headers: requestHeaders,
      body: body ? JSON.stringify(body) : undefined,
      credentials: 'include',
    });
  } catch {
    throw new ApiError('Failed to reach API', 0);
  }

  if (response.status === 204) return undefined as T;

  const contentType = response.headers.get('content-type');
  let data: T | OperationOutcome;

  if (
    contentType?.includes('application/json') ||
    contentType?.includes('application/fhir+json')
  ) {
    data = await response.json();
  } else if (contentType?.includes('text/plain') && !response.ok) {
    const text = await response.text();
    if (response.status === 401 && requireAuth) await triggerReauth();
    throw new ApiError(text.trim() || `Request failed (${response.status})`, response.status);
  } else {
    if (response.status === 401 && requireAuth) await triggerReauth();
    throw new ApiError(
      `Unexpected content type: ${contentType || 'unknown'}`,
      response.status
    );
  }

  if (!response.ok) {
    if (response.status === 401 && requireAuth) await triggerReauth();
    const outcome = data as OperationOutcome & { detail?: string };
    const message =
      outcome.issue?.[0]?.diagnostics ||
      (typeof outcome.detail === 'string' ? outcome.detail : Array.isArray(outcome.detail) ? outcome.detail[0] : undefined) ||
      'API request failed';
    throw new ApiError(message, response.status, outcome);
  }

  return data as T;
}

export const api = {
  get: <T>(endpoint: string, options?: Omit<RequestOptions, 'method' | 'body'>) =>
    apiFetch<T>(endpoint, { ...options, method: 'GET' }),

  post: <T>(endpoint: string, body: unknown, options?: Omit<RequestOptions, 'method' | 'body'>) =>
    apiFetch<T>(endpoint, { ...options, method: 'POST', body }),

  put: <T>(endpoint: string, body: unknown, options?: Omit<RequestOptions, 'method' | 'body'>) =>
    apiFetch<T>(endpoint, { ...options, method: 'PUT', body }),

  delete: <T>(endpoint: string, options?: Omit<RequestOptions, 'method' | 'body'>) =>
    apiFetch<T>(endpoint, { ...options, method: 'DELETE' }),
};
