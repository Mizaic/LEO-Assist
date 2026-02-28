#!/usr/bin/env python3
"""Expand domain surface forms from knowledge graph and cache to JSON."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from libs.ner.domain_loader import (  # noqa: E402
    default_config_dir,
    dump_expanded_domains,
    expand_domains_with_kg,
    load_domain_configs,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config-dir",
        default=str(default_config_dir(ROOT)),
        help="Path to domain config JSON directory",
    )
    parser.add_argument(
        "--output",
        default=str(ROOT / "exports" / "ner" / "expanded_domains.json"),
        help="Output JSON cache path",
    )
    parser.add_argument(
        "--desc-depth",
        type=int,
        default=2,
        help="IS_A descendant traversal depth (1-5)",
    )
    parser.add_argument(
        "--desc-limit",
        type=int,
        default=200,
        help="Max descendants per concept",
    )
    parser.add_argument(
        "--no-descendants",
        action="store_true",
        help="Do not include IS_A descendant concept forms",
    )
    args = parser.parse_args()

    cfg_dir = Path(args.config_dir)
    out = Path(args.output)

    logger.info("Loading domain JSON configs from %s", cfg_dir)
    domains = load_domain_configs(cfg_dir)
    logger.info("Loaded %d domains", len(domains))

    logger.info(
        "Expanding forms from KG (descendants=%s, depth=%d, limit=%d)",
        not args.no_descendants,
        args.desc_depth,
        args.desc_limit,
    )
    expand_domains_with_kg(
        domains,
        include_descendants=not args.no_descendants,
        descendant_depth=args.desc_depth,
        descendant_limit=args.desc_limit,
    )

    dump_expanded_domains(domains, out)
    logger.info("Wrote expanded domain cache: %s", out)

    total_forms = sum(len(d.surface_forms) for d in domains.values())
    logger.info("Summary: %d domains, %d total surface forms", len(domains), total_forms)
    for name in sorted(domains):
        s = domains[name].stats
        logger.info(
            "  %-30s forms %5d -> %-5d (+%d)",
            name,
            int(s.get("surface_form_count_before_kg", len(domains[name].surface_forms))),
            int(s.get("surface_form_count_after_kg", len(domains[name].surface_forms))),
            int(s.get("surface_forms_added_from_kg", 0)),
        )


if __name__ == "__main__":
    main()

