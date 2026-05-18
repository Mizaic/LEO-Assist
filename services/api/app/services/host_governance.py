"""LEO widget embedding-host governance register.

Atlas trace:
  DO: DO-5A298ABC
  DI: DI-2FBDAC7D
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-5A298ABC")

The four mandatory artefacts every embedding host SHALL have on
file before the LEO API will mint a production widget token:

  1. saas_embedding_agreement
  2. dpa                        (Data Processing Agreement)
  3. dcb0129_reference          (LEO supplier safety case ref)
  4. ifu_acknowledged           (host has acknowledged the
                                 LEO widget IFU; version captured)

This module is the in-process gatekeeper. Slice 6 keeps the
register in process memory; slice 7+ persists into the LEO Atlas
QMS register so the quarterly Clinical Safety Committee review
can read it directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock
from typing import Literal


REQUIRED_ARTEFACTS: tuple[str, ...] = (
    "saas_embedding_agreement",
    "dpa",
    "dcb0129_reference",
    "ifu_acknowledged",
)

ArtefactName = Literal[
    "saas_embedding_agreement",
    "dpa",
    "dcb0129_reference",
    "ifu_acknowledged",
]


class HostNotRegisteredError(Exception):
    """Raised when an operation references a host_id that is unknown."""


@dataclass
class HostRecord:
    host_id: str
    name: str
    contact: str
    artefacts: dict[str, str | None] = field(
        default_factory=lambda: {a: None for a in REQUIRED_ARTEFACTS}
    )
    acknowledged_ifu_version: str | None = None

    def is_production_ready(self) -> bool:
        return all(self.artefacts.get(a) for a in REQUIRED_ARTEFACTS)

    def to_dict(self) -> dict:
        return {
            "host_id": self.host_id,
            "name": self.name,
            "contact": self.contact,
            "artefacts": dict(self.artefacts),
            "acknowledged_ifu_version": self.acknowledged_ifu_version,
            "is_production_ready": self.is_production_ready(),
        }


_lock = RLock()
_register: dict[str, HostRecord] = {}


def register_host(host_id: str, name: str, contact: str) -> HostRecord:
    """Register a new embedding host (or return the existing record)."""
    with _lock:
        if host_id in _register:
            return _register[host_id]
        record = HostRecord(host_id=host_id, name=name, contact=contact)
        _register[host_id] = record
        return record


def mark_artefact_received(
    host_id: str,
    artefact: ArtefactName,
    evidence_uri: str,
) -> HostRecord:
    """Record evidence that one of the four artefacts is on file."""
    with _lock:
        record = _register.get(host_id)
        if record is None:
            raise HostNotRegisteredError(host_id)
        if artefact not in REQUIRED_ARTEFACTS:
            raise ValueError(f"unknown artefact: {artefact}")
        if not evidence_uri:
            raise ValueError("evidence_uri must be a non-empty string")
        record.artefacts[artefact] = evidence_uri
        return record


def acknowledge_ifu(host_id: str, version: str) -> HostRecord:
    """Record that the host has acknowledged the IFU version."""
    if not version:
        raise ValueError("version must be a non-empty string")
    with _lock:
        record = _register.get(host_id)
        if record is None:
            raise HostNotRegisteredError(host_id)
        record.acknowledged_ifu_version = version
        record.artefacts["ifu_acknowledged"] = f"ifu:{version}"
        return record


def get_host(host_id: str) -> HostRecord | None:
    with _lock:
        return _register.get(host_id)


def is_production_ready(host_id: str) -> bool:
    record = get_host(host_id)
    return record is not None and record.is_production_ready()


def list_hosts() -> list[dict]:
    with _lock:
        return [record.to_dict() for record in _register.values()]


def _reset_for_testing() -> None:
    with _lock:
        _register.clear()
