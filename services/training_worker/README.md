# Training Worker Service

FastAPI service for training orchestration, job tracking, and model lifecycle work.

## Local run

```bash
uvicorn app.main:app --app-dir services/training_worker --host 0.0.0.0 --port 8005
```

## CI/CD and ACA deployment

- Docker image: `leoaicr.azurecr.io/training-worker`
- Container App name: `training-worker`
- Dockerfile: `infra/dockerfiles/Dockerfile.training-worker`

GitHub Actions build this image in `CI - Build and Push Images` and deploy it in
`CD - Deploy`.

To trigger the full pipeline for this service, commit a small change in this
folder (for example this README) and push to `main`, or run the workflows with
`workflow_dispatch`.
