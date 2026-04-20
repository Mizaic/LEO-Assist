"""Run ``spacy`` CLI after registering LEO training architectures.

Atlas trace:
  DO: DO-4F80FAD8
  DI: DI-3103A562
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-4F80FAD8")

Used instead of ``python -m spacy`` so ``leo_training.TransformerListener.v1``
is registered before config resolution.
"""

from __future__ import annotations

from spacy.cli import setup_cli


def main() -> None:
    import app.spacy_listener_width  # noqa: F401 - registers architecture

    setup_cli()


if __name__ == "__main__":
    main()
