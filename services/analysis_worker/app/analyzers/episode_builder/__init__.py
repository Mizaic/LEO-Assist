"""Episode builder package -- backward-compatible re-export facade.

All public and test-visible symbols are re-exported here so that
``from services.analysis_worker.app.analyzers.episode_builder import X``
continues to work unchanged.
"""

from __future__ import annotations

from datetime import date

# -- Test hook (set by tests via ``eb._TODAY_OVERRIDE = date(...)``) ---------
_TODAY_OVERRIDE: date | None = None

# -- Config constants (re-exported for tests that reference them) -----------
from ._config import (  # noqa: E402
    DIAG_LOOKBACK_DAYS as _DIAG_LOOKBACK_DAYS,
    FALLBACK_REASON_WINDOW_DAYS_AFTER as _FALLBACK_REASON_WINDOW_DAYS_AFTER,
    FALLBACK_REASON_WINDOW_DAYS_BEFORE as _FALLBACK_REASON_WINDOW_DAYS_BEFORE,
    FIRST_PRESENTATION_LOOKBACK_DAYS as _FIRST_PRESENTATION_LOOKBACK_DAYS,
    INFERENCE_POST_WINDOW_DAYS as _INFERENCE_POST_WINDOW_DAYS,
    LETTER_WITHIN_DAYS_AFTER_VISIT as _LETTER_WITHIN_DAYS_AFTER_VISIT,
    MAX_BENIGN_CLOSURE_DAYS as _MAX_BENIGN_CLOSURE_DAYS,
    MAX_DAYS_PRESENTATION_TO_REFERRAL as _MAX_DAYS_PRESENTATION_TO_REFERRAL,
    NO_CANCER_CONCEPT_ID as _NO_CANCER_CONCEPT_ID,
    NO_TREATMENT_WINDOW_AFTER_LETTER_DAYS as _NO_TREATMENT_WINDOW_AFTER_LETTER_DAYS,
    PHANTOM_COMPLETED_WINDOW as _PHANTOM_COMPLETED_WINDOW,
    SAME_EPISODE_DAYS as _SAME_EPISODE_DAYS,
    STALE_HARD_DAYS as _STALE_HARD_DAYS,
    STALE_POST_SPECIALIST_DAYS as _STALE_POST_SPECIALIST_DAYS,
    _today_for_episode_rules,
)

# -- Types ------------------------------------------------------------------
from ._types import (  # noqa: E402
    BuildContext,
    EpisodeBuildResult,
    WriteEpisodeParams,
    _EpisodeSpec,
    _SpecialistClaim,
    _episode_id,
    _parse_date,
)

# -- Site resolution --------------------------------------------------------
from ._site_resolution import (  # noqa: E402
    _DESCENDANT_SITE_MAP,
    _GENERIC_CANCER_TERMS,
    _PATHWAY_GROUP_KEYS,
    _PATHWAY_TO_SPECIFIC,
    _SITE_BY_CONCEPT_ID,
    _SITE_MAP,
    _extract_condition_key,
    _extract_condition_key_from_anchor,
    _referral_route_from_concept,
    _site_keys_compatible,
)

# -- Grouping ---------------------------------------------------------------
from ._grouping import (  # noqa: E402
    _build_diagnosis_led_groups,
    _claim_specialists_for_episodes,
    _claim_window_referrals,
    _detect_phantom_sites,
    _find_best_referral,
    _group_open_referrals,
    _group_referrals_by_time,
)

# -- Cypher queries (re-exported with underscore prefix for compat) ---------
from ._cypher import (  # noqa: E402
    BENIGN_CLOSURE_QUERY as _BENIGN_CLOSURE_QUERY,
    FETCH_EPISODES_FOR_MERGE_Q as _FETCH_EPISODES_FOR_MERGE_Q,
    INFERENCE_ENC_Q as _INFERENCE_ENC_Q,
    INFERENCE_FETCH_Q as _INFERENCE_FETCH_Q,
    INFERENCE_UPDATE_Q as _INFERENCE_UPDATE_Q,
    LINK_ENCOUNTERS as _LINK_ENCOUNTERS,
    MARK_MERGED_Q as _MARK_MERGED_Q,
    MERGE_EPISODE as _MERGE_EPISODE,
    REFERRAL_CONTEXT_TEXT_Q as _REFERRAL_CONTEXT_TEXT_Q,
    RELATED_CLOSE_Q as _RELATED_CLOSE_Q,
    STALE_CLOSE_Q as _STALE_CLOSE_Q,
)

# -- Persistence ------------------------------------------------------------
from ._persistence import (  # noqa: E402
    _benign_closure_for_episode,
    _link_encounters_to_episode,
    _write_episode,
)

# -- Status -----------------------------------------------------------------
from ._status import (  # noqa: E402
    _cancer_diag_anchors,
    _determine_episode_status,
    _has_confirmed_diagnosis,
    _has_possible_only_diagnosis,
    _infer_completed_from_specialist_letter,
    _treatment_after_referral,
    _treatment_between,
)

# -- First presentation -----------------------------------------------------
from ._first_presentation import (  # noqa: E402
    _anchor_in_pre_referral_window,
    _anchor_is_complaint,
    _anchor_is_investigation,
    _anchor_is_place,
    _anchor_is_present,
    _anchor_tag,
    _first_presentation_from_anchors,
    _first_presentation_from_referral_context,
)

# -- Auto-close -------------------------------------------------------------
from ._auto_close import (  # noqa: E402
    _apply_auto_close_rules,
    _apply_outcome_inference,
    _merge_same_site_duplicates,
)

# -- Builder (public API) ---------------------------------------------------
from ._builder import (  # noqa: E402
    _build_closed_episode,
    _build_open_episode,
    _closed_episode_spec,
    _open_episode_spec,
    build_episodes,
)

__all__ = [
    "build_episodes",
    "EpisodeBuildResult",
]
