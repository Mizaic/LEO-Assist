"""Durable run spend rollup -- full-pipeline AuditEvent, not SBAR-only.

DI-9456E5BE: dashboard /analytics/llm-spend/runs reads AuditEvent.
The durable referral path only wrote SBAR tokens onto audit-{run_id},
so 16 Sep showed $0.68 while stages plus SBAR were $2.11 and Azure
billed about $3.49.
"""

from __future__ import annotations

from libs.workflow.run_llm_spend_rollup import (
    sum_stage_llm_usage,
    write_run_llm_spend_rollup,
)


def test_sum_stage_llm_usage_adds_every_step():
    rows = [
        {
            "step_id": "act-ref-extract",
            "metrics_json": (
                '{"llm_usage": {"input_tokens": 500000, "output_tokens": 10000,'
                ' "cached_input_tokens": 0, "llm_calls": 6, "cost_usd": 0.42}}'
            ),
        },
        {
            "step_id": "act-ref-sbar",
            "metrics_json": (
                '{"llm_usage": {"input_tokens": 280000, "output_tokens": 2000,'
                ' "cached_input_tokens": 0, "llm_calls": 4, "cost_usd": 0.22}}'
            ),
        },
        {"step_id": "act-ref-persist-facts", "metrics_json": '{"duration_ms": 12}'},
    ]
    totals = sum_stage_llm_usage(rows)
    assert totals["input_tokens"] == 780000
    assert totals["output_tokens"] == 12000
    assert totals["llm_calls"] == 10
    assert abs(totals["cost_usd"] - 0.64) < 1e-6


def test_write_run_llm_spend_rollup_overwrites_sbar_only_audit_event():
    runs: list[tuple[str, dict]] = []

    class _FakeClient:
        def run(self, query, **kwargs):
            runs.append((query, kwargs))
            if "HAS_STAGE" in query:
                return [
                    {
                        "step_id": "act-ref-extract",
                        "metrics_json": (
                            '{"llm_usage": {"input_tokens": 1000,'
                            ' "output_tokens": 20, "cached_input_tokens": 0,'
                            ' "llm_calls": 1, "cost_usd": 0.01}}'
                        ),
                    },
                    {
                        "step_id": "act-ref-sbar",
                        "metrics_json": (
                            '{"llm_usage": {"input_tokens": 2000,'
                            ' "output_tokens": 40, "cached_input_tokens": 0,'
                            ' "llm_calls": 2, "cost_usd": 0.02}}'
                        ),
                    },
                ]
            return []

    write_run_llm_spend_rollup(
        _FakeClient(),
        run_id="run-1",
        patient_id="p-1",
        encounter_id="e-1",
        status="completed",
    )
    writes = [kwargs for query, kwargs in runs if "AuditEvent" in query]
    assert writes, "expected an AuditEvent upsert"
    audit = writes[0]
    assert audit["id"] == "audit-run-1"
    assert audit["llm_input_tokens"] == 3000
    assert audit["llm_output_tokens"] == 60
    assert audit["llm_calls"] == 3
    assert abs(float(audit["llm_cost_usd"]) - 0.03) < 1e-6
