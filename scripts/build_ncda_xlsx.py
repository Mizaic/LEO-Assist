"""Populate the NCDA audit spreadsheet from ``ncda_export.json``.

Sheet 1 ("NCDA Template") is filled with cancer-confirmed episodes only,
matching the original audit intent. A new sheet ("All 2WW Episodes") is
added showing every referral in the dataset (cancer/benign/unknown) so
the reader can see what fell outside the cancer-only view.

Inputs:
    data/ground_truth/ncda_export.json
    data/Cancer Diagnosis Audit.xlsx   (template)

Output:
    data/Cancer Diagnosis Audit - LEO AI.xlsx
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

REPO_ROOT = Path(__file__).resolve().parent.parent
EXPORT_PATH = REPO_ROOT / "data" / "ground_truth" / "ncda_export.json"
TEMPLATE_PATH = REPO_ROOT / "data" / "Cancer Diagnosis Audit.xlsx"
OUTPUT_PATH = REPO_ROOT / "data" / "Cancer Diagnosis Audit - LEO AI.xlsx"

log = logging.getLogger("ncda_xlsx")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

# Column mapping for the NCDA Template sheet (row 5 = headers, data row 7+).
TEMPLATE_FIRST_DATA_ROW = 7
COMORBIDITY_COLS = [10, 11, 12, 13, 14]
SYMPTOM_COLS = [17, 18, 19, 20, 21]
INVESTIGATION_COLS = [26, 27, 28]

COL_PATIENT_ID = 1
COL_NHS_NO = 2
COL_DOB = 3
COL_GENDER = 4
COL_WHERE_PRESENTED = 15
COL_DATE_PRESENTED = 16
COL_INV_ORDERED_FLAG = 25
COL_DATE_REFERRAL = 29
COL_CONSULT_COUNT = 30
COL_SAFETY_NETTING = 34
COL_REFERRAL_TYPE = 35
COL_FIRST_SEEN = 38
COL_DIAGNOSIS = 39
COL_DIAG_DATE = 40
COL_STAGE = 42

THIN = Side(border_style="thin", color="CCCCCC")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
HEADER_FONT = Font(bold=True, color="FFFFFF")
OUTCOME_FILLS = {
    "cancer": PatternFill("solid", fgColor="F4CCCC"),
    "benign": PatternFill("solid", fgColor="D9EAD3"),
    None: PatternFill("solid", fgColor="FFF2CC"),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _to_date(value: Any):
    """Parse ISO-8601 date to datetime.date (None on failure)."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except (TypeError, ValueError):
        return None


def _format_stage(ep: dict[str, Any]) -> str:
    """Return human-readable stage string (e.g. 'Stage IIIA (TNM)') or 'Unknown'."""
    group = ep.get("stage_at_diagnosis")
    if not group:
        return "Unknown"
    system = ep.get("stage_system") or ""
    label = f"Stage {group}" if not group.startswith("Stage") else group
    if system and system not in {"unknown", "TNM", "explicit_stage"}:
        return f"{label} ({system})"
    return label


def _formatted_gender(value: str | None) -> str:
    """Return the NCDA-capitalised gender category."""
    if not value:
        return "Unspecified (including transgender)"
    v = value.strip().lower()
    if v.startswith("m"):
        return "Male"
    if v.startswith("f"):
        return "Female"
    return "Unspecified (including transgender)"


def _write_list(ws: Worksheet, row: int, cols: list[int], values: list[str]) -> None:
    """Write up to len(cols) values into the specified columns."""
    for i, col in enumerate(cols):
        ws.cell(row=row, column=col, value=values[i] if i < len(values) else None)


def _clear_existing_data(ws: Worksheet, first_row: int = TEMPLATE_FIRST_DATA_ROW) -> None:
    """Blank out existing sample rows from the template (rows first_row..max_row)."""
    for r in range(first_row, ws.max_row + 1):
        for c in range(1, ws.max_column + 1):
            cell = ws.cell(row=r, column=c)
            if cell.value is not None:
                cell.value = None


