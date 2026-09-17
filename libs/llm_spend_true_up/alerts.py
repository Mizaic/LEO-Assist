"""Send ops alerts from env-configured From and To addresses.

Atlas trace:
  DI: DI-3E297B23
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-3E297B23")
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Sequence

logger = logging.getLogger(__name__)


def parse_alert_recipients(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [part.strip() for part in str(raw).split(",") if part.strip()]


def alert_addresses() -> tuple[str, list[str]]:
    from_addr = os.getenv("MAIL_ALERTS_FROM_ADDRESS", "").strip()
    to_addrs = parse_alert_recipients(os.getenv("MAIL_ALERTS_TO_ADDRESSES", ""))
    return from_addr, to_addrs


def maybe_send_alert(
    subject: str,
    body: str,
    *,
    send_mail: Callable[..., None] | None = None,
) -> bool:
    """Send if both env addresses are set. Never fall back to a hardcoded From."""
    from_addr, to_addrs = alert_addresses()
    if not from_addr or not to_addrs:
        logger.warning("alerts: skip send -- MAIL_ALERTS_FROM_ADDRESS or TO is empty")
        return False
    mailer = default_send_mail if send_mail is None else send_mail
    mailer(
        subject=subject,
        body=body,
        from_address=from_addr,
        to_addresses=to_addrs,
    )
    return True


def default_send_mail(
    *,
    subject: str,
    body: str,
    from_address: str,
    to_addresses: Sequence[str],
) -> None:
    """Send HTML via Microsoft Graph using the alerts From mailbox."""
    import html

    import httpx

    token = _graph_token()
    safe_body = html.escape(body)
    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": "HTML", "content": f"<pre>{safe_body}</pre>"},
            "toRecipients": [
                {"emailAddress": {"address": addr, "name": addr}}
                for addr in to_addresses
            ],
        },
        "saveToSentItems": True,
    }
    resp = httpx.post(
        f"https://graph.microsoft.com/v1.0/users/{from_address}/sendMail",
        json=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        timeout=20,
    )
    resp.raise_for_status()


def _graph_token() -> str:
    import httpx

    client_id = os.getenv("MAIL_GRAPH_CLIENT_ID", "").strip()
    client_secret = os.getenv("MAIL_GRAPH_CLIENT_SECRET", "").strip()
    tenant = os.getenv("MAIL_GRAPH_TENANT_ID", "").strip()
    if not client_id or not client_secret or not tenant:
        raise RuntimeError("MAIL_GRAPH_* env is not set")
    resp = httpx.post(
        f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "https://graph.microsoft.com/.default",
        },
        timeout=15,
    )
    resp.raise_for_status()
    return str(resp.json()["access_token"])
