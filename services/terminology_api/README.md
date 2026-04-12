# Terminology API

FastAPI service for terminology lookup, value set operations, and coding support.

## Local run

```bash
uvicorn services.terminology_api.app.main:app --host 0.0.0.0 --port 8001 --reload
```

## CI/CD and ACA deployment

- Docker image: `leoaicr.azurecr.io/terminology-api`
- Container App name: `terminology-api`
- Dockerfile: `infra/dockerfiles/Dockerfile.terminology-api`

GitHub Actions build this image in `CI - Build and Push Images` and deploy it in
`CD - Deploy`.

To trigger the full pipeline for this service, commit a small change in this
folder (for example this README) and push to `main`, or run the workflows with
`workflow_dispatch`.