# ---------------------------------------------------------------------------
# NCDA Template population (cancer-only)
# ---------------------------------------------------------------------------
def _write_template_row(ws: Worksheet, row: int, ep: dict[str, Any]) -> None:
    """Fill one NCDA Template row for a cancer-confirmed episode."""
    ws.cell(row=row, column=COL_PATIENT_ID, value=row - TEMPLATE_FIRST_DATA_ROW + 1)
    ws.cell(row=row, column=COL_NHS_NO, value=ep.get("patient_id"))
    ws.cell(row=row, column=COL_DOB, value=_to_date(ep.get("birth_date")))
    ws.cell(row=row, column=COL_GENDER, value=_formatted_gender(ep.get("gender")))
    _write_list(ws, row, COMORBIDITY_COLS, ep.get("comorbidities") or [])
    ws.cell(row=row, column=COL_WHERE_PRESENTED, value=ep.get("where_first_presented"))
    ws.cell(row=row, column=COL_DATE_PRESENTED, value=_to_date(ep.get("first_presentation")))
    _write_list(ws, row, SYMPTOM_COLS, ep.get("presenting_symptoms") or [])
    ws.cell(row=row, column=COL_INV_ORDERED_FLAG,
            value=ep.get("investigations_ordered_flag"))
    _write_list(ws, row, INVESTIGATION_COLS, ep.get("investigations_ordered") or [])
    ws.cell(row=row, column=COL_DATE_REFERRAL, value=_to_date(ep.get("referral")))
    ws.cell(row=row, column=COL_CONSULT_COUNT, value=ep.get("consultations_before_referral"))
    ws.cell(row=row, column=COL_SAFETY_NETTING, value=ep.get("safety_netting_documented"))
    ws.cell(row=row, column=COL_REFERRAL_TYPE, value=ep.get("referral_type_label"))
    ws.cell(row=row, column=COL_FIRST_SEEN, value=_to_date(ep.get("first_seen")))
    ws.cell(row=row, column=COL_DIAGNOSIS, value=ep.get("diagnosis_label"))
    ws.cell(row=row, column=COL_DIAG_DATE, value=_to_date(ep.get("diagnosis_date")))
    ws.cell(row=row, column=COL_STAGE, value=_format_stage(ep))


def populate_template_sheet(ws: Worksheet, episodes: list[dict[str, Any]]) -> int:
    """Write cancer-confirmed episodes into the template. Return row count.

    We do NOT write the practice-name header cells in row 3 because they are
    merged ranges in the supplied template. The per-row data carries each
    episode's practice context implicitly via patient_id -> practice mapping.
    """
    cancer_eps = [e for e in episodes if e.get("diagnosis_outcome") == "cancer"]
    _clear_existing_data(ws)
    for i, ep in enumerate(cancer_eps):
        _write_template_row(ws, TEMPLATE_FIRST_DATA_ROW + i, ep)
    log.info("Wrote %d cancer episodes into NCDA Template", len(cancer_eps))
    return len(cancer_eps)


# ---------------------------------------------------------------------------
# New sheet: All 2WW Episodes
# ---------------------------------------------------------------------------
ALL_EPISODES_HEADERS = [
    "Patient ID", "Episode #", "Cancer Pathway", "Referral Type", "DoB", "Gender",
    "Practice", "IMD Decile",
    "First Presentation", "Referral Date", "First Seen", "Diagnosis Date",
    "Treatment Start", "Last Encounter",
    "Diagnosis Outcome", "Diagnosis Label", "Stage at Diagnosis",
    "Presenting Symptoms", "Investigations Ordered", "Comorbidities",
    "Consultations Before Referral", "Safety Netting Documented",
    "Days: Presentation to Referral", "Days: Referral to First Seen",
    "Days: Presentation to Diagnosis", "Days: Referral to Diagnosis",
    "Expected Status",
]


def _style_all_episodes_header(ws: Worksheet) -> None:
    """Apply header styling and freeze the top row."""
    for c, header in enumerate(ALL_EPISODES_HEADERS, start=1):
        cell = ws.cell(row=1, column=c, value=header)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center",
                                   wrap_text=True)
        cell.border = BORDER
    ws.row_dimensions[1].height = 36
    ws.freeze_panes = "A2"


