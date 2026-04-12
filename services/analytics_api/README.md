# Analytics API

FastAPI service for analytics endpoints consumed by the platform UI and API.

## Local run

```bash
uvicorn services.analytics_api.app.main:app --host 0.0.0.0 --port 8003 --reload
```

## CI/CD and ACA deployment

- Docker image: `leoaicr.azurecr.io/analytics-api`
- Container App name: `analytics-api`
- Dockerfile: `infra/dockerfiles/Dockerfile.analytics-api`

GitHub Actions build this image in `CI - Build and Push Images` and deploy it in
`CD - Deploy`.

To trigger the full pipeline for this service, commit a small change in this
folder (for example this README) and push to `main`, or run the workflows with
`workflow_dispatch`.
