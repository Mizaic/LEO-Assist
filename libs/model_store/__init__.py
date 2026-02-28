"""Model artifact store — Azure Blob Storage backend.

Models are never shipped in the Docker image or trained at runtime.
Upload once from the training pipeline; the inference service downloads
at startup and hot-reloads on demand.

Public API
----------
    from libs.model_store import ModelStore

    store = ModelStore()

    # Training pipeline: push a trained model directory
    uri = store.upload("models/medspacy_clinical_ner/v1.2", "1.2")

    # Inference service: download to a local temp dir at startup
    local_path = store.download("1.2")

    # List available versions
    versions = store.list_versions()
"""

from libs.model_store.store import ModelStore, ModelArtifact

__all__ = ["ModelStore", "ModelArtifact"]
