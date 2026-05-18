/**
 * TypeScript client for the /api/mail/* endpoints.
 * All endpoints are admin-only on the backend.
 *
 * Atlas trace:
 *   DO: DO-19BBE973
 *   DI: DI-B746E19E
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-19BBE973")
 */
import { triggerReauth } from "./client";

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      "X-Requested-With": "XMLHttpRequest",
      ...init?.headers,
    },
    ...init,
  });
  if (!res.ok) {
    if (res.status === 401) await triggerReauth();
    const text = await res.text().catch(() => res.statusText);
    throw new Error(text || `Request failed (${res.status})`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export interface MailMessage {
  id: string;
  subject: string;
  from_name: string;
  from_address: string;
  preview: string;
  received_at: string;
  is_read: boolean;
  is_bounce: boolean;
}

export interface MailMessageDetail extends MailMessage {
  body_html: string;
}

export function listMessages(skip = 0, top = 50): Promise<MailMessage[]> {
  return apiFetch<MailMessage[]>(`/api/mail/messages?skip=${skip}&top=${top}`);
}

export function getMessage(id: string): Promise<MailMessageDetail> {
  return apiFetch<MailMessageDetail>(`/api/mail/messages/${encodeURIComponent(id)}`);
}

export function replyToMessage(id: string, text: string): Promise<{ status: string }> {
  return apiFetch<{ status: string }>(
    `/api/mail/messages/${encodeURIComponent(id)}/reply`,
    { method: "POST", body: JSON.stringify({ text }) },
  );
}

export function deleteMessage(id: string): Promise<{ status: string }> {
  return apiFetch<{ status: string }>(
    `/api/mail/messages/${encodeURIComponent(id)}`,
    { method: "DELETE" },
  );
}
