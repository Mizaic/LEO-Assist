FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY services/ods_sync/requirements.txt /app/requirements-ods-sync.txt
RUN pip install --no-cache-dir -r requirements-ods-sync.txt

# Copy shared libs and service code
COPY libs/ /app/libs/
COPY services/ods_sync/ /app/services/ods_sync/

# Set PYTHONPATH so libs.* and services.ods_sync.* resolve correctly
ENV PYTHONPATH=/app

CMD ["python", "-m", "services.ods_sync.app.main"]
