# ── NER Model Inference Service ──────────────────────────────────────────────
#
# No model files in the image.  The model is downloaded from Azure Blob Storage
# at startup based on CODING_MODEL_VERSION.  To update the model:
#   1. Train and upload: python scripts/upload_model.py --version 1.3
#   2. Update CODING_MODEL_VERSION env var on the running container (or /reload)
#   3. No image rebuild required.
#
FROM python:3.11-slim

WORKDIR /app

# System deps for spaCy
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libgomp1 && \
    rm -rf /var/lib/apt/lists/*

COPY services/model_inference/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Copy only source code — no model weights
COPY libs/ /app/libs/
COPY services/model_inference/app/ /app/app/

# Local model cache — populated at runtime from blob, not from the image.
# Mount a persistent volume here in production for faster restarts.
ENV MODEL_STORE_CACHE_DIR=/var/model_cache
RUN mkdir -p /var/model_cache

EXPOSE 8004

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8004"]
