"""Register TransformerListener with explicit hidden width for frozen-transformer init.

Atlas trace:
  DO: DO-4F80FAD8
  DI: DI-3103A562
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-4F80FAD8")

When ``transformer`` is in ``frozen_components``, ``init_nlp`` disables that pipe
during ``Language.initialize``. The upstream ``TransformerModel`` then never runs
``initialize``, so it never sets ``nO`` and ``add_listener`` cannot copy the
dimension onto ``TransformerListener``. The stock
``spacy-transformers.TransformerListener.v1`` no longer accepts a ``width``
config key; this drop-in architecture sets ``listener.set_dim(\"nO\", width)``
before chaining, so SpanCategorizer init succeeds.

Import this module before spaCy resolves a config that references
``leo_training.TransformerListener.v1`` (see ``run_spacy_train_cli.py``).

Bio_ClinicalBERT hidden size is 768. Override via config ``width`` if the HF
model changes.
"""

from __future__ import annotations

from typing import List

from thinc.api import Model, chain
from thinc.types import Floats2d, Ragged
from spacy.tokens import Doc
from spacy_transformers.layers import TransformerListener, trfs2arrays
from spacy_transformers.util import registry


@registry.architectures.register("leo_training.TransformerListener.v1")
def leo_transformer_listener_v1(
    pooling: Model[Ragged, Floats2d],
    grad_factor: float = 1.0,
    upstream: str = "*",
    width: int = 768,
) -> Model[List[Doc], List[Floats2d]]:
    """Same as ``spacy-transformers.TransformerListener.v1`` but sets ``nO``."""
    listener = TransformerListener(upstream_name=upstream)
    listener.set_dim("nO", int(width))
    model: Model = chain(listener, trfs2arrays(pooling, grad_factor))
    model.set_ref("listener", listener)
    return model
