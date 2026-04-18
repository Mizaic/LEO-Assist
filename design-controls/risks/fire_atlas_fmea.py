"""
Bulk-fire 156 FMEA records to Atlas Design Controls MCP via HTTP.

Reads payload + state JSON, executes the 4-step FMEA workflow per record,
updates state after each successful step, continues on errors, prints
progress every 10 records.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import urllib.request
import urllib.error

ROOT = Path("/Users/robsmith/Documents/github/LEO-AI-CORE/design-controls/risks")
PAYLOAD_PATH = ROOT / "atlas_fmea_payloads.json"
STATE_PATH = ROOT / ".fire_state_v2.json"
MCP_CFG_PATH = Path("/Users/robsmith/.cursor/mcp.json")


def _load_mcp_config():
    cfg = json.loads(MCP_CFG_PATH.read_text())
    server = cfg["mcpServers"]["atlas-design-controls"]
    return server["url"], server["headers"]


MCP_URL, MCP_HEADERS = _load_mcp_config()


class McpError(Exception):
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


_COOKIES: dict = {}


def _build_request(payload: dict) -> urllib.request.Request:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(MCP_URL, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json, text/event-stream")
    req.add_header("User-Agent", "fire-atlas-fmea/1.0 (LEO-AI-CORE)")
    for k, v in MCP_HEADERS.items():
        req.add_header(k, v)
    if _COOKIES:
        cookie_hdr = "; ".join(f"{k}={v}" for k, v in _COOKIES.items())
        req.add_header("Cookie", cookie_hdr)
    return req


def _capture_cookies(resp) -> None:
    for cookie in resp.headers.get_all("Set-Cookie") or []:
        kv = cookie.split(";", 1)[0].strip()
        if "=" in kv:
            k, v = kv.split("=", 1)
            _COOKIES[k] = v


def _post(payload: dict, timeout: int = 60) -> dict:
    req = _build_request(payload)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            _capture_cookies(resp)
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        try:
            _capture_cookies(e)
        except Exception:
            pass
        raise McpError(f"HTTP {e.code}: {e.read().decode('utf-8', 'ignore')[:500]}")
    return _parse_response(raw)


def _parse_response(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("{"):
        return json.loads(raw)
    # SSE response: parse last "data:" line
    last_data = None
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            last_data = line[5:].strip()
    if last_data is None:
        raise McpError(f"Unparseable response: {raw[:300]}")
    return json.loads(last_data)


_REQ_ID = 0
_SESSION_ID = None


def _initialize() -> None:
    """MCP requires initialize handshake; capture mcp-session-id."""
    global _REQ_ID, _SESSION_ID, MCP_HEADERS
    _REQ_ID += 1
    payload = {
        "jsonrpc": "2.0",
        "id": _REQ_ID,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "fire_atlas_fmea", "version": "1.0"},
        },
    }
    req = _build_request(payload)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            _capture_cookies(resp)
            raw = resp.read().decode("utf-8")
            sid = resp.headers.get("mcp-session-id") or resp.headers.get("Mcp-Session-Id")
    except urllib.error.HTTPError as e:
        try:
            _capture_cookies(e)
        except Exception:
            pass
        raise
    if sid:
        _SESSION_ID = sid
        MCP_HEADERS = dict(MCP_HEADERS)
        MCP_HEADERS["mcp-session-id"] = sid
    notif = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    nreq = _build_request(notif)
    try:
        with urllib.request.urlopen(nreq, timeout=10) as r2:
            _capture_cookies(r2)
            r2.read()
    except Exception:
        pass


def _call_tool(name: str, arguments: dict, retries: int = 3) -> dict:
    global _REQ_ID
    last_err = None
    for attempt in range(retries):
        _REQ_ID += 1
        payload = {
            "jsonrpc": "2.0",
            "id": _REQ_ID,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
        try:
            resp = _post(payload, timeout=90)
        except (McpError, urllib.error.URLError, TimeoutError) as e:
            last_err = e
            time.sleep(2 * (attempt + 1))
            continue
        if "error" in resp:
            err = resp["error"]
            raise McpError(f"{name}: {err.get('code')} {err.get('message')}")
        result = resp.get("result", {})
        # MCP tool result has structuredContent (preferred) or content[].text
        if "structuredContent" in result:
            return result["structuredContent"]
        content = result.get("content", [])
        for item in content:
            if item.get("type") == "text":
                txt = item.get("text", "")
                try:
                    return json.loads(txt)
                except json.JSONDecodeError:
                    return {"_text": txt}
        return result
    raise McpError(f"{name}: exhausted retries: {last_err}")


def _load_state() -> dict:
    return json.loads(STATE_PATH.read_text())


def _save_state(state: dict) -> None:
    state["last_updated_at"] = _now_iso()
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(STATE_PATH)


def _ensure_entry(state: dict, master_id: str) -> dict:
    fired = state.setdefault("fired", {})
    entry = fired.setdefault(
        master_id,
        {
            "fmea_item_id": None,
            "risk_id": None,
            "risk_uuid": None,
            "step1_add": "pending",
            "step2_promote": "pending",
            "step3_update": "pending",
            "step4_product": "pending",
            "step5_un": "pending",
            "step6_di": "pending",
            "completed": False,
            "completed_at": None,
        },
    )
    return entry


def _bump(metrics: dict, key: str, n: int = 1) -> None:
    metrics[key] = metrics.get(key, 0) + n


def fire_record(record: dict, state: dict) -> bool:
    master_id = record["master_id"]
    entry = _ensure_entry(state, master_id)
    if entry.get("completed"):
        return True
    metrics = state["metrics"]
    failed_steps = []

    # Step 1: add_fmea_item
    if entry["step1_add"] != "ok":
        try:
            res = _call_tool("add_fmea_item", record["add"])
            entry["fmea_item_id"] = res.get("id")
            entry["step1_add"] = "ok"
            _bump(metrics, "fmea_items_created")
            _save_state(state)
        except Exception as e:
            entry["step1_add"] = f"fail: {str(e)[:200]}"
            entry["completed"] = False
            _bump(metrics, "errors")
            failed_steps.append("step1")
            _save_state(state)
            state.setdefault("failed", {})[master_id] = "step1: " + str(e)[:200]
            _save_state(state)
            return False

    fmea_item_id = entry["fmea_item_id"]

    # Step 2: promote
    if entry["step2_promote"] != "ok":
        try:
            res = _call_tool("promote_fmea_item_to_risk", {"item_id": fmea_item_id})
            entry["risk_id"] = res.get("dc_id") or res.get("risk_id")
            entry["risk_uuid"] = res.get("id")
            entry["step2_promote"] = "ok"
            _bump(metrics, "risks_promoted")
            _save_state(state)
        except Exception as e:
            entry["step2_promote"] = f"fail: {str(e)[:200]}"
            entry["completed"] = False
            _bump(metrics, "errors")
            state.setdefault("failed", {})[master_id] = "step2: " + str(e)[:200]
            _save_state(state)
            return False

    risk_id = entry["risk_id"]

    # Step 3: update_risk
    if entry["step3_update"] != "ok":
        args = {"risk_id": risk_id, **record["update"]}
        try:
            _call_tool("update_risk", args)
            entry["step3_update"] = "ok"
            _bump(metrics, "risks_updated")
            _save_state(state)
        except Exception as e:
            entry["step3_update"] = f"fail: {str(e)[:200]}"
            entry["completed"] = False
            _bump(metrics, "errors")
            state.setdefault("failed", {})[master_id] = "step3: " + str(e)[:200]
            _save_state(state)
            return False

    # Step 4: link Product
    if entry["step4_product"] != "ok":
        try:
            _call_tool(
                "link_design_controls",
                {
                    "source_ids": [record["product_id"]],
                    "target_ids": [risk_id],
                    "relationship": "HAS_RISK",
                },
            )
            entry["step4_product"] = "ok"
            _bump(metrics, "product_links_ok")
            _save_state(state)
        except Exception as e:
            entry["step4_product"] = f"fail: {str(e)[:200]}"
            _bump(metrics, "errors")
            failed_steps.append("step4")
            state.setdefault("failed", {})[master_id] = "step4: " + str(e)[:200]
            _save_state(state)

    # Step 5: link UNs (only if non-empty)
    if record.get("un_ids"):
        if entry["step5_un"] != "ok":
            try:
                _call_tool(
                    "link_design_controls",
                    {
                        "source_ids": record["un_ids"],
                        "target_ids": [risk_id],
                        "relationship": "HAS_RISK",
                    },
                )
                entry["step5_un"] = "ok"
                _bump(metrics, "un_links_ok")
                _save_state(state)
            except Exception as e:
                entry["step5_un"] = f"fail: {str(e)[:200]}"
                _bump(metrics, "errors")
                failed_steps.append("step5")
                state.setdefault("failed", {})[master_id] = "step5: " + str(e)[:200]
                _save_state(state)
    else:
        entry["step5_un"] = "skip"

    # Step 6: link DIs (only if non-empty)
    if record.get("di_ids"):
        if entry["step6_di"] != "ok":
            try:
                _call_tool(
                    "link_design_controls",
                    {
                        "source_ids": record["di_ids"],
                        "target_ids": [risk_id],
                        "relationship": "MITIGATES",
                    },
                )
                entry["step6_di"] = "ok"
                _bump(metrics, "di_links_ok")
                _save_state(state)
            except Exception as e:
                entry["step6_di"] = f"fail: {str(e)[:200]}"
                _bump(metrics, "errors")
                failed_steps.append("step6")
                state.setdefault("failed", {})[master_id] = "step6: " + str(e)[:200]
                _save_state(state)
    else:
        entry["step6_di"] = "skip"

    if not failed_steps:
        entry["completed"] = True
        entry["completed_at"] = _now_iso()
        _save_state(state)
        return True
    entry["completed"] = False
    _save_state(state)
    return False


def main() -> int:
    payload = json.loads(PAYLOAD_PATH.read_text())
    records = payload["records"]
    state = _load_state()
    if not state.get("started_at"):
        state["started_at"] = _now_iso()
        _save_state(state)

    print(f"Loaded {len(records)} records.")
    print(f"Initializing MCP session at {MCP_URL} ...")
    try:
        _initialize()
        print(f"MCP session id: {_SESSION_ID}")
    except Exception as e:
        print(f"Initialize failed (continuing anyway, server may be stateless): {e}")

    success_count = 0
    failure_ids = []

    for idx, rec in enumerate(records, start=1):
        master_id = rec["master_id"]
        record = {
            "master_id": master_id,
            "add": rec["add_fmea_item"],
            "update": rec["update_risk"],
            "product_id": rec["links"]["product_id"],
            "un_ids": rec["links"].get("un_ids", []),
            "di_ids": rec["links"].get("di_ids", []),
        }
        existing = state.get("fired", {}).get(master_id, {})
        if existing.get("completed"):
            success_count += 1
        else:
            ok = fire_record(record, state)
            if ok:
                success_count += 1
            else:
                failure_ids.append(master_id)
        if idx % 10 == 0:
            errors = state["metrics"].get("errors", 0)
            done = sum(
                1
                for v in state.get("fired", {}).values()
                if v.get("completed")
            )
            print(f"Progress: {done}/{len(records)} done, {errors} errors", flush=True)

    metrics = state["metrics"]
    print(
        "DONE: created={fmea_items_created} promoted={risks_promoted} "
        "updated={risks_updated} product_links={product_links_ok} "
        "un_links={un_links_ok} di_links={di_links_ok} errors={errors}".format(
            **metrics
        )
    )
    if failure_ids:
        print("Failed master_ids:")
        for mid in failure_ids:
            reason = state.get("failed", {}).get(mid, "(no reason captured)")
            print(f"  - {mid}: {reason}")
    print(f"State file: {STATE_PATH}")
    return 0 if not failure_ids else 1


if __name__ == "__main__":
    sys.exit(main())
