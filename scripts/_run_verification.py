"""Run label verification directly (Gold Dataset Rebuild Step 5).

Equivalent to POST /training/labels/verify-all with mode=all, reset_pending=true
but invoked directly without needing the API server running.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env")

# Ensure TERMINOLOGY_API_URL is set (the verifier needs the terminology service)
term_url = os.getenv("TERMINOLOGY_API_URL", "")
if not term_url:
    print("WARNING: TERMINOLOGY_API_URL not set. Checking common ports...")
    import socket

    for port in [8001, 8002]:
        try:
            s = socket.create_connection(("localhost", port), timeout=2)
            s.close()
            os.environ["TERMINOLOGY_API_URL"] = f"http://localhost:{port}"
            print(f"  Found terminology service at localhost:{port}")
            break
        except (ConnectionRefusedError, OSError):
            pass
    else:
        print("  No local terminology service found. Verification will still run")
        print("  but terminology resolution may fall back to alt-term LLM suggestions.")

from services.api.app.services.label_verifier import (
    begin_job_with_mode,
    get_job_state,
    run_verification,
)

import argparse

parser = argparse.ArgumentParser()
parser.add_argument(
    "--mode", default="resume", choices=["all", "resume", "hitl_only", "re_extract"]
)
args = parser.parse_args()

print(f"Starting label verification (mode={args.mode}, reset_pending=false)...")
if args.mode == "resume":
    print("Resume mode: skipping already-verified labels")

started = begin_job_with_mode(run_mode=args.mode, reset_pending=False)
if not started:
    print("ERROR: Could not start verification job (may already be running)")
    sys.exit(1)

print("Verification running in foreground. This will take 30-60 minutes...")
print("Progress will be logged below.\n")

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

run_verification()

state = get_job_state()
print(f"\n{'='*60}")
print(f"Verification complete!")
print(f"  Status: {state.get('status')}")
print(f"  Total labels: {state.get('total')}")
print(f"  Done: {state.get('done')}")
print(f"  Agreements: {state.get('agreements')}")
print(f"  Disagreements: {state.get('disagreements')}")
print(f"  Auto-resolved: {state.get('auto_resolved')}")
print(f"  Pending review: {state.get('pending_review')}")
print(f"  Errors: {state.get('errors')}")
print(f"{'='*60}")
