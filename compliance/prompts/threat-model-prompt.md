CONTEXT
You are auditing a SaaS medical device platform (UKCA Class I) for NHS cancer referral workflow management. Regulatory scope: ISO 13485, IEC 62304, UK GDPR, NHS DSPT, NCSC Secure by Design principles.

OBJECTIVE
Produce a Secure by Design threat model through iterative analysis. Output machine-readable artefacts (YAML/JSON) plus human-readable summaries. Use TODO markers for incomplete analysis.

TODO CONVENTIONS
- TODO:INSPECT - Requires deeper code analysis
- TODO:CROSS-REF - Depends on another component's analysis
- TODO:INFER - Documentation missing, inference required
- TODO:VERIFY - Cannot determine statically
- TODO:MANUAL - Requires human review

---

PHASE 1: ASSET INVENTORY

1.1 DATA ASSETS
Enumerate all data the system stores, processes, or transmits.

Output: data-assets.yaml
```yaml
data_assets:
  - id: DA-001
    name: 
    description: 
    classification: [PII | Clinical | Operational | Public]
    special_category: [true | false]  # UK GDPR Article 9
    clinical_safety_relevant: [true | false]
    storage_locations: []
    retention_requirements: 
    regulatory_references: []
```

1.2 SERVICE INVENTORY
Enumerate all services, processes, and compute resources.

Output: service-inventory.yaml
```yaml
services:
  - id: SVC-001
    name: 
    type: [API | Worker | Scheduler | Database | Cache | Queue | External]
    description: 
    entry_points: []
    dependencies: []
    runs_as: # user/service account
    network_exposure: [Public | Internal | Isolated]
    source_location: # code path
```

1.3 SECRETS INVENTORY
Enumerate all secrets, credentials, and cryptographic material.

Output: secrets-inventory.yaml
```yaml
secrets:
  - id: SEC-001
    name: 
    type: [API Key | Database Credential | Signing Key | Encryption Key | Certificate | OAuth Secret | Other]
    purpose: 
    storage_mechanism: [Environment Variable | Secrets Manager | Config File | Hardcoded | Unknown]
    rotation_policy: [Documented | Undocumented | None]
    scope: # which services use this
    exposure_risk: [Critical | High | Medium | Low]
    findings: # issues identified
```

1.4 INTEGRATION INVENTORY
Enumerate all external systems and third-party dependencies.

Output: integrations.yaml
```yaml
integrations:
  - id: INT-001
    name: 
    type: [NHS System | Third Party API | Identity Provider | Cloud Service | Dependency Library]
    direction: [Inbound | Outbound | Bidirectional]
    protocol: 
    authentication_method: 
    data_exchanged: []  # reference DA-XXX
    trust_level: [Trusted | Semi-Trusted | Untrusted]
    failure_mode: # what happens if unavailable
```

---

PHASE 2: TRUST BOUNDARIES

Identify all points where security context changes.

Output: trust-boundaries.yaml
```yaml
trust_boundaries:
  - id: TB-001
    name: 
    description: 
    from_zone: 
    to_zone: 
    crossing_mechanism: # API gateway, direct call, message queue
    authentication_at_boundary: 
    authorisation_at_boundary: 
    data_validation_at_boundary: 
    services_involved: []  # reference SVC-XXX
    data_crossing: []  # reference DA-XXX
```

Define security zones:
```yaml
security_zones:
  - id: ZONE-001
    name: 
    description: 
    network_segment: 
    access_control: 
    services_contained: []
```

---

PHASE 3: DATA FLOW MAPPING

Trace how each data asset moves through the system.

Output: data-flows.yaml
```yaml
data_flows:
  - id: DF-001
    name: 
    description: 
    trigger: # what initiates this flow
    data_assets: []  # reference DA-XXX
    path:
      - step: 1
        from: # SVC-XXX or external
        to: # SVC-XXX or external
        protocol: 
        encrypted_in_transit: [true | false]
        crosses_boundary: # TB-XXX or null
    transforms: # any data modification
    sink: # final destination
    clinical_pathway: [true | false]  # part of clinical decision flow
```

Generate Mermaid diagram: data-flow-diagram.md

---

PHASE 4: AUTHENTICATION & AUTHORISATION MAPPING

Output: authn-authz.yaml
```yaml
authentication:
  mechanisms:
    - id: AUTHN-001
      type: [OAuth2 | SAML | API Key | mTLS | Session | Other]
      provider: 
      applies_to: []  # SVC-XXX
      mfa_required: [true | false]
      session_management: 
      
authorisation:
  model: [RBAC | ABAC | ACL | Custom]
  roles:
    - id: ROLE-001
      name: 
      permissions: []
      assignment_mechanism: 
  permission_checks:
    - id: PERM-001
      resource: 
      action: 
      enforcement_point: # code location
      bypass_risks: 
```

---

PHASE 5: SECURITY CONTROLS MAPPING

Map existing controls to assets and boundaries.

Output: security-controls.yaml
```yaml
controls:
  - id: CTRL-001
    name: 
    type: [Preventive | Detective | Corrective]
    category: [Authentication | Authorisation | Encryption | Logging | Validation | Rate Limiting | Other]
    implementation: # code location or service
    protects: []  # DA-XXX, SVC-XXX, TB-XXX
    effectiveness: [Strong | Adequate | Weak | Unknown]
    gaps: 
```

---

PHASE 6: GAP ANALYSIS

Cross-reference inventories to identify:

6.1 UNPROTECTED ASSETS
- Data assets without encryption at rest/transit
- Services without authentication
- Boundaries without validation

6.2 ORPHANED SECRETS
- Secrets with no documented purpose
- Hardcoded credentials
- Missing rotation policies

6.3 UNMONITORED FLOWS
- Data flows without audit logging
- Clinical decision paths without traceability

6.4 CONTROL GAPS
- NCSC Secure by Design principles not met
- IEC 62304 security requirements gaps

Output: gap-analysis.yaml
```yaml
gaps:
  - id: GAP-001
    category: [Asset Protection | Secret Management | Flow Monitoring | Control Coverage | Regulatory]
    severity: [Critical | High | Medium | Low]
    description: 
    affected_elements: []  # reference IDs
    evidence: # code or config reference
    remediation: 
    regulatory_impact: []  # which standards affected
```

---

PHASE 7: CONSOLIDATION

Resolve all TODOs possible through cross-referencing.
Produce final outputs:
- threat-model-summary.md (human readable)
- All YAML artefacts (machine readable)
- Unresolved TODOs with specific information needed

---

CONSTRAINTS
- Evidence-based only. No theoretical gaps without code/config proof.
- Flag visibility limits explicitly.
- Prioritise clinical safety and patient data elements.
- Maintain traceability: every finding references specific artefact IDs.