# Model Inference Service

FastAPI service that hosts model inference endpoints used by coding workflows.

## Local run

```bash
uvicorn app.main:app --app-dir services/model_inference --host 0.0.0.0 --port 8004
```

## CI/CD and ACA deployment

- Docker image: `leoaicr.azurecr.io/model-inference`
- Container App name: `model-inference`
- Dockerfile: `infra/dockerfiles/Dockerfile.model-inference`

GitHub Actions build this image in `CI - Build and Push Images` and deploy it in
`CD - Deploy`.

To trigger the full pipeline for this service, commit a small change in this
folder (for example this README) and push to `main`, or run the workflows with
`workflow_dispatch`.
