"""UK Index of Multiple Deprivation (IMD) data retrieval.

Ported from auditor_2 agent/tools/deprivation_data_retriever.py.
Retrieves IMD 2019 data for UK postcodes and stores on Patient nodes.
"""

from __future__ import annotations

import csv
import io
import logging
import re
import time
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, HTTPException, Query

from libs.neo4j_client.client import PatientGraphClient

router = APIRouter()
logger = logging.getLogger(__name__)

_POSTCODE_RE = re.compile(r"^[A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2}$", re.IGNORECASE)
_IMD_UPLOAD_URL = "https://imd-by-postcode.opendatacommunities.org/imd/2019/ajax/upload"


@router.get("/imd/{postcode}")
async def get_imd_data(postcode: str):
    """Retrieve IMD data for a UK postcode."""
    clean = postcode.strip().upper()
    if not _POSTCODE_RE.match(clean):
        raise HTTPException(400, f"Invalid UK postcode: {postcode}")

    data = await _retrieve_imd(clean)
    if not data:
        raise HTTPException(404, f"No IMD data found for {clean}")
    return data


@router.post("/imd/enrich")
async def enrich_patient_imd(
    patient_id: str = Query(...),
    postcode: str = Query(...),
):
    """Retrieve IMD data and store it on the Patient node."""
    clean = postcode.strip().upper()
    if not _POSTCODE_RE.match(clean):
        raise HTTPException(400, f"Invalid UK postcode: {postcode}")

    data = await _retrieve_imd(clean)
    if not data:
        raise HTTPException(404, f"No IMD data found for {clean}")

    client = PatientGraphClient()
    try:
        client.run(
            "MATCH (p:Patient) WHERE toString(p.id) = $pid "
            "SET p.imd_decile = $decile, p.imd_rank = $rank, p.postcode = $pc",
            pid=patient_id,
            decile=data.get("Index of Multiple Deprivation Decile"),
            rank=data.get("Index of Multiple Deprivation Rank"),
            pc=clean,
        )
    finally:
        client.close()

    return {"patient_id": patient_id, "imd": data}


async def _retrieve_imd(postcode: str) -> Optional[Dict[str, Any]]:
    """Upload postcode to IMD service, poll for result, parse CSV."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                _IMD_UPLOAD_URL,
                data={"postcodes": postcode},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if resp.status_code != 200:
                return None

            result = resp.json()
            poll_path = result.get("poll-path")
            if not poll_path:
                return None

            base_url = "https://imd-by-postcode.opendatacommunities.org"
            for _ in range(20):
                time.sleep(0.5)
                poll_resp = await client.get(f"{base_url}{poll_path}")
                poll_data = poll_resp.json()
                if poll_data.get("completed"):
                    csv_path = poll_data.get("path")
                    if csv_path:
                        csv_resp = await client.get(f"{base_url}{csv_path}")
                        return _parse_csv(csv_resp.text)
                    break

    except Exception:
        logger.warning("IMD retrieval failed for %s", postcode, exc_info=True)
    return None


def _parse_csv(csv_text: str) -> Optional[Dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(csv_text))
    for row in reader:
        return dict(row)
    return None
