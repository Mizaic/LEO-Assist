"""Audit GPT-5 prompts. Atlas trace: DI-7B978C0C / DO-FA8FCECF."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

SEARCH_ROOTS = ("libs/prompts", "libs/llm_client", "services", "scripts")
PROMPT_NAME_PARTS = (
    "PROMPT",
    "SYSTEM",
    "INSTRUCTION",
    "TEMPLATE",
    "FEW_SHOT",
    "EXAMPLE",
    "SCHEMA",
)
STALE_PROVIDER_RE = re.compile(
    r"\b(?:anthropic|claude(?:-\d[\w.-]*)?|amazon bedrock|bedrock)\b",
    re.IGNORECASE,
)
CLINICAL_RE = re.compile(
    r"\b(?:clinical|clinician|patient|snomed|referral|diagnosis|health)\b",
    re.IGNORECASE,
)
JSON_REQUEST_RE = re.compile(
    r"\b(?:return|respond|reply|output|produce|emit)\b[^.\n]{0,50}\bjson\b",
    re.IGNORECASE,
)
_CONTRADICTION_TEXT = (
    (
        r"\b(?:return|output|respond with)\s+(?:only\s+)?json\b",
        r"\bdo not\s+(?:return|output|respond with)\s+json\b",
    ),
    (r"\buse\s+markdown\b", r"\bdo not\s+use\s+markdown\b"),
)
CONTRADICTION_PAIRS = tuple(
    (re.compile(first, re.I), re.compile(second, re.I))
    for first, second in _CONTRADICTION_TEXT
)


@dataclass(frozen=True)
class PromptSource:
    source_path: str
    symbol: str
    value: Any
    expression: str
    nested: bool


@dataclass(frozen=True)
class AuditInput:
    text: str
    schema: dict[str, Any] | None
    examples: list[Any]
    guarded: bool
    inline: bool


def _static_value(node: ast.AST, env: dict[str, Any]) -> Any:
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError):
        pass
    if isinstance(node, ast.Name):
        if node.id == "INJECTION_GUARD":
            return ""
        return env.get(node.id)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _static_value(node.left, env)
        right = _static_value(node.right, env)
        if isinstance(left, str) and isinstance(right, str):
            return left + right
        if isinstance(left, list) and isinstance(right, list):
            return left + right
    if isinstance(node, ast.JoinedStr):
        return _joined_string(node, env)
    return None


def _joined_string(node: ast.JoinedStr, env: dict[str, Any]) -> str | None:
    parts: list[str] = []
    for value in node.values:
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            parts.append(value.value)
        elif isinstance(value, ast.FormattedValue):
            resolved = _static_value(value.value, env)
            parts.append(str(resolved) if resolved is not None else "{dynamic}")
        else:
            return None
    return "".join(parts)


def _module_environment(tree: ast.Module) -> dict[str, Any]:
    env: dict[str, Any] = {}
    for node in tree.body:
        target: ast.AST | None = None
        value: ast.AST | None = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign):
            target, value = node.target, node.value
        if isinstance(target, ast.Name) and value is not None:
            resolved = _static_value(value, env)
            if resolved is not None:
                env[target.id] = resolved
    return env


def _prompt_like_name(name: str, nested: bool) -> bool:
    upper = name.upper()
    if not any(part in upper for part in PROMPT_NAME_PARTS):
        return False
    return name == upper or (nested and upper in {"SYSTEM", "SYSTEM_PROMPT"})


def _prompt_like_value(name: str, value: Any) -> bool:
    if isinstance(value, str):
        return len(value.strip()) >= 80
    upper = name.upper()
    return (
        isinstance(value, (list, tuple, dict))
        and ("EXAMPLE" in upper or "FEW_SHOT" in upper or "SCHEMA" in upper)
        and bool(value)
    )


def discover_prompt_sources(repo_root: Path) -> list[PromptSource]:
    """Discover Python prompt-like constants using AST only."""
    found: list[PromptSource] = []
    for search_root in SEARCH_ROOTS:
        root = repo_root / search_root
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            found.extend(_discover_file(repo_root, path))
    return sorted(found, key=lambda item: (item.source_path, item.symbol))


def _discover_file(repo_root: Path, path: Path) -> list[PromptSource]:
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (OSError, UnicodeDecodeError, SyntaxError):
        return []
    env = _module_environment(tree)
    relative = path.relative_to(repo_root).as_posix()
    top_level_ids = {id(node) for node in tree.body}
    found: list[PromptSource] = []
    for node in ast.walk(tree):
        assignment = _assignment_parts(node)
        if assignment is None:
            continue
        target, value = assignment
        nested = id(node) not in top_level_ids
        evaluated = _static_value(value, env)
        if not _prompt_like_name(target.id, nested):
            continue
        if not _prompt_like_value(target.id, evaluated):
            continue
        symbol = target.id if not nested else f"{target.id}@L{node.lineno}"
        expression = ast.get_source_segment(source, value) or ""
        found.append(PromptSource(relative, symbol, evaluated, expression, nested))
    return found


def _assignment_parts(node: ast.AST) -> tuple[ast.Name, ast.AST] | None:
    if isinstance(node, ast.Assign) and len(node.targets) == 1:
        target = node.targets[0]
        if isinstance(target, ast.Name):
            return target, node.value
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        if node.value is not None:
            return node.target, node.value
    return None


def load_seed_prompts() -> list[dict[str, Any]]:
    """Import the authoritative factory PromptConfig inventory."""
    module_name = (
        "scripts.seed_prompt_configs" if __package__ else "seed_prompt_configs"
    )
    module = __import__(module_name, fromlist=["SEED_PROMPTS"])
    return list(module.SEED_PROMPTS)


def build_inventory(
    repo_root: Path,
    seed_prompts: Sequence[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a deterministic inventory and cookbook audit report."""
    seeds = list(seed_prompts) if seed_prompts is not None else load_seed_prompts()
    sources = discover_prompt_sources(repo_root)
    source_by_hash = _sources_by_hash(sources)
    entries = [_seed_entry(seed, source_by_hash) for seed in seeds]
    seeded_hashes = {_sha256(str(seed.get("system_prompt", ""))) for seed in seeds}
    entries.extend(
        _source_entry(source, sources)
        for source in sources
        if _sha256(
            source.value
            if isinstance(source.value, str)
            else _canonical_json(source.value)
        )
        not in seeded_hashes
    )
    entries.sort(
        key=lambda item: (
            item["source_path"],
            item["symbol"],
            json.dumps(item["seeded_identity"], sort_keys=True),
        )
    )
    issue_count = sum(len(item["issues"]) for item in entries)
    issue_types = Counter(
        issue.split(":", 1)[0] for item in entries for issue in item["issues"]
    )
    issue_samples: dict[str, list[str]] = {}
    for item in entries:
        for issue in item["issues"]:
            kind = issue.split(":", 1)[0]
            samples = issue_samples.setdefault(kind, [])
            locator = f"{item['source_path']}:{item['symbol']}"
            if locator not in samples and len(samples) < 100:
                samples.append(locator)
    return {
        "entries": entries,
        "summary": {
            "entry_count": len(entries),
            "seeded_count": len(seeds),
            "issue_count": issue_count,
            "issue_types": dict(sorted(issue_types.items())),
            "issue_samples": dict(sorted(issue_samples.items())),
            "clean_count": sum(not item["issues"] for item in entries),
        },
    }


