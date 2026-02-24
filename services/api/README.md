# Training Creator HITL API (MVP)

## Run

```bash
pip install -r services/api/requirements.txt
uvicorn app.main:app --app-dir services/api --reload --port 8000
```

## Key Endpoints

- `POST /pipeline/run`
- `GET /review/tasks`
- `GET /review/tasks/{task_id}`
- `POST /review/tasks/{task_id}/decision`
- `GET /audit/candidate/{candidate_id}`
- `POST /exports/dataset`

## Notes

- Neo4j is the only state store.
- Approval and change events are append-only by design.
- Only approved candidates should be used for dataset exports.
