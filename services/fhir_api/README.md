# FHIR API

FastAPI service that exposes FHIR-aligned data and benchmark endpoints.

## Local run

```bash
uvicorn services.fhir_api.app.main:app --host 0.0.0.0 --port 8002 --reload
```

## CI/CD and ACA deployment

- Docker image: `leoaicr.azurecr.io/fhir-api`
- Container App name: `fhir-api`
- Dockerfile: `infra/dockerfiles/Dockerfile.fhir-api`

GitHub Actions build this image in `CI - Build and Push Images` and deploy it in
`CD - Deploy`.

To trigger the full pipeline for this service, commit a small change in this
folder (for example this README) and push to `main`, or run the workflows with
`workflow_dispatch`.
