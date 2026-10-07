"""Build form-recognition fixtures through the production conversion path.

Production markdown is made in HCCP-Agents, not in LEO:
DOC / DOCX / RTF -> HCCP-Doc-Converter ``POST /convert`` (LibreOffice
``html:HTML:EmbedImages``) -> ``HDTHTMLParser.convert_html_to_markdown``.

This script repeats that path locally against blank template forms in
``templates/`` so the fixtures match what the pipeline really sees. It
also re-saves each DOCX as DOC and RTF with LibreOffice first, so the
same form can be checked in every Word format we receive.

The HCCP-Agents parser is loaded from its own file, unchanged. Its
langchain base classes are stubbed because only the BeautifulSoup logic
is used.

Usage::

    python scripts/build_form_recognition_fixtures.py \
        --agents-repo ../HCCP-Agents

Writes one JSON fixture per form and format (the markdown is in ``text``).
Never touches Neo4j or any network service.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = REPO_ROOT / "templates"
OUT_DIR = REPO_ROOT / "tests" / "fixtures" / "form_recognition" / "markdown"
PARSER_REL = Path("agent") / "leo_agents" / "services" / "convert_to_md.py"
CONVERSION = (
    "LibreOffice --convert-to html:HTML:EmbedImages, then HCCP-Agents "
    "HDTHTMLParser.convert_html_to_markdown"
)

# (template file, fixture stem, extra Word formats to round-trip through)
SOURCES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("USCP-Gynaecology-Referral-Form-V8.docx", "uscp_gynae_v8", ("doc", "rtf")),
    ("Breast-Cancer-Referral-FormS1-v3.5.docx", "breast_s1_v3_5", ("doc", "rtf")),
    ("EoE_CA_Gynae_Referral_Form_Feb_25_.docx", "eoe_gynae_feb25", ()),
    ("LowerGI_Cancer-Referral-Form-V6.docx", "lower_gi_v6", ("rtf",)),
    ("20230523_EoE_USC_Proforma_LOWER_GI_FINAL_V6_1.docx", "eoe_lower_gi_v6_1", ()),
    ("Upper-GI-Cancers-Referral-Form-S1s.docx", "upper_gi_s1s", ()),
    ("Haematological-Cancer-Referral-Form-S1s.docx", "haem_s1s", ()),
    ("LungCancerReferralFormS1_V3.0.docx", "lung_s1_v3", ()),
    ("2WW-Non-site-specific-SystmOne.docx", "nss_systmone", ()),
    ("HeadAndNeckCancerReferralForm-V6.docx", "head_neck_v6", ()),
)


def _soffice() -> str:
    found = shutil.which("soffice")
    if found:
        return found
    default = Path(r"C:\Program Files\LibreOffice\program\soffice.exe")
    if default.exists():
        return str(default)
    raise SystemExit("LibreOffice (soffice) not found.")


def _stub_langchain() -> None:
    """Register the three langchain names convert_to_md.py imports."""

    class _Base:  # noqa: D401 - stand-in base class
        """Stand-in for BaseBlobParser / Document / Blob."""

    names = {
        "langchain_core": None,
        "langchain_core.documents": {"Document": _Base},
        "langchain_community": None,
        "langchain_community.document_loaders": None,
        "langchain_community.document_loaders.base": {"BaseBlobParser": _Base},
        "langchain_community.document_loaders.blob_loaders": {"Blob": _Base},
    }
    for name, attrs in names.items():
        module = types.ModuleType(name)
        for key, value in (attrs or {}).items():
            setattr(module, key, value)
        sys.modules[name] = module


def load_parser(agents_repo: Path):
    """Load HDTHTMLParser from the HCCP-Agents source file."""
    path = agents_repo / PARSER_REL
    if not path.exists():
        raise SystemExit(f"HCCP-Agents parser not found at {path}")
    _stub_langchain()
    spec = importlib.util.spec_from_file_location("hccp_convert_to_md", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.HDTHTMLParser()


def _convert(soffice: str, src: Path, target: str, outdir: Path) -> Path:
    command = [soffice, "--headless", "--convert-to", target, "--outdir"]
    subprocess.run(
        [*command, str(outdir), str(src)],
        check=True,
        capture_output=True,
        timeout=180,
    )
    ext = target.split(":", 1)[0]
    out = outdir / f"{src.stem}.{ext}"
    if not out.exists():
        raise RuntimeError(f"LibreOffice did not write {out.name}")
    return out


def to_markdown(soffice: str, parser, src: Path, workdir: Path) -> str:
    """Run one Word file through the production html -> markdown path."""
    html_path = _convert(soffice, src, "html:HTML:EmbedImages", workdir)
    html = html_path.read_text(encoding="utf-8", errors="replace")
    return parser.convert_html_to_markdown(html_content=html)


def write_fixture(out: Path, template: str, fmt: str, markdown: str) -> None:
    """JSON keeps the file ASCII while the text keeps its real characters."""
    payload = {
        "source_template": f"templates/{template}",
        "format": fmt,
        "conversion": CONVERSION,
        "text": markdown,
    }
    out.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2) + "\n",
        encoding="ascii",
        newline="\n",
    )


def build_one(soffice: str, parser, source: tuple, workdir: Path) -> list[Path]:
    template, stem, extra = source
    src = TEMPLATES / template
    written: list[Path] = []
    variants = [("docx", src)]
    for fmt in extra:
        fmt_dir = workdir / fmt
        fmt_dir.mkdir(exist_ok=True)
        variants.append((fmt, _convert(soffice, src, fmt, fmt_dir)))
    for fmt, path in variants:
        html_dir = workdir / f"html_{fmt}"
        html_dir.mkdir(exist_ok=True)
        markdown = to_markdown(soffice, parser, path, html_dir)
        out = OUT_DIR / f"{stem}.{fmt}.json"
        write_fixture(out, template, fmt, markdown)
        written.append(out)
    return written


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--agents-repo", type=Path, required=True)
    args = ap.parse_args(argv)
    parser = load_parser(args.agents_repo.resolve())
    soffice = _soffice()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for source in SOURCES:
            for path in build_one(soffice, parser, source, Path(tmp)):
                print(path.relative_to(REPO_ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
