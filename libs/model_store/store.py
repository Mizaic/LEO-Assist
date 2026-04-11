"""Azure Blob Storage model artifact store.

A trained spaCy model directory is zipped, uploaded to a versioned blob path,
and downloaded+unzipped by the inference service at startup.  Hot-reload
works by downloading a new version while the old one serves traffic, then
atomically swapping the in-memory reference.

Blob path convention
--------------------
  {container}/{model_name}/{version}/model.tar.gz
  {container}/{model_name}/{version}/manifest.json   ← metadata sidecar

Environment variables
---------------------
AZURE_STORAGE_CONNECTION_STRING   Azure Blob Storage connection string.
                                  Preferred -- used when set (sourced from Key Vault
                                  in ACA; set locally in your .env / secrets/.env).
AZURE_STORAGE_ACCOUNT_URL         Azure Blob Storage account URL fallback.
                                  (e.g. https://leoaimodels.blob.core.windows.net)
                                  Uses DefaultAzureCredential (Managed Identity in ACA,
                                  az login locally). Used when connection string is absent.
MODEL_STORE_CONTAINER             Container name (default: "ner-models")
MODEL_STORE_MODEL_NAME            Model name prefix (default: "medspacy_clinical_ner")
MODEL_STORE_CACHE_DIR             Local directory for downloaded model cache
                                  (default: /tmp/model_cache)

Fallback / local dev
--------------------
Leave both AZURE_STORAGE_CONNECTION_STRING and AZURE_STORAGE_ACCOUNT_URL unset to
activate the local-filesystem fallback. The store will read/write from
MODEL_STORE_CACHE_DIR instead of blob.
"""

from __future__ import annotations

import io
import json
import logging
import os
import shutil
import tarfile
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_CONTAINER = os.getenv("MODEL_STORE_CONTAINER", "ner-models")
_MODEL_NAME = os.getenv("MODEL_STORE_MODEL_NAME", "medspacy_clinical_ner")
_CACHE_DIR = Path(os.getenv("MODEL_STORE_CACHE_DIR", "/tmp/model_cache"))
_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
_ACCOUNT_URL = os.getenv("AZURE_STORAGE_ACCOUNT_URL", "")

_ARCHIVE_NAME = "model.tar.gz"
_MANIFEST_NAME = "manifest.json"


