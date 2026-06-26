"""Redis-backed Roaring bitmap store for guideline evaluation.

Atlas trace:
  DO: DO-E74B0605
  DI: DI-5E25E872
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-E74B0605")

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
import threading

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

# Module-level cache so every BitmapStore instance reuses the SAME
# redis.Redis (and therefore the SAME ConnectionPool) per URL.
#
# Why this matters: REDIS_URL points at Azure Cache for Redis over
# rediss:// in dev / staging / prod (see secrets/.env.secrets), so
# every fresh client opens a new TCP connection and a fresh TLS
# handshake (~100-300ms over UK-South). Without pooling, /evaluate's
# per-leaf bitmap reads + per-code int_id lookups multiplied that
# cost by N and could push a single replay request past the caller's
# 30s timeout. Caching the client lets redis-py's ConnectionPool
# reuse warm TLS connections so a typical evaluate completes in tens
# of ms instead of multiple seconds.
_CLIENT_CACHE: dict[str, redis.Redis] = {}
_CLIENT_CACHE_LOCK = threading.Lock()


def _get_client(url: str | None = None) -> redis.Redis:
    """Return a cached :class:`redis.Redis` client for ``url``.

    The same client instance is returned for the lifetime of the
    process (or until :func:`reset_client_cache` is called from a
    test). redis-py's ``ConnectionPool`` is thread-safe, so sharing a
    single client across threads is the documented happy path.
    """
    key = url or os.getenv("REDIS_URL", "redis://localhost:6379")
    cached = _CLIENT_CACHE.get(key)
    if cached is not None:
        return cached
    with _CLIENT_CACHE_LOCK:
        cached = _CLIENT_CACHE.get(key)
        if cached is not None:
            return cached
        client = redis.from_url(
            key,
            decode_responses=False,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
            health_check_interval=30,
        )
        _CLIENT_CACHE[key] = client
        return client


def reset_client_cache() -> None:
    """Drop the cached clients -- intended for use in tests only.

    Tests that monkeypatch ``REDIS_URL`` or swap out the redis module
    must call this between cases to avoid leaking a stale client into
    the next test's environment.
    """
    with _CLIENT_CACHE_LOCK:
        for client in _CLIENT_CACHE.values():
            try:
                client.close()
            except Exception:  # noqa: BLE001 - best-effort cleanup
                pass
        _CLIENT_CACHE.clear()


def _bitmap_key(bitmap_id: str) -> str:
    return f"{_RBM_PREFIX}{bitmap_id}"


def _ruleset_key(version: str) -> str:
    return f"{_RULESET_PREFIX}{version}"


def _normalise_scope(
    scope_type: str | None = None, scope_id: str | None = None
) -> tuple[str, str]:
    st = str(scope_type or _DEFAULT_SCOPE_TYPE).strip().lower() or _DEFAULT_SCOPE_TYPE
    sid = str(scope_id or _DEFAULT_SCOPE_ID).strip() or _DEFAULT_SCOPE_ID
    return st, sid


def _scope_token(scope_type: str | None = None, scope_id: str | None = None) -> str:
    st, sid = _normalise_scope(scope_type, scope_id)
    return f"{st}:{sid}"


def _scoped_ruleset_key(
    version: str, scope_type: str | None = None, scope_id: str | None = None
) -> str:
    return f"{_RULESET_PREFIX}{_scope_token(scope_type, scope_id)}:{version}"


def _scoped_current_key(
    scope_type: str | None = None, scope_id: str | None = None
) -> str:
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

    def get_int_ids_bulk(self, concept_ids: list[str]) -> dict[str, int]:
        """Look up int_ids for multiple concept IDs in a single Redis HMGET.

        Replaces N sequential HGET calls with one round trip, which is
        critical when evaluating patients with many SNOMED codes against
        Azure Cache for Redis (each TLS round trip costs 50-200 ms).

        Args:
            concept_ids: List of SNOMED concept ID strings to look up.

        Returns:
            Dict mapping concept_id to int_id for every concept that has
            been indexed.  Concepts not in the store are omitted.
        """
        if not concept_ids:
            return {}
        client = self._client()
        values = client.hmget(_INTIDS_KEY, concept_ids)
        return {
            cid: int(v)
            for cid, v in zip(concept_ids, values)
            if v is not None
        }

    def get_bitmaps_bulk(self, bitmap_ids: list[str]) -> dict[str, "BitMap"]:
        """Retrieve multiple BitMaps in a single Redis MGET round trip.

        Replaces N sequential GET calls with one round trip for all bitmaps
        needed in a logic tree evaluation pass.  On Azure TLS Redis each
        saved round trip costs 50-200 ms, so the saving is large for rules
        with many CONCEPT nodes.

        Args:
            bitmap_ids: List of BLAKE2b digests (as returned by put_bitmap).

        Returns:
            Dict mapping bitmap_id to BitMap for every id found in Redis.
            Missing ids are omitted.
        """
        if not bitmap_ids:
            return {}
        keys = [_bitmap_key(bid) for bid in bitmap_ids]
        client = self._client()
        values = client.mget(keys)
        return {
            bid: BitMap.deserialize(raw)
            for bid, raw in zip(bitmap_ids, values)
            if raw is not None
        }

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
                and ":"
                not in (k.decode() if isinstance(k, bytes) else k)[old_prefix_len:]
            ]
        return sorted(versions)

    def delete_scope(
        self,
        scope_type: str,
        scope_id: str,
    ) -> int:
        """Delete every Redis key belonging to a sandbox scope.

        Drops both the active-version pointer and every compiled
        ``ruleset:{scope}:*`` payload. Refuses to delete the production
        global scope so a stray call cannot wipe live rules.

        Returns:
            Number of Redis keys removed.
        """
        st, sid = _normalise_scope(scope_type, scope_id)
        if st == "global":
            raise ValueError(
                "delete_scope refuses to drop the global scope; "
                "production rulesets are off-limits."
            )
        client = self._client()
        token = _scope_token(st, sid)
        prefix = f"{_RULESET_PREFIX}{token}:"
        keys = list(client.keys(f"{prefix}*"))
        current_key = _scoped_current_key(st, sid)
        keys.append(current_key)
        if not keys:
            return 0
        return int(client.delete(*keys) or 0)

    def set_scope_ttl(
        self,
        scope_type: str,
        scope_id: str,
        *,
        ttl_seconds: int,
    ) -> int:
        """Apply a TTL to every Redis key in a sandbox scope.

        Acts as a safety net so abandoned sandbox compiles eventually
        expire even if the ``DELETE /scopes`` cleanup call is missed.
        Refuses to TTL the global scope.

        Returns:
            Number of keys an EXPIRE was set on.
        """
        st, sid = _normalise_scope(scope_type, scope_id)
        if st == "global":
            raise ValueError(
                "set_scope_ttl refuses to expire the global scope."
            )
        if ttl_seconds <= 0:
            return 0
        client = self._client()
        token = _scope_token(st, sid)
        prefix = f"{_RULESET_PREFIX}{token}:"
        keys = list(client.keys(f"{prefix}*"))
        keys.append(_scoped_current_key(st, sid))
        applied = 0
        for k in keys:
            if client.expire(k, ttl_seconds):
                applied += 1
        return applied

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
