"""Rule-based spaCy encounter textcat component.

Classifies GP encounters as admin_only / document_transfer / clinical using
deterministic phrase and regex pattern matching. EPR text is never sent to an
LLM, eliminating the prompt injection surface identified in NER-T-001.

Classification priority (highest wins):
    1. clinical_override match  -> clinical
    2. document_transfer match  -> document_transfer
    3. admin_only match         -> admin_only
    4. (default)                -> clinical

Extending the classifier requires only editing ``encounter_rules.json``.
No code changes and no model retraining are needed.
"""
from __future__ import annotations

import json
import logging
import re
import threading
from pathlib import Path
from typing import Optional

import spacy
from spacy.language import Language
from spacy.matcher import PhraseMatcher
from spacy.tokens import Doc

logger = logging.getLogger(__name__)

_RULES_PATH = Path(__file__).parent / "encounter_rules.json"

CONTENT_TYPES = ("admin_only", "document_transfer", "clinical")
DEFAULT_LABEL = "clinical"

# Maximum characters of encounter text passed to the pipeline.
# Keeps processing time bounded; mirrors the 3000-char window used previously.
_MAX_CHARS = 3000


# ── Component ─────────────────────────────────────────────────────────────────


class EncounterTextcat:
    """spaCy pipeline component that classifies encounters via pattern rules.

    Sets ``doc.cats`` with one-hot scores for the winning class.

    Args:
        nlp:        The parent spaCy ``Language`` pipeline.
        name:       Component name (injected by spaCy).
        rules_path: Path to the JSON rule file. Defaults to ``encounter_rules.json``
                    in the same directory as this module.
    """

    def __init__(self, nlp, name: str, rules_path: str) -> None:
        path = Path(rules_path)
        rules: dict = json.loads(path.read_text(encoding="utf-8"))

        admin = rules.get("admin_only", {})
        doc_t = rules.get("document_transfer", {})
        clin = rules.get("clinical_override", {})

        self._admin_matcher = self._build_phrase_matcher(
            nlp, admin.get("phrases", [])
        )
        self._admin_regex: list[re.Pattern] = [
            re.compile(p) for p in admin.get("regex", [])
        ]
        self._admin_max_length: int = int(admin.get("max_length", 0))

        self._doc_matcher = self._build_phrase_matcher(
            nlp, doc_t.get("phrases", [])
        )
        self._doc_regex: list[re.Pattern] = [
            re.compile(p) for p in doc_t.get("regex", [])
        ]

        self._clin_matcher = self._build_phrase_matcher(
            nlp, clin.get("phrases", [])
        )
        self._clin_regex: list[re.Pattern] = [
            re.compile(p) for p in clin.get("regex", [])
        ]

        logger.debug("EncounterTextcat: loaded rules from %s", path)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _build_phrase_matcher(nlp, phrases: list[str]) -> PhraseMatcher:
        matcher = PhraseMatcher(nlp.vocab, attr="LOWER")
        if phrases:
            patterns = list(nlp.tokenizer.pipe(phrases))
            matcher.add("MATCH", patterns)
        return matcher

    @staticmethod
    def _hits(matcher: PhraseMatcher, doc: Doc) -> bool:
        return bool(matcher(doc))

    @staticmethod
    def _regex_hits(patterns: list[re.Pattern], text: str) -> bool:
        return any(p.search(text) for p in patterns)

    # ── Pipeline entry point ──────────────────────────────────────────────────

    def __call__(self, doc: Doc) -> Doc:
        text = doc.text

        # 1. clinical_override: strong GP-authored signals win unconditionally.
        if self._hits(self._clin_matcher, doc) or self._regex_hits(
            self._clin_regex, text
        ):
            label = "clinical"

        # 2. document_transfer: filing-action language.
        elif self._hits(self._doc_matcher, doc) or self._regex_hits(
            self._doc_regex, text
        ):
            label = "document_transfer"

        # 3. admin_only: non-clinical admin / system entries.
        elif (
            self._hits(self._admin_matcher, doc)
            or self._regex_hits(self._admin_regex, text)
            or (
                self._admin_max_length
                and len(text.strip()) <= self._admin_max_length
            )
        ):
            label = "admin_only"

        # 4. Default: clinical (conservative — never miss a clinical encounter).
        else:
            label = DEFAULT_LABEL

        doc.cats = {ct: 1.0 if ct == label else 0.0 for ct in CONTENT_TYPES}
        return doc


# ── spaCy factory registration ────────────────────────────────────────────────


def _encounter_textcat_factory(nlp, name: str, rules_path: str) -> EncounterTextcat:
    return EncounterTextcat(nlp, name, rules_path)


if not Language.has_factory("encounter_textcat"):
    Language.factory(
        "encounter_textcat",
        default_config={"rules_path": str(_RULES_PATH)},
        func=_encounter_textcat_factory,
    )


# ── Singleton pipeline ────────────────────────────────────────────────────────

_nlp_lock = threading.Lock()
_nlp_instance: Optional[Language] = None


def _get_pipeline(rules_path: Optional[str] = None) -> Language:
    """Return a cached blank ``en`` spaCy pipeline with the encounter_textcat component.

    Thread-safe. The pipeline is created once and reused for the lifetime of
    the process. The ``PhraseMatcher`` instances inside the component are
    read-only after init, so concurrent calls are safe.
    """
    global _nlp_instance
    with _nlp_lock:
        if _nlp_instance is None:
            nlp = spacy.blank("en")
            cfg: dict = {}
            if rules_path:
                cfg["rules_path"] = rules_path
            nlp.add_pipe("encounter_textcat", config=cfg)
            _nlp_instance = nlp
            logger.info("EncounterTextcat pipeline initialised (rules: %s)", rules_path or _RULES_PATH)
    return _nlp_instance


def classify_text(text: str, rules_path: Optional[str] = None) -> str:
    """Classify encounter text and return the winning content_type label.

    Args:
        text:       Raw encounter text (will be truncated to ``_MAX_CHARS``).
        rules_path: Override the default rule file path (used in tests).

    Returns:
        One of ``"admin_only"``, ``"document_transfer"``, or ``"clinical"``.
    """
    if not text or not text.strip():
        return "admin_only"

    nlp = _get_pipeline(rules_path)
    doc = nlp(text[:_MAX_CHARS])
    if not doc.cats:
        return DEFAULT_LABEL
    return max(doc.cats, key=lambda k: doc.cats[k])


def reset_pipeline() -> None:
    """Reset the singleton pipeline (for testing / config reload).

    Should not be called in production code.
    """
    global _nlp_instance
    with _nlp_lock:
        _nlp_instance = None
