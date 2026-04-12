# Services and CI/CD map

This file maps each deployed service to its Docker image and Azure Container App.
It is the quickest way to validate end-to-end GitHub Actions coverage.

## Startup script parity

Local startup script: `scripts/start_leo-ai-core.sh`

Services started by the script and deployed via GitHub Actions:

- `api` -> image/app `core-api`
- `terminology_api` -> image/app `terminology-api`
- `fhir_api` -> image/app `fhir-api`
- `analytics_api` -> image/app `analytics-api`
- `model_inference` -> image/app `model-inference`
- `training_worker` -> image/app `training-worker`
- `pipeline_worker` -> image/app `pipeline-worker`
- `ui` -> image/app `ui`

## Trigger all service pipelines

1. Make a small README-only change in each service folder:
   - `services/api/README.md`
   - `services/terminology_api/README.md`
   - `services/fhir_api/README.md`
   - `services/analytics_api/README.md`
   - `services/model_inference/README.md`
   - `services/training_worker/README.md`
   - `services/pipeline_worker/README.md`
   - `services/ui/README.md`
2. Push to `main` to trigger:
   - `CI - Build and Push Images`
   - `CD - Deploy` (dev automatic on successful CI run)
3. For validation or production, run `CD - Deploy` with `workflow_dispatch` and
   choose `environment=val` or `environment=prod`.
