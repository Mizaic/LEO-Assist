"""Rewrite Atlas risks in plain English (reading age 11) for clinicians.

For each risk in atlas_fmea_payloads.json, calls Claude Sonnet via Bedrock to
produce DCB0129/ISO 14971 compliant text:

    - title                       (1 sentence, plain English)
    - hazard_description          (1-2 sentences)
    - hazardous_situation         (1-2 sentences)
    - harm_description            (1-2 sentences)
    - mitigation_plan_description (3-5 sentences naming the linked controls,
                                   roles, and how effectiveness is measured)

Linked design-input (DI) titles are passed to the model as the source of
truth for the mitigation plan -- the model must NOT invent controls.

Outputs:

    - atlas_fmea_payloads_v2.json    (drop-in replacement for the firer)
    - rewrite_diff_report.csv        (old vs new text for spot-checking)

Usage:

    python3 rewrite_risks_plain_english.py --sample 3       # dry-run 3 records
    python3 rewrite_risks_plain_english.py                   # full 156
    python3 rewrite_risks_plain_english.py --resume          # skip already done
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from libs.llm_client.factory import create_llm  # noqa: E402
from libs.llm_client.prompt_safety import INJECTION_GUARD  # noqa: E402

HERE = Path(__file__).parent
PAYLOAD_IN = HERE / "atlas_fmea_payloads.json"
PAYLOAD_OUT = HERE / "atlas_fmea_payloads_v2.json"
DIFF_CSV = HERE / "rewrite_diff_report.csv"
ATLAS_INDEX = HERE / "_atlas_index.json"


SYSTEM_PROMPT = INJECTION_GUARD + """You are a clinical safety officer rewriting
risk descriptions for an NHS clinical safety case under DCB0129 and ISO 14971.

Your audience is a clinician (GP, nurse, pharmacist) reading at UK reading age
11. They understand routine clinical terms (patient, diagnosis, medication, GP,
pathway) but are NOT software engineers and do NOT know IT or AI jargon.

Your job: rewrite each risk so a busy clinician can read it in under 30 seconds
and understand exactly what could go wrong, what could happen to the patient,
and what stops it from happening.

Style rules (apply to EVERY field):

1. Short sentences. 15-20 words max. One idea per sentence.
2. Active voice. "The system shows the doctor a warning" not "A warning is
   shown to the doctor".
3. Plain English. Replace IT/AI jargon:
   - "NLP" / "natural language processing" -> "the AI tool that reads notes"
   - "SNOMED CT code" / "concept ID" -> "clinical code"
   - "extraction" -> "pulling information from notes"
   - "context engine" / "assertion" -> "the AI tool that decides if something
     is present, absent, or possible"
   - "post-processing" / "pipeline" -> "the AI workflow"
   - "ConText" / "ontology" / "taxonomy" -> "the rules the AI follows"
   - "API" / "endpoint" / "service" -> "system component"
   - "writeback" -> "saving changes back into the patient record"
   - "training data" -> "examples used to teach the AI"
   - "gold standard" -> "examples checked by an expert"
   - "F1" / "precision" / "recall" -> "accuracy"
   - "ALARP" / "RPN" -> keep as-is (clinicians know these)
4. Clinical terms a clinician already knows are fine (hypertension is OK, but
   on FIRST mention add a plain version in brackets if it might be ambiguous).
5. UK English. Use "medicine" not "medication" where natural. "Doctor" or
   "clinician" not "physician". "Recognise" not "recognize".

DCB0129/ISO 14971 mitigation plan rules:

- Name each control in plain words, citing the linked design-input ID at the
  end of its sentence in brackets.
- For EACH control, say: what it does, who runs it, how often.
- End with one sentence on how the safety team checks the controls are working
  (e.g. "The clinical safety committee reviews this every quarter.").
- Do NOT invent controls. Use ONLY the linked design inputs (DIs) provided.
- If fewer than 2 linked DIs are listed, still produce a mitigation plan and
  note "Additional controls are being identified" at the end.

Severity / probability are already set numerically -- do NOT restate them.

Return a single JSON object with EXACTLY these keys (no extra keys, no prose
outside the JSON):

    {
      "title": "...",
      "hazard_description": "...",
      "hazardous_situation": "...",
      "harm_description": "...",
      "mitigation_plan_description": "..."
    }

