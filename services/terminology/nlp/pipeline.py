"""
Pipeline assembly for UK GP clinical NLP.

Wires medspaCy components (ConText, Sectionizer, TargetMatcher, PyRuSH,
Postprocessor) with custom components (AbbreviationDetector, ReadCodeExtractor,
EntityLinker, ValueUnitExtractor, DateExtractor, ConfidenceScorer) using
UK GP-specific rule files.

Usage::

    from services.terminology.nlp.pipeline import load

    nlp = load(kb_path="data/entities.jsonl", index_path="data/")
    doc = nlp("PMH: DM, HTN. C/O SOB for 2 weeks. O/E NAD. BP 120/80.")
    for ent in doc.ents:
        print(ent.text, ent._.snomed_code, ent._.is_negated, ent._.confidence)
"""

from __future__ import annotations

from os import path
from pathlib import Path
from typing import Iterable, Optional, Union

import spacy
from spacy import Language

from .extensions import set_extensions

# Trigger factory registrations
from .components import abbreviation_detector  # noqa: F401
from .components import read_code_extractor  # noqa: F401
from .components import entity_linker  # noqa: F401
from .components import value_unit_extractor  # noqa: F401
from .components import date_extractor  # noqa: F401
from .components import confidence_scorer  # noqa: F401

_RESOURCES = Path(__file__).resolve().parent / "resources"

DEFAULT_PIPE_NAMES = {
    "medspacy_tokenizer",
    "abbreviation_detector",
    "medspacy_pyrush",
    "read_code_extractor",
    "medspacy_target_matcher",
    "clinical_entity_linker",
    "medspacy_context",
    "medspacy_sectionizer",
    "value_unit_extractor",
    "date_extractor",
    "confidence_scorer",
    "medspacy_postprocessor",
}

_RESOLVED_SPAN_ATTRS = {
    "NEGATED_EXISTENCE": {"is_negated": True},
    "POSSIBLE_EXISTENCE": {"is_uncertain": True},
    "HISTORICAL": {"is_historical": True},
    "HYPOTHETICAL": {"is_hypothetical": True},
    "FAMILY": {"is_family": True},
    "RESOLVED": {"is_resolved": True},
}

_SECTION_SPAN_ATTRS = {
    "past_medical_history": {"is_historical": True},
    "family_history": {"is_family": True},
    "plan": {"is_hypothetical": True},
    "safety_netting": {"is_hypothetical": True},
}


def load(
    kb_path: str | Path | None = None,
    index_path: str | Path | None = None,
    neo4j_driver=None,
    enable: Union[set[str], str] = "default",
    language_code: str = "en_gb",
    load_rules: bool = True,
) -> Language:
    """Build and return the UK GP clinical NLP pipeline.

    Parameters
    ----------
    kb_path : path to Entity JSONL file (for Tier 1 linker)
    index_path : directory containing TF-IDF + ANN artifacts
    neo4j_driver : optional ``neo4j.AsyncDriver`` for Tier 2 fallback
    enable : set of component names or ``"default"``
    language_code : resource subdirectory (default ``en_gb``)
    load_rules : whether to load default rule files
    """
    set_extensions()

    if isinstance(enable, str) and enable == "default":
        pipe_names = DEFAULT_PIPE_NAMES
    else:
        pipe_names = set(enable)

    resources = _RESOURCES / language_code

    nlp = spacy.blank("en")

    # 1. Tokenizer
    if "medspacy_tokenizer" in pipe_names:
        from medspacy.custom_tokenizer import create_medspacy_tokenizer

        nlp.tokenizer = create_medspacy_tokenizer(nlp)

    # 2. Abbreviation detector
    if "abbreviation_detector" in pipe_names:
        config: dict = {}
        if load_rules:
            abbrev_path = str(resources / "gp_abbreviations.json")
            if path.exists(abbrev_path):
                config["abbreviations_path"] = abbrev_path
            config["language_code"] = language_code
        nlp.add_pipe("abbreviation_detector", config=config)

    # 3. PyRuSH sentence splitter (falls back to spaCy sentencizer if unavailable)
    if "medspacy_pyrush" in pipe_names:
        try:
            from PyRuSH import PyRuSHSentencizer  # noqa: F401

            rush_path = str(resources / "rush_rules.tsv")
            if not path.exists(rush_path):
                rush_path = str(
                    Path(__file__).resolve().parents[2]
                    / "resources"
                    / "en"
                    / "rush_rules.tsv"
                )
            nlp.add_pipe("medspacy_pyrush", config={"rules_path": rush_path})
        except ImportError:
            import warnings

            warnings.warn(
                "PyRuSH not available -- falling back to spaCy sentencizer. "
                "Install PyRuSH for clinical sentence segmentation.",
                stacklevel=2,
            )
            nlp.add_pipe("sentencizer")

    # 4. Read code extractor
    if "read_code_extractor" in pipe_names:
        nlp.add_pipe("read_code_extractor")

    # 5. Target matcher
    if "medspacy_target_matcher" in pipe_names:
        nlp.add_pipe("medspacy_target_matcher")
        if load_rules:
            target_path = resources / "target_rules.json"
            if target_path.exists():
                from medspacy.target_matcher import TargetRule

                rules = TargetRule.from_json(str(target_path))
                nlp.get_pipe("medspacy_target_matcher").add(rules)

    # 6. Entity linker
    if "clinical_entity_linker" in pipe_names:
        linker_config: dict = {
            "kb_path": str(kb_path) if kb_path else None,
            "index_path": str(index_path) if index_path else None,
        }
        nlp.add_pipe("clinical_entity_linker", config=linker_config)
        if neo4j_driver:
            nlp.get_pipe("clinical_entity_linker").set_neo4j_driver(
                neo4j_driver
            )

    # 7. ConText
    if "medspacy_context" in pipe_names:
        context_config: dict = {"span_attrs": _RESOLVED_SPAN_ATTRS}
        if load_rules:
            ctx_path = str(resources / "context_rules.json")
            if path.exists(ctx_path):
                context_config["rules"] = ctx_path
            context_config["language_code"] = language_code
        else:
            context_config["rules"] = None
            context_config["language_code"] = language_code
        nlp.add_pipe("medspacy_context", config=context_config)

    # 8. Sectionizer
    if "medspacy_sectionizer" in pipe_names:
        section_config: dict = {"span_attrs": _SECTION_SPAN_ATTRS}
        if load_rules:
            sec_path = str(resources / "section_patterns.json")
            if path.exists(sec_path):
                section_config["rules"] = sec_path
            section_config["language_code"] = language_code
        else:
            section_config["rules"] = None
            section_config["language_code"] = language_code
        nlp.add_pipe("medspacy_sectionizer", config=section_config)

    # 9. Value/unit extractor
    if "value_unit_extractor" in pipe_names:
        nlp.add_pipe("value_unit_extractor")

    # 10. Date extractor
    if "date_extractor" in pipe_names:
        nlp.add_pipe("date_extractor")

    # 11. Confidence scorer
    if "confidence_scorer" in pipe_names:
        nlp.add_pipe("confidence_scorer")

    # 12. Postprocessor
    if "medspacy_postprocessor" in pipe_names:
        nlp.add_pipe("medspacy_postprocessor")

    return nlp
