"""Redis-backed Roaring bitmap store for guideline evaluation.

Key scheme:
    rbm:{blake2b_16_hex}                                  -- serialised pyroaring BitMap bytes
    snomed:intids                                         -- Redis hash: concept_id -> int_id
    snomed:intids:next                                    -- atomic counter for int_id assignment
    ruleset:{scope_token}:{version}                       -- JSON ruleset dict
    ruleset:current:{scope_token}                         -- pointer to active ruleset version name

Scope token format:
    {scope_type}:{scope_id}
    e.g. guideline:NG12, domain:cancer_audit, subdomain:cancer_audit:symptoms
"""

from __future__ import annotations

import hashlib
import json
import logging
import os

import redis
from pyroaring import BitMap

logger = logging.getLogger(__name__)

_RBM_PREFIX = "rbm:"
_INTIDS_KEY = "snomed:intids"
_INTIDS_NEXT = "snomed:intids:next"
_RULESET_PREFIX = "ruleset:"
_CURRENT_KEY = "ruleset:current"
_DEFAULT_SCOPE_TYPE = "global"
_DEFAULT_SCOPE_ID = "default"


def _get_client(url: str | None = None) -> redis.Redis:
    return redis.from_url(
        url or os.getenv("REDIS_URL", "redis://localhost:6379"),
        decode_responses=False,
        socket_connect_timeout=5,
        socket_timeout=5,
        retry_on_timeout=True,
    )


def _bitmap_key(bitmap_id: str) -> str:
    return f"{_RBM_PREFIX}{bitmap_id}"


def _ruleset_key(version: str) -> str:
    return f"{_RULESET_PREFIX}{version}"


def _normalise_scope(scope_type: str | None = None, scope_id: str | None = None) -> tuple[str, str]:
    st = str(scope_type or _DEFAULT_SCOPE_TYPE).strip().lower() or _DEFAULT_SCOPE_TYPE
    sid = str(scope_id or _DEFAULT_SCOPE_ID).strip() or _DEFAULT_SCOPE_ID
    return st, sid


def _scope_token(scope_type: str | None = None, scope_id: str | None = None) -> str:
    st, sid = _normalise_scope(scope_type, scope_id)
    return f"{st}:{sid}"


def _scoped_ruleset_key(version: str, scope_type: str | None = None, scope_id: str | None = None) -> str:
    return f"{_RULESET_PREFIX}{_scope_token(scope_type, scope_id)}:{version}"


def _scoped_current_key(scope_type: str | None = None, scope_id: str | None = None) -> str:
    return f"{_CURRENT_KEY}:{_scope_token(scope_type, scope_id)}"


