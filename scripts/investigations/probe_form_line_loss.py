"""Read-only probe: show what normalisation does to spiked checkbox lines.

Prints the raw line, the layout-rule rewrite, and whether the injected
clinical sentence survived ``extractable_clinical_lines``. Used to tell a
real recall hole apart from an artefact of the survey's docx reader.

Usage:
    .venv/bin/python scripts/investigations/probe_form_line_loss.py \
        Breast-Cancer-Referral-FormS1-v3.5.docx --limit 6
"""

from __future__ import annotations

import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from libs.ner.form_checkbox_normalizer import (  # noqa: E402
    extractable_clinical_lines,
)
from libs.ner.form_layout_rules import (  # noqa: E402
    apply_form_layout_rules,
    has_trailing_prose,
)
from scripts.investigations.survey_form_templates import (  # noqa: E402
    SENTINEL,
    _BOX,
    _docx_text,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("form")
    parser.add_argument("--limit", type=int, default=6)
    args = parser.parse_args()

    text = _docx_text(ROOT / "templates" / args.form)
    lines = [ln for ln in text.splitlines() if ln.strip()]
    shown = 0
    for line in lines:
        if not _BOX.search(line) or shown >= args.limit:
            continue
        shown += 1
        spiked = f"{line.rstrip()} {SENTINEL}"
        kept = extractable_clinical_lines(spiked)
        print(f"--- raw      : {line.strip()[:200]!r}")
        print(f"    spiked   : {spiked.strip()[:200]!r}")
        print(f"    prose?   : {has_trailing_prose(spiked)}")
        print(f"    layout   : {apply_form_layout_rules(spiked)[:200]!r}")
        print(f"    kept     : {[k[:160] for k in kept]}")
        print(f"    survived : {'vulval sores' in ' '.join(kept).lower()}")
        print()


if __name__ == "__main__":
    main()
