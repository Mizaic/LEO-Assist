"""Register TransformerListener with explicit hidden width for frozen-transformer init.

Atlas trace:
  DO: DO-4F80FAD8
  DI: DI-3103A562
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-4F80FAD8")

When ``transformer`` is in ``frozen_components``, spaCy's ``init_nlp`` calls
``nlp.select_pipes(disable=frozen_components)`` before ``nlp.initialize()``.
Two downstream effects:

1. ``TransformerModel.nO`` is never set, so ``add_listener`` cannot copy the
   dimension onto ``TransformerListener``.  Fixed here by calling
   ``listener.set_dim("nO", width)`` explicitly.

2. ``TransformerModel.init()`` is never called, so the HuggingFace tokenizer
   (``model.layers[0].shims[0]._hfmodel.tokenizer``) stays ``None``.  The
   first ``nlp.update()`` call (via ``annotating_components``) then crashes:
       TypeError: 'NoneType' object is not callable
   Fixed by the ``leo_training.init_frozen_transformer.v1`` callback below,
   which is wired into ``[initialize] after_init`` in ``base.cfg``.

Import this module before spaCy resolves a config that references any
``leo_training.*`` symbol (see ``run_spacy_train_cli.py``).
"""

from __future__ import annotations

import logging
from typing import Callable, List

from spacy.language import Language
from spacy.tokens import Doc
from spacy_transformers import Transformer as _SpacyTransformer
from spacy_transformers.layers import TransformerListener, trfs2arrays
from spacy_transformers.layers.transformer_model import init as _trf_model_init
from spacy_transformers.util import registry
from thinc.api import Model, chain
from thinc.types import Floats2d, Ragged

from libs.training_ext import label_smoothing as _label_smoothing
from libs.training_ext import lora_adapter as _lora_adapter
from libs.training_ext import suggesters as _suggesters  # noqa: F401

_lora_adapter.register_lora_callback()
_label_smoothing.register_label_smoothing_scorer()

logger = logging.getLogger(__name__)


@registry.misc.register("leo_training.init_frozen_transformer.v1")
def make_init_frozen_transformer() -> Callable[[Language], None]:
    """Return an ``after_init`` callback that force-initialises any Transformer
    pipe whose HuggingFace model was skipped because it was in
    ``frozen_components`` during ``nlp.initialize()``.

    Register in ``[initialize] after_init`` of the spaCy training config.
    """

    def after_init(nlp: Language) -> None:
        # Use nlp.components (not nlp.pipeline) so that frozen components,
        # which are disabled via select_pipes() during nlp.initialize(), are
        # still visited.  nlp.pipeline excludes disabled components.
        for name, pipe in nlp.components:
            if not isinstance(pipe, _SpacyTransformer):
                continue
            if pipe.model.attrs.get("has_transformer", False):
                continue
            logger.info(
                "[after_init] Frozen transformer '%s' was skipped during "
                "nlp.initialize(); loading HuggingFace model + tokenizer now.",
                name,
            )
            _trf_model_init(pipe.model)
            logger.info(
                "[after_init] Transformer '%s' initialised (tokenizer=%s).",
                name,
                type(pipe.model.tokenizer).__name__,
            )

    return after_init


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