def _sources_by_hash(sources: Sequence[PromptSource]) -> dict[str, PromptSource]:
    """Choose a stable source location for each discovered prompt hash."""
    result: dict[str, PromptSource] = {}
    for source in sources:
        if not isinstance(source.value, str):
            continue
        digest = _sha256(source.value)
        current = result.get(digest)
        rank = (not source.source_path.startswith("libs/prompts/"), source.source_path)
        current_rank = (
            (True, "")
            if current is None
            else (
                not current.source_path.startswith("libs/prompts/"),
                current.source_path,
            )
        )
        if current is None or rank < current_rank:
            result[digest] = source
    return result


def _seed_entry(
    seed: dict[str, Any],
    source_by_hash: dict[str, PromptSource],
) -> dict[str, Any]:
    text = str(seed.get("system_prompt", ""))
    source = source_by_hash.get(_sha256(text))
    name = str(seed.get("name", "unknown"))
    version = seed.get("version")
    schema = _parse_schema(seed.get("output_schema"))
    examples = list(seed.get("few_shot_examples") or [])
    path = source.source_path if source else "scripts/seed_prompt_configs.py"
    symbol = source.symbol if source else f"SEED_PROMPTS[{name}@{version}]"
    guarded = bool(source and "INJECTION_GUARD" in source.expression)
    return _entry(
        path,
        symbol,
        _category(symbol, seeded=True),
        {"name": name, "version": version},
        AuditInput(text, schema, examples, guarded, False),
    )


