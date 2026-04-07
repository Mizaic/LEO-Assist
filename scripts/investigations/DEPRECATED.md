# DEPRECATED -- Investigation Scripts

The one-off investigation scripts in this directory are superseded by the
**Data Quality Toolkit** (DI-LEO-AI-089, implemented April 2026).

Use the API, MCP server, or admin UI instead:

| Old script pattern | New capability |
|--------------------|----------------|
| `_check_ep_props.py`, `_debug_stale_episodes.py`, `_stale_*` | `GET /admin/dq/episodes/stale` or `dq_episodes_stale` MCP tool |
| `_patient_*_breakdown.py`, `_patient_enc_raw.py` | `GET /admin/dq/patient/{id}` or `dq_patient_inspect` MCP tool |
| `_patient_180d_inference_scan.py`, `_stale_post_spec_detail.py` | `GET /admin/dq/episodes/infer-outcome` or `dq_episodes_infer_outcome` MCP tool |
| `_audit_orphan_concept_codes.py`, `_find_all_orphan_concepts.py` | `GET /admin/dq/domain/orphans` or `dq_domain_orphans` MCP tool |
| `_check_expansion_coverage.py`, `_check_isa_expansion.py` | `GET /admin/dq/domain/coverage` |
| `_check_diagnosis_coverage.py`, `_cancer_diagnosis_truth.py` | `GET /admin/dq/rules/run` (SAFE-001, COVE-001) |
| `_seed_*.py` (surface form seeding) | `/admin/dq/terminology/sf/*` endpoints |
| `_count_patients.py`, `_multi_episode_patients.py` | `GET /admin/dq/sitrep` or `GET /admin/dq/cohort` |
| `_episode_report.py` | `GET /admin/dq/episodes/health` + `/admin/dq/episodes/completeness` |
| `_encounter_text_audit.py`, `_check_encounter_text.py` | `GET /admin/dq/patient/{id}/encounters?with_text=true` |
| `_check_active_filter.py`, `_check_documents_nodes.py` | `GET /admin/dq/rules/run` (REFI-001, VALD-001) |

## Retirement schedule

- **Cycle 1 (current)**: Deprecation notices added. Scripts remain on disk.
- **Cycle 2 (next sprint)**: Scripts moved to `scripts/investigations/_archive/`.
- **Cycle 3**: Archive deleted after team confirms full adoption of toolkit.

## Admin UI

Access at `/admin/data-quality` (platform admin only).

## MCP (Cursor)

Add to `~/.cursor/mcp.json`:
```json
{
  "mcpServers": {
    "leo-dq": {
      "command": "python",
      "args": ["-m", "services.dq_mcp.server"],
      "cwd": "C:/path/to/LEO-AI-CORE",
      "env": {
        "DQ_API_BASE_URL": "http://localhost:8000",
        "DQ_API_COOKIE": "session=<your-admin-session-cookie>"
      }
    }
  }
}
```
