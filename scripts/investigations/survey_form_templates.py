"""Read-only survey: how do the form layout rules behave across every template?

Converts each referral proforma in templates/ to text and reports, per form:
  lines        total non-blank lines
  marked       lines or cells the rules suppress
  boxes        lines carrying a checkbox
  mixed        lines where free text follows the last checkbox
  lost_words   words deleted by normalisation (must always be 0)

Makes no writes and calls no LLM.

Usage:
    .venv/bin/python scripts/investigations/survey_form_templates.py
"""

from __future__ import annotations

import pathlib
import re
import sys
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from libs.ner.form_checkbox_normalizer import (  # noqa: E402
    extractable_clinical_lines,
)
from libs.ner.form_layout_rules import (  # noqa: E402
    NON_EXTRACTABLE_MARKER,
    apply_form_layout_rules,
    has_trailing_prose,
)

TEMPLATES = ROOT / "templates"
_BOX = re.compile(r"\[\s*\]|\[(?:X|x)\]|\(\s*\)|\((?:X|x)\)")
_WORD = re.compile(r"[A-Za-z0-9.]{3,}")
_XML_TAG = re.compile(r"<[^>]+>")


def _docx_text(path: pathlib.Path) -> str:
    """Plain text from a .docx / .dotm, including table cells."""
    with zipfile.ZipFile(path) as zf:
        name = next(
            (n for n in ("word/document.xml",) if n in zf.namelist()),
            None,
        )
        if name is None:
            return ""
        xml = zf.read(name).decode("utf-8", errors="replace")
    # Word stores tickboxes three ways: a legacy form field, a content
    # control, or a literal ballot-box glyph. Render all three as brackets
    # so the survey sees what a text export would show.
    xml = re.sub(
        r"<w:checkBox>(?:(?!</w:checkBox>).)*?"
        r"<w:(?:checked|default)[^>]*w:val=\"(?:1|true)\"[^>]*/>"
        r"(?:(?!</w:checkBox>).)*?</w:checkBox>",
        "[X]",
        xml,
        flags=re.DOTALL,
    )
    xml = re.sub(r"<w:checkBox>.*?</w:checkBox>", "[ ]", xml, flags=re.DOTALL)
    # Field instruction runs ("FORMCHECKBOX") are Word plumbing, never text.
    xml = re.sub(r"<w:instrText[^>]*>.*?</w:instrText>", "", xml, flags=re.DOTALL)
    xml = re.sub(r"</w:p>", "\n", xml)
    xml = re.sub(r"</w:tc>", " | ", xml)
    xml = re.sub(r"<w:tab[^>]*/>", " ", xml)
    xml = xml.replace("\u2610", "[ ]").replace("\u2612", "[X]")
    xml = xml.replace("\u2611", "[X]")
    return _XML_TAG.sub("", xml)


def _words(text: str) -> set[str]:
    marker = NON_EXTRACTABLE_MARKER.strip("[]").lower()
    return {w for w in _WORD.findall(text.lower()) if w != marker}


SENTINEL = "Two open vulval sores noted on examination"


def _sentinel_survivors(lines: list[str]) -> tuple[int, int]:
    """Append a clinical sentence to each checkbox line; count survivors.

    A blank proforma has no narrative, so recall cannot be measured from it
    directly. Injecting a known sentence onto the risky lines shows whether a
    GP's free text would survive normalisation on a form we never taught.
    """
    probed = tried = 0
    for index, line in enumerate(lines):
        if not _BOX.search(line):
            continue
        tried += 1
        spiked = list(lines)
        spiked[index] = f"{line.rstrip()} {SENTINEL}"
        kept = " ".join(extractable_clinical_lines("\n".join(spiked)))
        if "vulval sores" in kept.lower():
            probed += 1
    return probed, tried


def _survey(path: pathlib.Path) -> dict[str, int] | None:
    if path.suffix.lower() not in {".docx", ".dotm"}:
        return None
    text = _docx_text(path)
    if not text.strip():
        return None

    lines = [ln for ln in text.splitlines() if ln.strip()]
    boxes = [ln for ln in lines if _BOX.search(ln)]
    mixed = [ln for ln in boxes if has_trailing_prose(ln)]

    lost = 0
    for line in lines:
        lost += len(_words(line) - _words(apply_form_layout_rules(line)))

    kept = extractable_clinical_lines(text)
    survived, probed = _sentinel_survivors(lines)
    return {
        "lines": len(lines),
        "boxes": len(boxes),
        "mixed": len(mixed),
        "kept_lines": len(kept),
        "survived": survived,
        "probed": probed,
        "lost_words": lost,
    }


def main() -> None:
    header = (
        f"{'form':<52}{'lines':>7}{'boxes':>7}{'mixed':>7}"
        f"{'kept':>7}{'survive':>9}{'lost':>6}"
    )
    print(header)
    print("-" * len(header))
    totals = {"mixed": 0, "lost": 0, "survived": 0, "probed": 0}
    forms = 0
    for path in sorted(TEMPLATES.iterdir()):
        stats = _survey(path)
        if stats is None:
            continue
        forms += 1
        totals["mixed"] += stats["mixed"]
        totals["lost"] += stats["lost_words"]
        totals["survived"] += stats["survived"]
        totals["probed"] += stats["probed"]
        missed = stats["probed"] - stats["survived"]
        flag = "  <-- DROPPED NARRATIVE" if missed else ""
        survive = f"{stats['survived']}/{stats['probed']}"
        print(
            f"{path.name[:50]:<52}{stats['lines']:>7}{stats['boxes']:>7}"
            f"{stats['mixed']:>7}{stats['kept_lines']:>7}{survive:>9}"
            f"{stats['lost_words']:>6}{flag}"
        )
    print("-" * len(header))
    print(f"forms surveyed             : {forms}")
    print(f"lines with box + prose     : {totals['mixed']}")
    print(f"words deleted by rules     : {totals['lost']}")
    print("injected narrative survived: " f"{totals['survived']}/{totals['probed']}")


if __name__ == "__main__":
    main()