def _source_entry(
    source: PromptSource,
    all_sources: Sequence[PromptSource],
) -> dict[str, Any]:
    siblings = [
        item
        for item in all_sources
        if item.source_path == source.source_path and item is not source
    ]
    schemas = [item.value for item in siblings if "SCHEMA" in item.symbol.upper()]
    examples = _nearby_examples(source, siblings)
    schema = next(
        (_parse_schema(item) for item in schemas if _parse_schema(item)), None
    )
    value = source.value
    text = value if isinstance(value, str) else _canonical_json(value)
    inline = source.nested or source.source_path.startswith(("services/", "scripts/"))
    return _entry(
        source.source_path,
        source.symbol,
        _category(source.symbol),
        None,
        AuditInput(
            text,
            schema,
            examples,
            "INJECTION_GUARD" in source.expression,
            inline,
        ),
    )


def _nearby_examples(
    source: PromptSource,
    siblings: Sequence[PromptSource],
) -> list[Any]:
    upper_source = source.symbol.upper()
    if "SCHEMA" in upper_source:
        return []
    if isinstance(source.value, (list, tuple)):
        return list(source.value)
    if not isinstance(source.value, str):
        return []
    version = re.search(r"_V(\d+)\b", source.symbol.upper())
    version_token = f"_V{version.group(1)}" if version else ""
    examples: list[Any] = []
    for item in siblings:
        upper = item.symbol.upper()
        if version_token and version_token not in upper:
            continue
        if isinstance(item.value, (list, tuple)) and (
            "EXAMPLE" in upper or "FEW_SHOT" in upper
        ):
            examples.extend(item.value)
    return examples


def _entry(
    source_path: str,
    symbol: str,
    category: str,
    seeded_identity: dict[str, Any] | None,
    material: AuditInput,
) -> dict[str, Any]:
    issues = audit_prompt(
        material.text,
        material.schema,
        material.examples,
        category=category,
        guarded=material.guarded,
        inline=material.inline,
    )
    return {
        "source_path": source_path,
        "symbol": symbol,
        "category": category,
        "consumer": (
            f"PromptConfig:{seeded_identity['name']}"
            if seeded_identity
            else source_path
        ),
        "model_tier": "runtime-configured",
        "seed_status": "seeded" if seeded_identity else "code_only",
        "seeded_identity": seeded_identity,
        "sha256": _sha256(material.text),
        "output_schema_present": material.schema is not None,
        "few_shot_count": len(material.examples),
        "issues": issues,
    }


def audit_prompt(
    text: str,
    schema: dict[str, Any] | None,
    examples: Sequence[Any],
    *,
    category: str = "system_prompt",
    guarded: bool = False,
    inline: bool = False,
) -> list[str]:
    """Run deterministic conservative cookbook checks on one prompt."""
    issues: list[str] = []
    contradictory = any(
        first.search(text) and second.search(text)
        for first, second in CONTRADICTION_PAIRS
    )
    if contradictory:
        issues.append("contradictory_imperatives")
    json_requested = bool(JSON_REQUEST_RE.search(text))
    if json_requested and schema is None and not _has_inline_json_contract(text):
        issues.append("unclear_json_output_contract")
    issues.extend(_few_shot_json_issues(text, schema, examples))
    if _has_duplicate_examples(examples):
        issues.append("duplicate_few_shots")
    if STALE_PROVIDER_RE.search(text):
        issues.append("stale_claude_bedrock_wording")
    is_system = category == "system_prompt"
    if inline and is_system and CLINICAL_RE.search(text) and not guarded:
        issues.append("likely_missing_injection_guard")
    if not text.isascii() or not _canonical_json(list(examples)).isascii():
        issues.append("non_ascii")
    return sorted(set(issues))