def _episode_row(patient_counts: dict[str, int], ep: dict[str, Any]) -> list[Any]:
    """Build a flat row of values for the All Episodes sheet."""
    pid = ep["patient_id"]
    patient_counts[pid] = patient_counts.get(pid, 0) + 1
    return [
        pid,
        patient_counts[pid],
        ep.get("cancer_type"),
        ep.get("referral_type"),
        _to_date(ep.get("birth_date")),
        _formatted_gender(ep.get("gender")),
        ep.get("practice_name"),
        ep.get("imd_decile"),
        _to_date(ep.get("first_presentation")),
        _to_date(ep.get("referral")),
        _to_date(ep.get("first_seen")),
        _to_date(ep.get("diagnosis_date")),
        _to_date(ep.get("treatment_start")),
        _to_date(ep.get("last_encounter")),
        ep.get("diagnosis_outcome") or "unknown",
        ep.get("diagnosis_label"),
        _format_stage(ep) if ep.get("diagnosis_outcome") == "cancer" else "",
        "; ".join(ep.get("presenting_symptoms") or []),
        "; ".join(ep.get("investigations_ordered") or []),
        "; ".join(c for c in (ep.get("comorbidities") or []) if c != "No co-morbidity"),
        ep.get("consultations_before_referral"),
        ep.get("safety_netting_documented"),
        ep.get("days_presentation_to_referral"),
        ep.get("days_referral_to_first_seen"),
        ep.get("days_presentation_to_diagnosis"),
        ep.get("days_referral_to_diagnosis"),
        ep.get("expected_status"),
    ]


def populate_all_episodes_sheet(ws: Worksheet, episodes: list[dict[str, Any]]) -> None:
    """Write every episode (cancer/benign/unknown) to the All Episodes sheet."""
    _style_all_episodes_header(ws)
    sorted_eps = sorted(
        episodes,
        key=lambda e: (
            e["patient_id"],
            _to_date(e.get("referral")) or _to_date(e.get("first_presentation"))
            or datetime.min.date(),
        ),
    )
    patient_counts: dict[str, int] = {}
    for r_idx, ep in enumerate(sorted_eps, start=2):
        row = _episode_row(patient_counts, ep)
        for c_idx, value in enumerate(row, start=1):
            cell = ws.cell(row=r_idx, column=c_idx, value=value)
            cell.border = BORDER
            cell.alignment = Alignment(vertical="top", wrap_text=True)
        outcome_fill = OUTCOME_FILLS.get(ep.get("diagnosis_outcome"))
        if outcome_fill is not None:
            ws.cell(row=r_idx, column=15).fill = outcome_fill
    _autosize_columns(ws)
    log.info("Wrote %d total episodes into All 2WW Episodes", len(sorted_eps))


def _autosize_columns(ws: Worksheet) -> None:
    """Apply best-effort column widths for readability."""
    widths = {
        1: 14, 2: 9, 3: 14, 4: 18, 5: 12, 6: 10, 7: 28, 8: 6,
        9: 14, 10: 14, 11: 14, 12: 14, 13: 14, 14: 14,
        15: 12, 16: 32, 17: 14,
        18: 40, 19: 40, 20: 30,
        21: 14, 22: 14, 23: 14, 24: 14, 25: 14, 26: 14, 27: 14,
    }
    for col, width in widths.items():
        ws.column_dimensions[get_column_letter(col)].width = width


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def _load_payload() -> dict[str, Any]:
    """Read the enriched export JSON (raises if missing)."""
    with EXPORT_PATH.open() as f:
        return json.load(f)


def build_xlsx() -> None:
    """Assemble the two-sheet NCDA audit workbook."""
    payload = _load_payload()
    episodes = payload["episodes"]
    wb = load_workbook(TEMPLATE_PATH)
    populate_template_sheet(wb["NCDA Template"], episodes)
    if "All 2WW Episodes" in wb.sheetnames:
        del wb["All 2WW Episodes"]
    ws_all = wb.create_sheet("All 2WW Episodes", index=1)
    populate_all_episodes_sheet(ws_all, episodes)
    wb.save(OUTPUT_PATH)
    log.info("Saved %s", OUTPUT_PATH)


if __name__ == "__main__":
    build_xlsx()