class BitmapStore:
    """Redis-backed Roaring bitmap persistence.

    Uses BLAKE2b hashing to assign deterministic Redis keys to bitmaps,
    so identical sets of integer IDs always map to the same storage key.
    """

    def __init__(self, redis_url: str | None = None) -> None:
        self._url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379")

    def _client(self) -> redis.Redis:
        return _get_client(self._url)

    def put_bitmap(self, int_ids: list[int]) -> str:
        """Store a BitMap and return its deterministic key.

        Args:
            int_ids: Sorted list of integer SNOMED concept IDs.

        Returns:
            BLAKE2b hex digest used as the Redis key suffix.
        """
        bm = BitMap(int_ids)
        raw = bytes(bm.serialize())
        digest = hashlib.blake2b(raw, digest_size=8).hexdigest()
        key = _bitmap_key(digest)
        client = self._client()
        if not client.exists(key):
            client.set(key, raw)
        return digest

    def get_bitmap(self, bitmap_id: str) -> BitMap | None:
        """Retrieve a BitMap by its key digest.

        Args:
            bitmap_id: BLAKE2b digest returned by :meth:`put_bitmap`.

        Returns:
            Deserialised :class:`pyroaring.BitMap`, or ``None`` if not found.
        """
        client = self._client()
        raw = client.get(_bitmap_key(bitmap_id))
        if raw is None:
            return None
        return BitMap.deserialize(raw)

    def get_or_assign_int_id(self, concept_id: str) -> int:
        """Return existing int_id for a SNOMED concept, or assign a new one.

        Thread-safe via atomic Redis INCR.

        Args:
            concept_id: SNOMED concept ID string (e.g. ``443416000``).

        Returns:
            Stable integer identifier for the concept.
        """
        client = self._client()
        existing = client.hget(_INTIDS_KEY, concept_id)
        if existing is not None:
            return int(existing)
        new_id = client.incr(_INTIDS_NEXT)
        client.hset(_INTIDS_KEY, concept_id, new_id)
        return new_id

    def get_int_id(self, concept_id: str) -> int | None:
        """Look up an existing int_id without creating a new one.

        Args:
            concept_id: SNOMED concept ID string.

        Returns:
            Integer ID or ``None`` if the concept has not been indexed.
        """
        client = self._client()
        value = client.hget(_INTIDS_KEY, concept_id)
        return int(value) if value is not None else None

    def write_ruleset(
        self,
        version: str,
        ruleset: dict,
        *,
        scope_type: str | None = None,
        scope_id: str | None = None,
    ) -> None:
        """Persist a compiled ruleset under the given version name.

        Args:
            version: Ruleset version string (e.g. ``v20260308-1``).
            ruleset: Ruleset dict produced by :class:`GuidelineCompiler`.
        """
        client = self._client()
        payload = dict(ruleset)
        st, sid = _normalise_scope(scope_type, scope_id)
        payload.setdefault("scope_type", st)
        payload.setdefault("scope_id", sid)
        client.set(_scoped_ruleset_key(version, st, sid), json.dumps(payload))

    def get_ruleset(
        self,
        version: str,
        *,
        scope_type: str | None = None,
        scope_id: str | None = None,
    ) -> dict | None:
        """Load a ruleset by version name.

        Args:
            version: Version string.

        Returns:
            Ruleset dict, or ``None`` if not found.
        """
        client = self._client()
        raw = client.get(_scoped_ruleset_key(version, scope_type, scope_id))
        if raw is None and (scope_type is None and scope_id is None):
            # Backward compatibility for old global key format.
            raw = client.get(_ruleset_key(version))
        return json.loads(raw) if raw else None

    def get_current_ruleset(
        self,
        *,
        scope_type: str | None = None,
        scope_id: str | None = None,
    ) -> dict | None:
        """Load the currently active ruleset.

        Returns:
            Active ruleset dict, or ``None`` if no version is active.
        """
        client = self._client()
        version = client.get(_scoped_current_key(scope_type, scope_id))
        if not version and (scope_type is None and scope_id is None):
            # Backward compatibility for old global pointer key.
            version = client.get(_CURRENT_KEY)
        if not version:
            return None
        version_str = version.decode() if isinstance(version, bytes) else version
        return self.get_ruleset(version_str, scope_type=scope_type, scope_id=scope_id)

    def set_current_version(
        self,
        version: str,
        *,
        scope_type: str | None = None,
        scope_id: str | None = None,
    ) -> None:
        """Point the active-version pointer at a compiled ruleset.

        Args:
            version: Version string that must already exist in Redis.
        """
        client = self._client()
        client.set(_scoped_current_key(scope_type, scope_id), version)

    def list_versions(
        self,
        *,
        scope_type: str | None = None,
        scope_id: str | None = None,
    ) -> list[str]:
        """Return all compiled ruleset version names.

        Returns:
            List of version strings in lexicographic order.
        """
        client = self._client()
        token = _scope_token(scope_type, scope_id)
        prefix = f"{_RULESET_PREFIX}{token}:"
        keys = client.keys(f"{prefix}*")
        prefix_len = len(prefix)
        versions: list[str] = []
        for k in keys:
            name = k.decode() if isinstance(k, bytes) else k
            if not name.startswith(prefix):
                continue
            versions.append(name[prefix_len:])

        if scope_type is None and scope_id is None and not versions:
            # Backward compatibility for legacy global keys.
            old_keys = client.keys(f"{_RULESET_PREFIX}*")
            old_prefix_len = len(_RULESET_PREFIX)
            versions = [
                (k.decode() if isinstance(k, bytes) else k)[old_prefix_len:]
                for k in old_keys
                if (k.decode() if isinstance(k, bytes) else k) != _CURRENT_KEY
                and ":" not in (k.decode() if isinstance(k, bytes) else k)[old_prefix_len:]
            ]
        return sorted(versions)

    def get_current_version_name(
        self,
        *,
        scope_type: str | None = None,
        scope_id: str | None = None,
    ) -> str | None:
        """Return the name of the currently active version, or None."""
        client = self._client()
        raw = client.get(_scoped_current_key(scope_type, scope_id))
        if raw is None and (scope_type is None and scope_id is None):
            raw = client.get(_CURRENT_KEY)
        if raw is None:
            return None
        return raw.decode() if isinstance(raw, bytes) else raw
