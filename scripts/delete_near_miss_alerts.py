#!/usr/bin/env python3
"""Delete all CSSAlert nodes with status 'near_miss' from the patient graph.

Usage:
    python -m scripts.delete_near_miss_alerts
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

from libs.neo4j_client.client import PatientGraphClient

client = PatientGraphClient()

rows = client.run(
    "MATCH (a:CSSAlert) WHERE a.alert_type = 'near_miss' "
    "DETACH DELETE a RETURN count(a) AS deleted"
)
deleted = rows[0]["deleted"] if rows else 0
print(f"Deleted {deleted} near_miss CSSAlert nodes")

client.close()
