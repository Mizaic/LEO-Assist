#!/usr/bin/env python3
"""Ensure Cloudflare rewrites the origin Host header for the widget CDN.

Azure Storage Static Website rejects proxied requests unless the origin
Host header matches the storage account web endpoint hostname.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

RULE_REF = "leo_widget_azure_origin_host"
RULE_DESC = "LEO widget: rewrite origin Host for Azure Static Website"
API_ROOT = "https://api.cloudflare.com/client/v4"


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        print(f"missing required env var: {name}", file=sys.stderr)
        sys.exit(1)
    return value


def _request(method: str, url: str, token: str, body: dict | None = None) -> dict:
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
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _build_rule(public_host: str, origin_host: str) -> dict:
    return {
        "ref": RULE_REF,
        "description": RULE_DESC,
        "expression": f'(http.host eq "{public_host}")',
        "action": "route",
        "action_parameters": {
            "host_header": origin_host,
            "origin": {"host": origin_host},
        },
    }


def _merge_rules(existing: list[dict], rule: dict) -> list[dict]:
    kept = [item for item in existing if item.get("ref") != RULE_REF]
    return kept + [rule]


def main() -> None:
    token = _require("CLOUDFLARE_API_TOKEN")
    zone_id = _require("CLOUDFLARE_ZONE_ID")
    public_host = _require("WIDGET_PUBLIC_HOST")
    origin_host = _require("AZURE_WIDGET_ORIGIN_HOST").rstrip("/")
    if origin_host.startswith("https://"):
        origin_host = origin_host.removeprefix("https://")
    if origin_host.startswith("http://"):
        origin_host = origin_host.removeprefix("http://")

    rule = _build_rule(public_host, origin_host)
    entrypoint_url = (
        f"{API_ROOT}/zones/{zone_id}/rulesets/phases/http_request_origin/entrypoint"
    )

    try:
        payload = _request("GET", entrypoint_url, token)
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
        create_url = f"{API_ROOT}/zones/{zone_id}/rulesets"
        payload = _request(
            "POST",
            create_url,
            token,
            {
                "name": "LEO widget origin rules",
                "kind": "zone",
                "phase": "http_request_origin",
                "rules": [rule],
            },
        )
    else:
        ruleset = payload["result"]
        rules = _merge_rules(ruleset.get("rules", []), rule)
        update_url = f"{API_ROOT}/zones/{zone_id}/rulesets/{ruleset['id']}"
        payload = _request("PUT", update_url, token, {"rules": rules})

    if not payload.get("success"):
        print(json.dumps(payload, indent=2), file=sys.stderr)
        sys.exit(1)

    print(
        f"Applied origin Host override: {public_host} -> {origin_host}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
