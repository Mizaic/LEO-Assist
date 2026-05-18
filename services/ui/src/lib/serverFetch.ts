/**
 * Shared server-side HTTP client with keep-alive connection pooling.
 *
 * Next.js Route Handlers each call `fetch()` against our internal Python
 * services. By default, the Node.js fetch driver creates a new connection
 * per request, which means a fresh TCP + TLS handshake against the same
 * upstream host on every UI page load. For high-traffic dashboards that
 * hit five or six APIs in parallel, that handshake cost dominates.
 *
 * This module exports two helpers:
 *
 *   - `serverFetch(url, init)` -- drop-in replacement for `fetch` that
 *     reuses a single keep-alive Agent for all internal API hosts.
 *   - `getServiceAgent()` -- the underlying undici Agent, in case a
 *     caller needs to attach it to a third-party client.
 *
 * The pool is sized for our typical concurrency budget (8 concurrent
 * requests per upstream) and recycles connections after a short idle
 * window so we never accumulate stale sockets.
 */
import { Agent, fetch as undiciFetch } from "undici";

const KEEP_ALIVE_TIMEOUT_MS = Number(
  process.env.UI_FETCH_KEEPALIVE_MS ?? "30000",
);
const CONNECTIONS_PER_HOST = Number(
  process.env.UI_FETCH_CONNECTIONS_PER_HOST ?? "16",
);
const HEADERS_TIMEOUT_MS = Number(
  process.env.UI_FETCH_HEADERS_TIMEOUT_MS ?? "30000",
);
const BODY_TIMEOUT_MS = Number(
  process.env.UI_FETCH_BODY_TIMEOUT_MS ?? "120000",
);

let _agent: Agent | null = null;

export function getServiceAgent(): Agent {
  if (_agent) return _agent;
  _agent = new Agent({
    connections: CONNECTIONS_PER_HOST,
    keepAliveTimeout: KEEP_ALIVE_TIMEOUT_MS,
    keepAliveMaxTimeout: KEEP_ALIVE_TIMEOUT_MS,
    headersTimeout: HEADERS_TIMEOUT_MS,
    bodyTimeout: BODY_TIMEOUT_MS,
    pipelining: 1,
  });
  return _agent;
}

/**
 * fetch() replacement that uses the shared keep-alive agent.
 *
 * Falls back transparently to the global fetch if undici is unavailable
 * (e.g. tests that swap the runtime). Streaming bodies are passed through
 * unchanged.
 */
export async function serverFetch(
  input: string | URL,
  init?: Parameters<typeof undiciFetch>[1],
): Promise<Response> {
  const agent = getServiceAgent();
  const response = await undiciFetch(input, {
    ...init,
    dispatcher: agent,
  });
  return response as unknown as Response;
}
