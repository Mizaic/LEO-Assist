This directory is for local training outputs only. Do not commit model weights
(transformer, spancat, etc.); they exceed Git and GitHub limits.

Canonical store: Azure Blob via libs/model_store (versioned model.tar.gz + manifest).

- Production path: the training worker uploads after training
  (services/training_worker/app/job_runner.py, phase "upload").

- Manual or ad-hoc: from repo root, with Azure env from .env.example:
    python scripts/upload_model.py --version YOUR_VERSION --model-dir PATH_TO_model-best

- Runtime: services download to MODEL_STORE_CACHE_DIR (default /tmp/model_cache).

For local dev without Azure, ModelStore uses MODEL_STORE_CACHE_DIR on disk
(AZURE_STORAGE_* unset). Still keep that tree out of git.
