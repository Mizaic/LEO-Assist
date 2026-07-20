"""Read-only Cypher backing the "pick a rule" pickers in the rule editor.

Used by the RULE_FIRED logic-tree leaf (a rule can depend on another
rule having fired) and any other UI surface that needs a plain-English
list of active rules to choose from. This has no dependency on the
retired :TestPatient library.
"""

from __future__ import annotations

LIST_RULES_FOR_PICKER = """
MATCH (rule:AppropriatenessRule)
WHERE coalesce(rule.status, 'active') IN ['active', 'pending_review']
  AND ($guideline_id IS NULL OR
       EXISTS {
         MATCH (g:Guideline { id: $guideline_id })
               -[:HAS_RECOMMENDATION]->()-[:HAS_RULE]->(rule)
       })
OPTIONAL MATCH (rule)<-[:HAS_RULE]-(rec:Recommendation)
              <-[:HAS_RECOMMENDATION]-(g:Guideline)
OPTIONAL MATCH (rec)<-[:HAS_RECOMMENDATION]-(ch:Chapter)
OPTIONAL MATCH (rule)-[:HAS_ACTION_GROUP]->(:ActionGroup)
              -[ha:HAS_ACTION]->(_action_target)
RETURN rule.id                                AS rule_id,
       coalesce(rule.status, 'active')        AS status,
       rule.name                              AS name,
       rule.logicJson                         AS logic_json,
       rec.verbatim                           AS recommendation_text,
       ch.title                               AS chapter_title,
       ha.priority                            AS action_priority,
       g.id                                   AS guideline_id,
       g.title                                AS guideline_title
ORDER BY g.title, ch.title, rule.name
"""
