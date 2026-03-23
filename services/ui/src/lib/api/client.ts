import type { OperationOutcome } from '@/lib/types/fhir';

function resolveApiBaseUrl(): string {
  if (typeof window !== 'undefined') return window.location.origin;
  return (process.env.INTERNAL_API_BASE || 'http://localhost:8000').replace(/\/+$/, '');
}

const API_BASE_URL = resolveApiBaseUrl();

const PROXY_BASE = `${API_BASE_URL}/api/proxy`;

let reauthInProgress = false;

async function triggerReauth(): Promise<void> {
  if (typeof window === 'undefined' || reauthInProgress) return;
  reauthInProgress = true;
  try {
    const next = encodeURIComponent(window.location.pathname || "/care/dashboard");
    // Same-origin path so the nonce cookie is set on the UI origin.
    window.location.href = `/auth/login?next_url=${next}`;
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
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
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
    'X-Requested-With': 'XMLHttpRequest',
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
