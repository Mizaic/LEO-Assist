# Design Controls — Document Index

IEC 62304:2006+A1:2015 compliant design control documentation for the Primary Care Clinical Pathway Audit Platform.

**Software Safety Classification: Class B** (non-serious injury is possible via indirect harm pathway — see DC-SC-001)

---

## Document Register

| ID | Document | IEC 62304 Clause | Version | Status |
|----|----------|-----------------|---------|--------|
| DC-IU-001 | [Intended Use Statement](./intended-use.md) | Input to 5.2 | 0.2.0 | Draft |
| DC-SC-001 | [Safety Classification](./DC-SC-001-safety-classification.md) | 4.3 | 2.0.0 | Draft |
| DC-SDP-001 | [Software Development Plan](./DC-SDP-001-development-plan.md) | 4.4 | 2.0.0 | Draft |
| DC-SRS-001 | [Software Requirements Specification](./DC-SRS-001-software-requirements.md) | 5.2 | 1.0.0 | Draft |
| DC-ITP-001 | [Integration Test Plan](./DC-ITP-001-integration-test-plan.md) | 5.6 | 1.0.0 | Draft |
| DC-STP-001 | [System Test Plan](./DC-STP-001-system-test-plan.md) | 5.7 | 1.0.0 | Draft |
| DC-SMP-001 | [Maintenance Plan](./DC-SMP-001-maintenance-plan.md) | 6 | 1.0.0 | Draft |
| DC-RM-001 | [Risk Management](./DC-RM-001-risk-management.md) | 7 / ISO 14971 | 2.0.0 | Draft |
| DC-CM-001 | [Configuration Management](./DC-CM-001-configuration-management.md) | 8 | 1.0.0 | Draft |
| DC-SOUP-001 | [SOUP List](./DC-SOUP-001-soup-list.md) | 8.1.2 | 1.0.0 | Draft |
| DC-PR-001 | [Problem Resolution](./DC-PR-001-problem-resolution.md) | 9 | 1.0.0 | Draft |
| DC-TM-001 | [Traceability Matrix](./DC-TM-001-traceability-matrix.md) | Voluntary | 1.0.0 | Draft |
| -- | [Neo4j Terminology Schema](./neo4j-nlp-terminology-schema.md) | Reference | -- | Implemented |

---

## Related Documentation

| Location | Contents |
|----------|----------|
| [docs/nlp-pipeline/](../docs/nlp-pipeline/) | Software Architecture (02), Detailed Design (03), Implementation (04), V&V Procedures (05), Phase Plans (06), Verification Report |

---

## IEC 62304 Class B Compliance Checklist

| Clause | Requirement | Document | Status |
|--------|------------|----------|--------|
| 4.3 | Safety classification | DC-SC-001 | Done |
| 4.4 | Development planning | DC-SDP-001 | Done |
| 5.1 | Software development process | DC-SDP-001 | Done |
| 5.2 | Software requirements analysis | DC-SRS-001 | Done |
| 5.3 | Software architectural design | docs/nlp-pipeline/02-* | Done |
| 5.4 | Software detailed design | docs/nlp-pipeline/03-* (voluntary, not required for Class B) | Done |
| 5.5 | Software unit implementation and verification | 58 unit tests; DC-STP-001 Section 5 | Done |
| 5.6 | Software integration and integration testing | DC-ITP-001 | Done |
| 5.7 | Software system testing | DC-STP-001 | Done |
| 5.8 | Software release | DC-SDP-001 Section 11 | Done |
| 6 | Software maintenance | DC-SMP-001 | Done |
| 7 | Software risk management | DC-RM-001 | Done |
| 8 | Software configuration management | DC-CM-001 + DC-SOUP-001 | Done |
| 9 | Software problem resolution | DC-PR-001 | Done |
