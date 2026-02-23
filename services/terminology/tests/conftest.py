"""pytest configuration -- add project root to sys.path."""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Import component modules to trigger @Language.factory() registration.
import services.terminology.nlp.components.abbreviation_detector  # noqa: F401
import services.terminology.nlp.components.read_code_extractor  # noqa: F401
import services.terminology.nlp.components.entity_linker  # noqa: F401
import services.terminology.nlp.components.value_unit_extractor  # noqa: F401
import services.terminology.nlp.components.date_extractor  # noqa: F401
import services.terminology.nlp.components.confidence_scorer  # noqa: F401
