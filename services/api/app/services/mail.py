"""Microsoft Graph mail service.

Atlas trace:
  DO: DO-92F92EFB
  DI: DI-88C1715A
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-92F92EFB")

Sends and reads mail via Microsoft Graph using app-only credentials from the
**mail Graph app** (MAIL_GRAPH_*), which may live in a different Entra tenant
than the LEO user-login app (AZURE_AD_*). The mailbox address comes from
MAIL_FROM_ADDRESS (Bicep mailFromAddress).

Required application permissions on the mail Graph app registration:
  Mail.Send        - POST /users/{mailbox}/sendMail
  Mail.ReadWrite   - GET/PATCH/DELETE /users/{mailbox}/messages
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_MAIL_GRAPH_TENANT_ID = os.getenv("MAIL_GRAPH_TENANT_ID", "")
_MAIL_GRAPH_CLIENT_ID = os.getenv("MAIL_GRAPH_CLIENT_ID", "")
_MAIL_GRAPH_CLIENT_SECRET = os.getenv("MAIL_GRAPH_CLIENT_SECRET", "")
_MAIL_FROM = os.getenv("MAIL_FROM_ADDRESS", "")
_FRONTEND_URL = os.getenv("FRONTEND_URL", "")

_GRAPH_BASE = "https://graph.microsoft.com/v1.0"

_BOUNCE_SUBJECTS = re.compile(
    r"^(undeliverable|delivery status notification|delivery failed|"
    r"failure notice|mail delivery failed|returned mail)",
    re.IGNORECASE,
)
_BOUNCE_SENDERS = re.compile(r"mailer-daemon|postmaster", re.IGNORECASE)


def _mail_graph_token_url() -> str:
    tenant = _MAIL_GRAPH_TENANT_ID.strip()
    if not tenant:
        raise RuntimeError(
            "MAIL_GRAPH_TENANT_ID is not set (mail Graph app tenant)"
        )
    return f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"


def _get_graph_token() -> str:
    """Obtain an app-only access token for the mail Graph app."""
    client_id = _MAIL_GRAPH_CLIENT_ID.strip()
    client_secret = _MAIL_GRAPH_CLIENT_SECRET.strip()
    if not client_id or not client_secret:
        raise RuntimeError(
            "MAIL_GRAPH_CLIENT_ID and MAIL_GRAPH_CLIENT_SECRET must be set"
        )
    resp = httpx.post(
        _mail_graph_token_url(),
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "https://graph.microsoft.com/.default",
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_get_graph_token()}",
        "Content-Type": "application/json",
    }


def send_onboarding_invite_email(
    to_email: str,
    to_name: str,
    org_name: str,
    org_type: str,
) -> None:
    """Send an onboarding invite to a newly provisioned org primary user."""
    org_type_label = {
        "alliance": "Cancer Alliance",
        "icb": "Integrated Care Board",
        "pcn": "Primary Care Network",
        "gp": "GP Practice",
    }.get(org_type, "Organisation")
    subject = f"Your LEO account is ready -- {org_name}"
    accept_url = f"{_FRONTEND_URL}/onboarding/accept"
    body_html = _onboarding_body_html(to_name, to_email, org_name, org_type_label, accept_url)
    _send_html_mail(to_email, to_name or to_email, subject, body_html)


def send_invite_email(to_email: str, to_name: str, invited_by: str) -> None:
    """Send a plain-English invite to a newly added user."""
    subject = "You have been added to LEO"
    body_html = _invite_body_html(to_name, to_email, invited_by)
    _send_html_mail(to_email, to_name or to_email, subject, body_html)


def _send_html_mail(
    to_email: str, to_name: str, subject: str, body_html: str
) -> None:
    if not _MAIL_FROM.strip():
        raise RuntimeError("MAIL_FROM_ADDRESS is not set")
    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": "HTML", "content": body_html},
            "toRecipients": [
                {"emailAddress": {"address": to_email, "name": to_name}}
            ],
        },
        "saveToSentItems": True,
    }
    resp = httpx.post(
        f"{_GRAPH_BASE}/users/{_MAIL_FROM}/sendMail",
        json=payload,
        headers=_headers(),
        timeout=20,
    )
    resp.raise_for_status()


def _onboarding_body_html(
    to_name: str,
    to_email: str,
    org_name: str,
    org_type_label: str,
    accept_url: str,
) -> str:
    return f"""
