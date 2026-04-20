"""Cypher queries for phrase-level multi-label approval policy.

Atlas trace:
  DO: DO-BE96444E
  DI: DI-BAC284B4
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-BE96444E")
"""

LIST_PHRASE_MULTILABEL_APPROVALS = """
MATCH (p:PhraseMultiLabelApproval)
RETURN
    p.phrase_norm AS phrase_norm,
    p.phrase_display AS phrase_display,
    coalesce(p.allowed_labels, []) AS allowed_labels,
    toString(p.created_at) AS created_at,
    p.created_by AS created_by,
    toString(p.updated_at) AS updated_at,
    p.updated_by AS updated_by
ORDER BY p.phrase_norm ASC
"""


UPSERT_PHRASE_MULTILABEL_APPROVAL = """
MERGE (p:PhraseMultiLabelApproval {phrase_norm: $phrase_norm})
ON CREATE SET
    p.id = $id,
    p.phrase_display = $phrase_display,
    p.allowed_labels = $allowed_labels,
    p.created_at = datetime(),
    p.created_by = $updated_by,
    p.updated_at = datetime(),
    p.updated_by = $updated_by
ON MATCH SET
    p.phrase_display = $phrase_display,
    p.allowed_labels = $allowed_labels,
    p.updated_at = datetime(),
    p.updated_by = $updated_by
RETURN
    p.phrase_norm AS phrase_norm,
    p.phrase_display AS phrase_display,
    coalesce(p.allowed_labels, []) AS allowed_labels
"""


DELETE_PHRASE_MULTILABEL_APPROVAL = """
MATCH (p:PhraseMultiLabelApproval {phrase_norm: $phrase_norm})
WITH p
DELETE p
RETURN count(*) AS deleted
"""
