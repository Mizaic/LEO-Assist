"""Check which DIs cover terminology/resolver/NER pipeline."""

import re
from pathlib import Path

DIS = [
    "DI-LEO-AI-004.yaml",
    "DI-LEO-AI-033.yaml",
    "DI-LEO-AI-034.yaml",
    "DI-LEO-AI-038.yaml",
    "DI-LEO-AI-039.yaml",
    "DI-LEO-AI-040.yaml",
    "DI-LEO-AI-041.yaml",
    "DI-LEO-AI-044.yaml",
    "DI-LEO-AI-048.yaml",
]
base = Path("design-controls/design-inputs")
for fname in DIS:
    f = base / fname
    if not f.exists():
        continue
    content = f.read_text(encoding="utf-8", errors="ignore")
    id_m = re.search(r"id:\s*(.+)", content)
    title_m = re.search(r"title:\s*(.+)", content)
    req_m = re.search(r"requirement:\s*(.{0,200})", content, re.DOTALL)
    files_m = re.findall(r"file_structure.*?(?=\n\s*\n|\Z)", content, re.DOTALL)
    print(f"{fname}")
    print(f"  id:    {id_m.group(1).strip() if id_m else '?'}")
    print(f"  title: {title_m.group(1).strip() if title_m else '?'}")
    if req_m:
        req = req_m.group(1).strip().replace("\n", " ")[:130]
        print(f"  req:   {req}")
    print()