@dataclass
class ModelArtifact:
    """Metadata sidecar stored alongside each model version in blob."""

    model_name: str
    version: str
    blob_path: str  # e.g. "medspacy_clinical_ner/1.2/model.tar.gz"
    schema_version: str = ""
    deid_version: str = ""
    label_mapping_version: str = ""
    dataset_version: str = ""
    size_bytes: int = 0
    uploaded_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    notes: str = ""

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ModelArtifact":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class ModelStore:
    """Versioned model artifact store backed by Azure Blob Storage.

    Falls back to local filesystem when no connection string is configured.
    """

    def __init__(self) -> None:
        self._container = _CONTAINER
        self._model_name = _MODEL_NAME
        self._cache_dir = _CACHE_DIR
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._blob_client = self._init_blob_client()

    def _init_blob_client(self):
        try:
            from azure.storage.blob import BlobServiceClient

            if _CONNECTION_STRING:
                client = BlobServiceClient.from_connection_string(_CONNECTION_STRING)
                logger.info(
                    "ModelStore: connected via connection string, container=%s",
                    self._container,
                )
            elif _ACCOUNT_URL:
                from libs.azure.credentials import get_credential

                client = BlobServiceClient(
                    account_url=_ACCOUNT_URL, credential=get_credential()
                )
                logger.info(
                    "ModelStore: connected via account URL + managed identity, container=%s",
                    self._container,
                )
            else:
                logger.info(
                    "ModelStore: no Azure credentials set -- using local filesystem at %s",
                    self._cache_dir,
                )
                return None

            try:
                client.create_container(self._container)
            except Exception:
                pass  # container already exists
            return client

        except Exception:
            logger.warning(
                "ModelStore: failed to init Azure Blob client -- falling back to local FS",
                exc_info=True,
            )
            return None

    # ------------------------------------------------------------------
    # Upload
    # ------------------------------------------------------------------

    def upload(
        self,
        model_dir: str | Path,
        version: str,
        *,
        schema_version: str = "",
        deid_version: str = "",
        label_mapping_version: str = "",
        dataset_version: str = "",
        notes: str = "",
    ) -> str:
        """Upload a trained spaCy model directory to the store.

        Args:
            model_dir: Local path to the trained model directory.
            version: Version string (e.g. "1.2").

        Returns:
            The canonical blob path URI for the uploaded model archive.
        """
        model_dir = Path(model_dir)
        if not model_dir.exists():
            raise FileNotFoundError(
                f"ModelStore.upload: model_dir not found: {model_dir}"
            )

        blob_prefix = f"{self._model_name}/{version}"
        archive_blob = f"{blob_prefix}/{_ARCHIVE_NAME}"

        # Zip the model directory into a temp file
        with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            with tarfile.open(tmp_path, "w:gz") as tar:
                tar.add(model_dir, arcname=self._model_name)

            size_bytes = tmp_path.stat().st_size
            logger.info(
                "ModelStore.upload: model=%s v%s size=%.1fMB",
                self._model_name,
                version,
                size_bytes / 1_048_576,
            )

            # Build metadata
            artifact = ModelArtifact(
                model_name=self._model_name,
                version=version,
                blob_path=archive_blob,
                schema_version=schema_version,
                deid_version=deid_version,
                label_mapping_version=label_mapping_version,
                dataset_version=dataset_version,
                size_bytes=size_bytes,
                notes=notes,
            )

            if self._blob_client:
                self._upload_to_blob(tmp_path, archive_blob)
                self._upload_manifest(artifact, f"{blob_prefix}/{_MANIFEST_NAME}")
            else:
                self._upload_local(tmp_path, archive_blob)
                self._upload_manifest_local(artifact, blob_prefix)

        finally:
            tmp_path.unlink(missing_ok=True)

        logger.info("ModelStore.upload: uploaded %s", archive_blob)
        return archive_blob

    def _upload_to_blob(self, local_path: Path, blob_name: str) -> None:
        container_client = self._blob_client.get_container_client(self._container)
        with local_path.open("rb") as f:
            container_client.upload_blob(blob_name, f, overwrite=True)

    def _upload_manifest(self, artifact: ModelArtifact, blob_name: str) -> None:
        container_client = self._blob_client.get_container_client(self._container)
        data = json.dumps(artifact.to_dict(), indent=2).encode("utf-8")
        container_client.upload_blob(blob_name, data, overwrite=True)

    def _upload_local(self, src: Path, blob_name: str) -> None:
        dest = self._local_path(blob_name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)

    def _upload_manifest_local(self, artifact: ModelArtifact, prefix: str) -> None:
        dest = self._local_path(f"{prefix}/{_MANIFEST_NAME}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(artifact.to_dict(), indent=2), encoding="utf-8")

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------

    def download(
        self,
        version: str,
        *,
        force: bool = False,
    ) -> Path:
        """Download and unpack a model version to the local cache directory.

        Returns the path to the unpacked model directory.  If the version
        is already cached locally, skip the download unless ``force=True``.

        Args:
            version: Version string to download.
            force: Re-download even if cached.

        Returns:
            Path to the local unpacked model directory.
        """
        local_model_dir = (
            self._cache_dir / self._model_name / version / self._model_name
        )

        if local_model_dir.exists() and not force:
            logger.info(
                "ModelStore.download: v%s already cached at %s",
                version,
                local_model_dir,
            )
            return local_model_dir

        blob_prefix = f"{self._model_name}/{version}"
        archive_blob = f"{blob_prefix}/{_ARCHIVE_NAME}"
        unpack_dir = self._cache_dir / self._model_name / version

        unpack_dir.mkdir(parents=True, exist_ok=True)

        if self._blob_client:
            archive_bytes = self._download_from_blob(archive_blob)
        else:
            archive_bytes = self._download_local(archive_blob)

        logger.info(
            "ModelStore.download: unpacking v%s (%.1fMB) to %s",
            version,
            len(archive_bytes) / 1_048_576,
            unpack_dir,
        )
        with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as tar:
            tar.extractall(unpack_dir)

        if not local_model_dir.exists():
            raise RuntimeError(
                f"ModelStore.download: expected model dir at {local_model_dir} after unpack"
            )

        logger.info("ModelStore.download: v%s ready at %s", version, local_model_dir)
        return local_model_dir

    def _download_from_blob(self, blob_name: str) -> bytes:
        container_client = self._blob_client.get_container_client(self._container)
        blob_client = container_client.get_blob_client(blob_name)
        downloader = blob_client.download_blob()
        return downloader.readall()

    def _download_local(self, blob_name: str) -> bytes:
        src = self._local_path(blob_name)
        if not src.exists():
            raise FileNotFoundError(f"ModelStore: local artifact not found: {src}")
        return src.read_bytes()

    # ------------------------------------------------------------------
    # List / metadata
    # ------------------------------------------------------------------

    def list_versions(self) -> list[ModelArtifact]:
        """Return all uploaded model versions, newest first."""
        if self._blob_client:
            return self._list_blob_versions()
        return self._list_local_versions()

    def get_manifest(self, version: str) -> Optional[ModelArtifact]:
        """Return the artifact metadata for a version, or None."""
        blob_name = f"{self._model_name}/{version}/{_MANIFEST_NAME}"
        try:
            if self._blob_client:
                data = self._download_from_blob(blob_name)
                return ModelArtifact.from_dict(json.loads(data.decode("utf-8")))
            local = self._local_path(blob_name)
            if local.exists():
                return ModelArtifact.from_dict(
                    json.loads(local.read_text(encoding="utf-8"))
                )
        except Exception:
            logger.warning(
                "ModelStore.get_manifest: failed for v%s", version, exc_info=True
            )
        return None

    def _list_blob_versions(self) -> list[ModelArtifact]:
        container_client = self._blob_client.get_container_client(self._container)
        prefix = f"{self._model_name}/"
        manifests: list[ModelArtifact] = []
        for blob in container_client.list_blobs(name_starts_with=prefix):
            if blob.name.endswith(f"/{_MANIFEST_NAME}"):
                try:
                    data = self._download_from_blob(blob.name)
                    manifests.append(
                        ModelArtifact.from_dict(json.loads(data.decode("utf-8")))
                    )
                except Exception:
                    pass
        return sorted(manifests, key=lambda a: a.uploaded_at, reverse=True)

    def _list_local_versions(self) -> list[ModelArtifact]:
        base = self._local_path(self._model_name)
        if not base.exists():
            return []
        manifests: list[ModelArtifact] = []
        for version_dir in base.iterdir():
            m = version_dir / _MANIFEST_NAME
            if m.exists():
                try:
                    manifests.append(
                        ModelArtifact.from_dict(
                            json.loads(m.read_text(encoding="utf-8"))
                        )
                    )
                except Exception:
                    pass
        return sorted(manifests, key=lambda a: a.uploaded_at, reverse=True)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _local_path(self, blob_name: str) -> Path:
        return self._cache_dir / blob_name
