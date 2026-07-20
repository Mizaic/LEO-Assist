"""Focused tests for local guideline API safeguards."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

_API_ROOT = Path(__file__).parent.parent / "services" / "api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from app.routers.local_guidance import ImportRequest, import_guideline
from app.schemas.local_guideline import LocalGuidelineDraft, LocalGuidelineMetadata


@pytest.mark.asyncio
async def test_import_rejects_unverified_draft() -> None:
    """The API must not persist a draft flagged as likely incorrect."""
    request = ImportRequest(
        draft=LocalGuidelineDraft(
            metadata=LocalGuidelineMetadata(
                short_code="RHEUM-01", title="Rheumatology"
            ),
            likely_incorrect=True,
            verification_errors=["Unsupported recommendation."],
        )
    )

    with pytest.raises(HTTPException) as error:
        await import_guideline(request, scope=None)  # type: ignore[arg-type]

    assert error.value.status_code == 422
