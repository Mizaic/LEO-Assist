#!/usr/bin/env python3
"""Deploy the LEO widget Cloudflare Worker proxy for Azure Static Website."""

from __future__ import annotations

import json
import os
import sys
import uuid
import urllib.error
import urllib.request
from pathlib import Path

API_ROOT = "https://api.cloudflare.com/client/v4"
WORKER_PATH = (
    Path(__file__).resolve().parents[1]
    / "infra/widget-cdn/cloudflare-worker/widget-proxy.js"
)


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        print(f"missing required env var: {name}", file=sys.stderr)
        sys.exit(1)
    return value


def _json_request(method: str, url: str, token: str, body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(f"Cloudflare API {exc.code} for {url}: {detail}", file=sys.stderr)
        raise


def _multipart_upload(url: str, token: str, metadata: dict, script: bytes) -> dict:
    boundary = f"----LeoWidget{uuid.uuid4().hex}"
    meta_bytes = json.dumps(metadata).encode("utf-8")
    parts = [
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="metadata"\r\n'
            f"Content-Type: application/json\r\n\r\n"
        ).encode("utf-8"),
        meta_bytes,
        b"\r\n",
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="widget-proxy.js"; '
            f'filename="widget-proxy.js"\r\n'
            f"Content-Type: application/javascript+module\r\n\r\n"
        ).encode("utf-8"),
        script,
        b"\r\n",
        f"--{boundary}--\r\n".encode("utf-8"),
    ]
    body = b"".join(parts)
    req = urllib.request.Request(
        url,
        data=body,
        method="PUT",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(f"Cloudflare API {exc.code} for {url}: {detail}", file=sys.stderr)
        raise


def _upload_script(
    token: str, account_id: str, script_name: str, origin_host: str
) -> None:
    metadata = {
        "main_module": "widget-proxy.js",
        "compatibility_date": "2024-01-01",
        "bindings": [
            {
                "type": "plain_text",
                "name": "ORIGIN_HOST",
                "text": origin_host,
            }
        ],
    }
    script = WORKER_PATH.read_bytes()
    url = f"{API_ROOT}/accounts/{account_id}/workers/scripts/{script_name}"
    payload = _multipart_upload(url, token, metadata, script)
    if not payload.get("success"):
        print(json.dumps(payload, indent=2), file=sys.stderr)
        sys.exit(1)


def _ensure_route(
    token: str, zone_id: str, script_name: str, public_host: str
) -> None:
    pattern = f"{public_host}/*"
    routes_url = f"{API_ROOT}/zones/{zone_id}/workers/routes"
    payload = _json_request("GET", routes_url, token)
    for route in payload.get("result", []):
        if route.get("pattern") == pattern:
            route_id = route["id"]
            if route.get("script") == script_name:
                return
            update_url = f"{routes_url}/{route_id}"
            _json_request(
                "PUT",
                update_url,
                token,
                {"pattern": pattern, "script": script_name},
            )
            return

    create_payload = _json_request(
        "POST",
        routes_url,
        token,
        {"pattern": pattern, "script": script_name},
    )
    if not create_payload.get("success"):
        print(json.dumps(create_payload, indent=2), file=sys.stderr)
        sys.exit(1)


def main() -> None:
    token = _require("CLOUDFLARE_API_TOKEN")
    account_id = _require("CLOUDFLARE_ACCOUNT_ID")
    zone_id = _require("CLOUDFLARE_ZONE_ID")
    public_host = _require("WIDGET_PUBLIC_HOST")
    origin_host = _require("AZURE_WIDGET_ORIGIN_HOST").rstrip("/")
    origin_host = origin_host.removeprefix("https://").removeprefix("http://")
    environment = os.environ.get("WIDGET_ENVIRONMENT", "dev").strip() or "dev"
    script_name = f"leo-widget-cdn-{environment}"

    _upload_script(token, account_id, script_name, origin_host)
    _ensure_route(token, zone_id, script_name, public_host)
    print(
        f"Deployed worker {script_name} for {public_host} -> {origin_host}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
