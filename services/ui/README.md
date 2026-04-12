# Training Creator HITL UI (MVP)

## Run

```bash
cd services/ui
npm install
npm run dev
```

Set `VITE_API_BASE` if API is not at `http://localhost:8000`.

## Features

- Review queue list
- Encounter/span highlighting
- Coding/context proposal table
- Approve/edit/reject/escalate submission
- Audit timeline panel

## CI/CD and ACA deployment

- Docker image: `leoaicr.azurecr.io/ui`
- Container App name: `ui`
- Dockerfile: `infra/dockerfiles/Dockerfile.ui`

GitHub Actions build this image in `CI - Build and Push Images` and deploy it in
`CD - Deploy`.

To trigger the full pipeline for this service, commit a small change in this
folder (for example `services/ui/README.md`) and push to `main`, or run the
workflows with `workflow_dispatch`.
