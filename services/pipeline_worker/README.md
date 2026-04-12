# Pipeline Worker Service

FastAPI service that executes asynchronous pipeline jobs from the message bus.

## Local run

```bash
uvicorn services.pipeline_worker.app.main:app --host 0.0.0.0 --port 8006
```

## CI/CD and ACA deployment

- Docker image: `leoaicr.azurecr.io/pipeline-worker`
- Container App name: `pipeline-worker`
- Dockerfile: `infra/dockerfiles/Dockerfile.pipeline-worker`

GitHub Actions build this image in `CI - Build and Push Images` and deploy it in
`CD - Deploy`.

To trigger the full pipeline for this service, commit a small change in this
folder (for example this README) and push to `main`, or run the workflows with
`workflow_dispatch`.
