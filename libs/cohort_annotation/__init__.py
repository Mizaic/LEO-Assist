"""Cancer cohort annotation pipeline.

Multi-step LangGraph pipeline for generating gold NER annotations from
the cancer cohort encounters exported by
scripts/cohort/export_cancer_cohort_for_annotation.py.

Architecture:
  PreClassifier (deterministic) -> DeterministicExtractor (regex)
  -> StructuredVerify (Haiku) -> NarrativeNode (Haiku)
  -> Merge -> SpanClosure -> R16d RelationClosure
  -> [RelationLinker (Haiku, conditional)] -> Validators
  -> gold JSON

Entry points:
  libs.cohort_annotation.runner.annotate_encounter  - single encounter
  libs.cohort_annotation.runner.annotate_batch      - thread-pool batch
"""
