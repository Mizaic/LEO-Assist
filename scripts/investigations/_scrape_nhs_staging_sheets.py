from __future__ import annotations

import json
import re
from io import StringIO
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests

BASE_URL = "https://digital.nhs.uk"
INDEX_URL = f"{BASE_URL}/ndrs/data/cancer-data-training-materials/staging-sheets"
OUT_DIR = Path("configs/staging_rules")
MANIFEST_PATH = OUT_DIR / "_manifest.json"
TIMEOUT_SECONDS = 45

_UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

_ROMAN_TO_INT = {
    "0": 0,
    "I": 1,
    "II": 2,
    "III": 3,
    "IV": 4,
    "V": 5,
    "VI": 6,
}

_EARLY_LATE_DEFAULT = {
    "0": "early",
    "I": "early",
    "IA": "early",
    "IB": "early",
    "IC": "early",
    "II": "early",
    "IIA": "early",
    "IIB": "early",
    "IIC": "early",
    "III": "late",
    "IIIA": "late",
    "IIIB": "late",
    "IIIC": "late",
    "IV": "late",
    "IVA": "late",
    "IVB": "late",
    "IVC": "late",
}


def _slug_from_url(url: str) -> str:
    return urlparse(url).path.rstrip("/").split("/")[-1]


def _normalise_stage_group(raw: str) -> str:
    text = re.sub(r"\s+", " ", str(raw or "")).strip()
    text = re.sub(r"(?i)^stage\s*", "", text).strip()
    return text.upper()


def _stage_numeric(group: str) -> int | None:
    clean = re.sub(r"[^A-Z0-9]", "", group.upper())
    if not clean:
        return None
    for key in ("IV", "III", "II", "I", "0", "V", "VI"):
        if clean.startswith(key):
            return _ROMAN_TO_INT.get(key)
    if clean and clean[0].isdigit():
        return int(clean[0])
    return None


def _first_col(cols: list[str], candidates: tuple[str, ...]) -> str | None:
    lower = {c.lower(): c for c in cols}
    for col in cols:
        key = col.lower()
        if any(token in key for token in candidates):
            return lower[key]
    return None


def _is_tnm_table(df: pd.DataFrame) -> bool:
    cols = [str(c).strip() for c in df.columns]
    c_t = _first_col(cols, ("t stage", "t category", " t "))
    c_n = _first_col(cols, ("n stage", "n category", " n "))
    c_m = _first_col(cols, ("m stage", "m category", " m "))
    c_stage = _first_col(cols, ("stage", "stage group"))
    return bool(c_t and c_n and c_m and c_stage)


def _extract_tnm_rules(df: pd.DataFrame) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    cols = [str(c).strip() for c in df.columns]
    c_t = _first_col(cols, ("t stage", "t category", " t "))
    c_n = _first_col(cols, ("n stage", "n category", " n "))
    c_m = _first_col(cols, ("m stage", "m category", " m "))
    c_stage = _first_col(cols, ("stage", "stage group"))
    if not (c_t and c_n and c_m and c_stage):
        return rules

    for _, row in df.iterrows():
        t_val = str(row.get(c_t, "")).strip().upper()
        n_val = str(row.get(c_n, "")).strip().upper()
        m_val = str(row.get(c_m, "")).strip().upper()
        sg = _normalise_stage_group(str(row.get(c_stage, "")).strip())
        if not (t_val and n_val and m_val and sg):
            continue
        rules.append(
            {
                "t": t_val,
                "n": n_val,
                "m": m_val,
                "stage_group": sg,
                "stage_numeric": _stage_numeric(sg),
            }
        )
    return rules


def _fetch_text(url: str) -> str:
    res = requests.get(url, headers=_UA, timeout=TIMEOUT_SECONDS)
    res.raise_for_status()
    return res.text


def _discover_sheet_urls(index_html: str) -> list[str]:
    links = re.findall(
        r'href="(/ndrs/data/cancer-data-training-materials/staging-sheets/[^"#?]+)"',
        index_html,
    )
    urls = {
        urljoin(BASE_URL, path)
        for path in links
        if path.rstrip("/")
        != "/ndrs/data/cancer-data-training-materials/staging-sheets"
    }
    # Defensive include in case index rendering changes.
    urls.add(INDEX_URL)
    return sorted(u for u in urls if u != INDEX_URL)


def _extract_site_title(html: str, slug: str) -> str:
    m = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if not m:
        return slug.replace("-", " ").title()
    title = re.sub(r"\s+", " ", m.group(1)).strip()
    title = title.replace(" - NHS England Digital", "")
    return title


def _parse_site(url: str, html: str) -> dict[str, Any]:
    slug = _slug_from_url(url)
    tables = pd.read_html(StringIO(html))
    rules: list[dict[str, Any]] = []
    for df in tables:
        if _is_tnm_table(df):
            rules.extend(_extract_tnm_rules(df))
    dedup: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for r in rules:
        dedup[(r["t"], r["n"], r["m"], r["stage_group"])] = r

    payload = {
        "site_name": _extract_site_title(html, slug),
        "site_slug": slug,
        "source_url": url,
        "staging_edition": "UICC 8th (assumed unless page states otherwise)",
        "tnm_to_stage_group": list(dedup.values()),
        "stage_group_to_early_late": _EARLY_LATE_DEFAULT,
    }
    return payload


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    index_html = _fetch_text(INDEX_URL)
    urls = _discover_sheet_urls(index_html)

    written: list[dict[str, Any]] = []
    for url in urls:
        slug = _slug_from_url(url)
        try:
            html = _fetch_text(url)
            payload = _parse_site(url, html)
            out = OUT_DIR / f"{slug}.json"
            out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            written.append(
                {
                    "site_slug": slug,
                    "source_url": url,
                    "rule_count": len(payload["tnm_to_stage_group"]),
                    "has_tnm_rules": bool(payload["tnm_to_stage_group"]),
                }
            )
            print(f"OK  {slug:40} rules={len(payload['tnm_to_stage_group'])}")
        except Exception as exc:  # noqa: BLE001
            print(f"ERR {slug:40} {exc}")
            written.append(
                {
                    "site_slug": slug,
                    "source_url": url,
                    "rule_count": 0,
                    "has_tnm_rules": False,
                    "error": str(exc),
                }
            )

    manifest = {
        "index_url": INDEX_URL,
        "site_count": len(urls),
        "generated_files": len([x for x in written if "error" not in x]),
        "sites": written,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Wrote {MANIFEST_PATH} with {len(urls)} sites")


if __name__ == "__main__":
    main()