<html><body style="font-family:Arial,sans-serif;font-size:15px;color:#222;max-width:600px">
  <p>Hi {_escape(to_name or to_email)},</p>
  <p>
    Your <strong>LEO</strong> administrator account has been set up for
    <strong>{_escape(org_name)}</strong> ({_escape(org_type_label)}).
  </p>
  <p>
    As the primary user, you can manage sub-organisations, invite staff,
    and configure your organisation&rsquo;s settings in the LEO portal.
  </p>
  <p>
    To get started, please sign in with your Microsoft work account and
    complete the short setup wizard:
  </p>
  <p style="margin:24px 0">
    <a href="{accept_url}"
       style="background:#1565C0;color:#fff;padding:12px 24px;text-decoration:none;border-radius:4px;font-weight:bold">
      Set up my organisation in LEO
    </a>
  </p>
  <p>
    If you have any questions, contact us at
    <a href="mailto:{_MAIL_FROM}">{_MAIL_FROM}</a>.
  </p>
  <p style="color:#777;font-size:13px">
    You are receiving this because Mizaic has set up a LEO account for your organisation.
    If this was a mistake, please reply to this email.
  </p>
</body></html>
""".strip()


def _invite_body_html(to_name: str, to_email: str, invited_by: str) -> str:
    return f"""
<html><body style="font-family:Arial,sans-serif;font-size:15px;color:#222;max-width:600px">
  <p>Hi {_escape(to_name or to_email)},</p>
  <p>
    <strong>{_escape(invited_by)}</strong> has added you to <strong>LEO</strong> &mdash;
    a tool that helps clinicians review patient data safely.
  </p>
  <p>
    To get started, sign in using your Microsoft work account:
  </p>
  <p style="margin:24px 0">
    <a href="{_FRONTEND_URL}"
       style="background:#1565C0;color:#fff;padding:12px 24px;text-decoration:none;border-radius:4px;font-weight:bold">
      Sign in to LEO
    </a>
  </p>
  <p>
    If you have any questions, reply to this email or contact us at
    <a href="mailto:{_MAIL_FROM}">{_MAIL_FROM}</a>.
  </p>
  <p style="color:#777;font-size:13px">
    You are receiving this because an admin added your email address to LEO.
    If this was a mistake, you do not need to do anything.
  </p>
</body></html>
""".strip()


def list_messages(skip: int = 0, top: int = 50) -> list[dict[str, Any]]:
    """Return a summary list of messages from the support inbox."""
    resp = httpx.get(
        f"{_GRAPH_BASE}/users/{_MAIL_FROM}/messages",
        params={
            "$top": min(top, 100),
            "$skip": skip,
            "$select": "id,subject,from,receivedDateTime,bodyPreview,isRead",
            "$orderby": "receivedDateTime desc",
        },
        headers=_headers(),
        timeout=20,
    )
    resp.raise_for_status()
    return [_summarise(m) for m in resp.json().get("value", [])]


def get_message(msg_id: str) -> dict[str, Any]:
    """Return the full message including HTML body."""
    resp = httpx.get(
        f"{_GRAPH_BASE}/users/{_MAIL_FROM}/messages/{msg_id}",
        params={"$select": "id,subject,from,toRecipients,receivedDateTime,body,isRead"},
        headers=_headers(),
        timeout=20,
    )
    resp.raise_for_status()
    m = resp.json()
    return {
        **_summarise(m),
        "body_html": m.get("body", {}).get("content", ""),
    }


def reply_to_message(msg_id: str, body_text: str) -> None:
    """Send a plain-text reply to a message."""
    payload = {
        "message": {
            "body": {"contentType": "Text", "content": body_text},
        },
        "comment": body_text,
    }
    resp = httpx.post(
        f"{_GRAPH_BASE}/users/{_MAIL_FROM}/messages/{msg_id}/reply",
        json=payload,
        headers=_headers(),
        timeout=20,
    )
    resp.raise_for_status()


def delete_message(msg_id: str) -> None:
    """Move a message to the Deleted Items folder (soft delete)."""
    resp = httpx.post(
        f"{_GRAPH_BASE}/users/{_MAIL_FROM}/messages/{msg_id}/move",
        json={"destinationId": "deleteditems"},
        headers=_headers(),
        timeout=20,
    )
    resp.raise_for_status()


def mark_read(msg_id: str) -> None:
    """Mark a message as read."""
    resp = httpx.patch(
        f"{_GRAPH_BASE}/users/{_MAIL_FROM}/messages/{msg_id}",
        json={"isRead": True},
        headers=_headers(),
        timeout=15,
    )
    resp.raise_for_status()


def _summarise(m: dict[str, Any]) -> dict[str, Any]:
    sender = m.get("from", {}).get("emailAddress", {})
    from_name = sender.get("name", "")
    from_addr = sender.get("address", "")
    subject = m.get("subject", "(no subject)")
    is_bounce = bool(
        _BOUNCE_SENDERS.search(from_addr)
        or _BOUNCE_SENDERS.search(from_name)
        or _BOUNCE_SUBJECTS.match(subject)
    )
    return {
        "id": m.get("id"),
        "subject": subject,
        "from_name": from_name,
        "from_address": from_addr,
        "preview": m.get("bodyPreview", ""),
        "received_at": m.get("receivedDateTime"),
        "is_read": m.get("isRead", False),
        "is_bounce": is_bounce,
    }


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
