"""Mail router — read and reply to the leo.support inbox.

All endpoints require platform admin. Uses the Graph mail service which
authenticates via client credentials (app-level token).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.deps import require_admin
from app.services import mail as mail_svc
from libs.auth.org_scope import CallerScope

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mail", tags=["mail"])


class ReplyBody(BaseModel):
    text: str


@router.get("/messages")
async def list_messages(
    skip: int = 0,
    top: int = 50,
    _scope: CallerScope = Depends(require_admin),
) -> list[dict[str, Any]]:
    """List messages in the leo.support inbox, newest first."""
    try:
        return mail_svc.list_messages(skip=skip, top=top)
    except Exception as exc:
        logger.error("Failed to list messages: %s", exc)
        raise HTTPException(502, "Could not reach the mail service. Try again shortly.")


@router.get("/messages/{msg_id}")
async def get_message(
    msg_id: str,
    _scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Get a single message with its full HTML body. Marks it as read."""
    try:
        result = mail_svc.get_message(msg_id)
        try:
            mail_svc.mark_read(msg_id)
        except Exception:
            pass
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to get message %s: %s", msg_id, exc)
        raise HTTPException(502, "Could not load this message.")


@router.post("/messages/{msg_id}/reply")
async def reply_to_message(
    msg_id: str,
    body: ReplyBody,
    _scope: CallerScope = Depends(require_admin),
) -> dict[str, str]:
    """Send a reply from leo.support to the sender of a message."""
    if not body.text.strip():
        raise HTTPException(400, "Reply text cannot be empty.")
    try:
        mail_svc.reply_to_message(msg_id, body.text.strip())
        return {"status": "sent"}
    except Exception as exc:
        logger.error("Failed to reply to message %s: %s", msg_id, exc)
        raise HTTPException(502, "Could not send the reply.")


@router.delete("/messages/{msg_id}")
async def delete_message(
    msg_id: str,
    _scope: CallerScope = Depends(require_admin),
) -> dict[str, str]:
    """Move a message to Deleted Items."""
    try:
        mail_svc.delete_message(msg_id)
        return {"status": "deleted"}
    except Exception as exc:
        logger.error("Failed to delete message %s: %s", msg_id, exc)
        raise HTTPException(502, "Could not delete this message.")