All values are plain UTF-8 strings. No markdown, no bullets, no headings.
"""


@dataclass
class DICatalogue:
    by_dc_id: dict[str, str]

    @classmethod
    def load(cls, path: Path) -> "DICatalogue":
        data = json.loads(path.read_text())
        return cls(by_dc_id={d["dcId"]: d["title"] for d in data["design_inputs"]})

    def titles_for(self, dc_ids: list[str]) -> list[tuple[str, str]]:
        out = []
        for dc_id in dc_ids:
            title = self.by_dc_id.get(dc_id)
            if title:
                out.append((dc_id, title))
        return out


def _build_user_message(record: dict, di_pairs: list[tuple[str, str]]) -> str:
    upd = record["update_risk"]
    di_lines = (
        "\n".join(f"  - {dc_id}: {title}" for dc_id, title in di_pairs)
        if di_pairs
        else "  (none provided)"
    )
    return json.dumps(
        {
            "current_text": {
                "title": upd.get("title", ""),
                "hazard_description": upd.get("hazard_description", ""),
                "hazardous_situation": upd.get("hazardous_situation", ""),
                "harm_description": upd.get("harm_description", ""),
                "mitigation_plan_description": upd.get(
                    "mitigation_plan_description", ""
                ),
            },
            "scoring": {
                "initial_severity": upd.get("initial_severity"),
                "initial_probability": upd.get("initial_probability"),
                "harm_severity": upd.get("harm_severity"),
                "safety_class": upd.get("safety_class"),
            },
            "linked_controls_authoritative_list": di_lines,
            "instruction": (
                "Rewrite the five text fields per the system rules. Return JSON "
                "only. Do not change any score, status, or DI ID."
            ),
        },
        indent=2,
    )


def _parse_response(text: str) -> dict[str, str] | None:
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].lstrip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        obj = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    required = {
        "title",
        "hazard_description",
        "hazardous_situation",
        "harm_description",
        "mitigation_plan_description",
    }
    if not required.issubset(obj.keys()):
        return None
    return {k: str(obj[k]).strip() for k in required}


def rewrite_one(client, record: dict, di_pairs: list[tuple[str, str]],
                max_attempts: int = 3) -> dict[str, str] | None:
    user_msg = _build_user_message(record, di_pairs)
    last_err: str | None = None
    for attempt in range(max_attempts):
        try:
            resp = client.converse(
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_msg}],
                max_tokens=1500,
                temperature=0.2,
                json_mode=True,
            )
            parsed = _parse_response(resp.text)
            if parsed:
                return parsed
            last_err = f"unparseable response: {resp.text[:200]}"
        except Exception as e:  # noqa: BLE001
            last_err = str(e)[:200]
        time.sleep(1.5 * (attempt + 1))
    print(f"  WARN rewrite failed after {max_attempts} attempts: {last_err}",
          flush=True)
    return None


def _apply_rewrite(record: dict, rewrite: dict[str, str]) -> dict:
    new = json.loads(json.dumps(record))
    new["update_risk"]["title"] = rewrite["title"]
    new["update_risk"]["hazard_description"] = rewrite["hazard_description"]
    new["update_risk"]["hazardous_situation"] = rewrite["hazardous_situation"]
    new["update_risk"]["harm_description"] = rewrite["harm_description"]
    new["update_risk"]["mitigation_measures_detail"] = rewrite[
        "mitigation_plan_description"
    ]
    new["update_risk"].pop("mitigation_plan_description", None)
    new["rewrite_provenance"] = {
        "rewriter": "claude-sonnet-4-6 via Bedrock",
        "rewriter_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "reading_age_target": 11,
        "compliance": ["DCB0129", "ISO 14971"],
    }
    return new


def _diff_row(record_old: dict, record_new: dict) -> list[Any]:
    o = record_old["update_risk"]
    n = record_new["update_risk"]
    return [
        record_old["master_id"],
        o.get("title", ""),
        n.get("title", ""),
        o.get("hazard_description", ""),
        n.get("hazard_description", ""),
        o.get("hazardous_situation", ""),
        n.get("hazardous_situation", ""),
        o.get("harm_description", ""),
        n.get("harm_description", ""),
        o.get("mitigation_plan_description", ""),
        n.get("mitigation_plan_description", ""),
    ]


def _write_diff_csv(rows: list[list[Any]]) -> None:
    with DIFF_CSV.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "master_id",
            "title_old", "title_new",
            "hazard_old", "hazard_new",
            "hazardous_situation_old", "hazardous_situation_new",
            "harm_old", "harm_new",
            "mitigation_old", "mitigation_new",
        ])
        for row in rows:
            w.writerow(row)


def _load_resume(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text())
    return {}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, default=0,
                        help="Process only first N records (0 = all)")
    parser.add_argument("--resume", action="store_true",
                        help="Skip records already in the v2 output file")
    parser.add_argument("--ids", type=str, default="",
                        help="Comma-sep master_ids to process (overrides --sample)")
    args = parser.parse_args()

    payload = json.loads(PAYLOAD_IN.read_text())
    records = payload["records"]
    catalogue = DICatalogue.load(ATLAS_INDEX)

    existing_v2 = {}
    if args.resume and PAYLOAD_OUT.exists():
        existing = json.loads(PAYLOAD_OUT.read_text())
        existing_v2 = {r["master_id"]: r for r in existing.get("records", [])}
        print(f"Resume: {len(existing_v2)} records already rewritten.")

    if args.ids:
        wanted = {x.strip() for x in args.ids.split(",") if x.strip()}
        records = [r for r in records if r["master_id"] in wanted]
    elif args.sample > 0:
        records = records[: args.sample]

    workers = int(os.getenv("REWRITE_WORKERS", "8"))
    print(f"Rewriting {len(records)} records via Bedrock Claude Sonnet 4.6 "
          f"(workers={workers})...")
    client = create_llm(provider="aws", tier="big")

    results: dict[str, dict | None] = {}
    failures: list[str] = []
    lock = Lock()
    completed = 0

    def _worker(rec: dict) -> tuple[str, dict | None, dict]:
        mid = rec["master_id"]
        if mid in existing_v2:
            return mid, None, rec
        di_pairs = catalogue.titles_for(rec["links"]["di_ids"])
        rewrite = rewrite_one(client, rec, di_pairs)
        return mid, rewrite, rec

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(_worker, rec) for rec in records]
        for fut in as_completed(futs):
            mid, rewrite, rec = fut.result()
            with lock:
                if mid in existing_v2:
                    results[mid] = existing_v2[mid]
                elif rewrite is None:
                    failures.append(mid)
                    results[mid] = rec
                else:
                    results[mid] = _apply_rewrite(rec, rewrite)
                completed += 1
                if completed % 10 == 0 or completed == len(records):
                    print(f"  Progress: {completed}/{len(records)}  "
                          f"failures={len(failures)}", flush=True)
                    ordered = [results[r["master_id"]] for r in records
                               if r["master_id"] in results]
                    _write_intermediate(payload, ordered, records, existing_v2)

    out_records = [results[r["master_id"]] for r in records]
    diff_rows: list[list[Any]] = []
    for r in records:
        new = results[r["master_id"]]
        if new.get("rewrite_provenance") and r["master_id"] not in existing_v2:
            diff_rows.append(_diff_row(r, new))

    _write_intermediate(payload, out_records, records, existing_v2)
    _write_diff_csv(diff_rows)

    print(f"\nDone. Output: {PAYLOAD_OUT.name}  Diff: {DIFF_CSV.name}")
    if failures:
        print(f"Failures ({len(failures)}): {failures}")
    return 0


def _write_intermediate(payload: dict, out_records: list[dict],
                        processed: list[dict], existing_v2: dict) -> None:
    """Merge processed records with any others kept from prior v2 file."""
    processed_ids = {r["master_id"] for r in processed}
    final = list(out_records)
    for mid, rec in existing_v2.items():
        if mid not in processed_ids and mid not in {r["master_id"] for r in final}:
            final.append(rec)
    payload_v2 = {
        "workshop_id": payload.get("workshop_id"),
        "product_id": payload.get("product_id"),
        "scoring_note": payload.get("scoring_note"),
        "rewrite_note": (
            "Text fields rewritten by Claude Sonnet 4.6 to UK reading age 11 for "
            "clinician audience under DCB0129 / ISO 14971. Mitigation plans cite "
            "the linked Atlas DI IDs explicitly. Scores, IDs, and links are "
            "unchanged from atlas_fmea_payloads.json."
        ),
        "records": final,
    }
    PAYLOAD_OUT.write_text(json.dumps(payload_v2, indent=2))


if __name__ == "__main__":
    sys.exit(main())