def _few_shot_json_issues(
    text: str,
    schema: dict[str, Any] | None,
    examples: Sequence[Any],
) -> list[str]:
    expected = schema.get("type") if schema else None
    if expected not in {"object", "array"}:
        if re.search(r"\bjson\s+(?:object|dictionary)\b", text, re.I):
            expected = "object"
        elif re.search(r"\bjson\s+(?:array|list)\b", text, re.I):
            expected = "array"
    if not expected and schema is None and not JSON_REQUEST_RE.search(text):
        return []
    issues: list[str] = []
    for index, example in enumerate(examples):
        if not isinstance(example, dict) or "output" not in example:
            continue
        output = example.get("output") if isinstance(example, dict) else None
        parsed, valid = _parse_json_output(output)
        if not valid:
            issues.append(f"few_shot_output_not_json:{index}")
        elif expected == "object" and not isinstance(parsed, dict):
            issues.append(f"few_shot_json_type_mismatch:{index}")
        elif expected == "array" and not isinstance(parsed, list):
            issues.append(f"few_shot_json_type_mismatch:{index}")
    return issues


def _parse_json_output(value: Any) -> tuple[Any, bool]:
    if isinstance(value, (dict, list)):
        return value, True
    if not isinstance(value, str):
        return None, False
    try:
        return json.loads(value), True
    except json.JSONDecodeError:
        return None, False


def _has_inline_json_contract(text: str) -> bool:
    if re.search(r"\b(?:supplied|provided)\s+(?:output\s+)?schema\b", text, re.I):
        return True
    if re.search(r"\bmatching\s+the\s+shape\s+in\s+the\s+user\s+message\b", text, re.I):
        return True
    if re.search(r"\bmatching\b[^.\n]{0,30}\bschema\b[^.\n]{0,30}\buser\b", text, re.I):
        return True
    if re.search(r"\buser(?:-message)?\s+schema\b", text, re.I):
        return True
    if re.search(r"\bjson\s+(?:array|list)\b[^.\n]{0,50}\bstrings?\b", text, re.I):
        return True
    has_braces = "{" in text and "}" in text
    has_named_field = bool(re.search(r'["`][A-Za-z_][\w-]*["`]\s*:', text))
    has_fields_phrase = bool(re.search(r"\bjson\b[^.\n]{0,40}\bfields?\b", text, re.I))
    has_collection_field = bool(re.search(r"\b[A-Za-z_][\w-]*\[\]", text))
    return has_fields_phrase or (has_braces and has_named_field) or has_collection_field


def _has_duplicate_examples(examples: Sequence[Any]) -> bool:
    seen: set[str] = set()
    for example in examples:
        if isinstance(example, dict):
            value = {"input": example.get("input"), "output": example.get("output")}
        else:
            value = example
        digest = _sha256(_canonical_json(value))
        if digest in seen:
            return True
        seen.add(digest)
    return False


def _parse_schema(value: Any) -> dict[str, Any] | None:
    parsed = value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return None
    return parsed if isinstance(parsed, dict) and bool(parsed) else None


def _category(symbol: str, *, seeded: bool = False) -> str:
    upper = symbol.upper()
    if "EXAMPLE" in upper or "FEW_SHOT" in upper:
        return "few_shot"
    if "SCHEMA" in upper:
        return "output_schema"
    if "SYSTEM" in upper or seeded:
        return "system_prompt"
    if "TEMPLATE" in upper or "TASK" in upper:
        return "user_prompt"
    return "prompt"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_json_report(report: dict[str, Any], output_path: Path) -> None:
    """Write a deterministic JSON report to the requested path."""
    output_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=True, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the read-only prompt inventory CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-out", type=Path, help="Write the full JSON report.")
    args = parser.parse_args(argv)
    repo_root = Path(__file__).resolve().parent.parent
    report = build_inventory(repo_root)
    summary = report["summary"]
    print("Prompt audit:", json.dumps(summary, sort_keys=True))
    if args.json_out:
        write_json_report(report, args.json_out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
