# Neo4j NLP Terminology Schema Design

**Purpose:** Populate Neo4j with terminology data to support spaCy-based clinical coding of medical records for UK primary care (NCDA).

**Status:** Design document — partially implemented. Core SNOMED terminology (Concepts, Terms, Relationships, ReadCodes, ICD-10 maps) loaded. Fulltext and vector indexes operational. SurfaceForm writeback active via HITL learning loop. UMLS crosswalk, dm+d drug extension, and SPECIALIST Lexicon loaders not yet built.

---

## 1. Goals

- **Full Neo4j population:** Load ALL terminology data from `external_content/` into Neo4j
- **Local spaCy model:** Use populated Neo4j to build/train a local spaCy NLP model for fast entity linking
- **Neo4j as fallback:** At runtime, spaCy model handles known terms; Neo4j is queried only for terms the model doesn't recognise
- **Entity linking:** Encounter text → spaCy NER spans → local model lookup → (fallback) Neo4j → SNOMED + ICD-10 codes
- **UK focus:** SNOMED UK Clinical Edition as primary, UMLS as crosswalk, Read/CTV3 for legacy
- **Streaming loaders:** Process multi-GB files without loading into memory

---

## 2. Architecture: Runtime Flow

```
Encounter text
    │
    ▼
┌──────────────────┐
│ spaCy pipeline    │
│ (local model)     │─── known term ──► SNOMED + ICD-10 (instant, from model KB)
│                   │
│  if not found:    │
│                   │
│  ┌────────────┐   │
│  │ Neo4j      │   │─── fallback ────► SNOMED + ICD-10 (graph query)
│  │ terminology│   │
│  └────────────┘   │
└──────────────────┘
```

1. spaCy NER extracts clinical spans from text
2. Entity linker checks the local KB (trained from Neo4j data)
3. Unknown terms fall through to Neo4j graph query
4. Newly resolved terms feed back into model retraining

---

## 3. Canonical Code Outputs

For clinical coding output, we standardise on:

| Terminology | Source | Term Type | Rationale |
|-------------|--------|-----------|-----------|
| **SNOMED UK** | SNOMED UK Clinical Edition | PT (Preferred Term) | UK clinical standard |
| **ICD-10** | SNOMED UK maps or UMLS | PT / billable code | UK mortality/billing |
| **Read/CTV3** | SNOMED UK maps or UKTC | — | Legacy GP migration |

---

## 4. Neo4j Schema

### 4.1 Core Nodes

```
(:Concept)
  - id: string (SNOMED conceptId, e.g. "73211009")
  - fsn: string (Fully Specified Name)
  - semantic_tag: string (extracted from FSN, e.g. "disorder", "finding")
  - effective_time: string
  - active: boolean
  - module_id: string

(:Term)
  - id: string (SNOMED descriptionId or synthetic id)
  - surface_form: string (original term string, e.g. "Diabetes mellitus")
  - normalized_form: string (lowercase, stripped, for matching)
  - term_type: string (PT | SY | FSN)
  - language_code: string (e.g. "en")
  - active: boolean

(:UmlsConcept)
  - cui: string (UMLS CUI, e.g. "C0011849")
  - preferred_name: string (UMLS preferred English name)
  - semantic_types: string[] (e.g. ["Disease or Syndrome"])

(:ReadCode)
  - code: string (e.g. "C10..")
  - term: string
  - version: string (v2 | ctv3)

(:Icd10Code)
  - code: string (e.g. "E11.9")
  - term: string

(:DrugConcept)
  - id: string (SNOMED concept ID from dm+d)
  - name: string
  - type: string (VTM | VMP | VMPP | AMP | AMPP)

(:SurfaceForm)
  - form: string (original surface form from known_terms, encounters, lexicon)
  - normalized: string (lowercased/normalised)
  - source: string (known_terms | encounter_analysis | clinical_term_analysis | lexicon)
  - mapped: boolean
```

### 4.2 Relationships

```
(:Term)-[:DESCRIBES]->(:Concept)
  - Links SNOMED description terms to concepts
  - Properties: acceptability (preferred | acceptable), from Language refset

(:Concept)-[:IS_A]->(:Concept)
  - SNOMED hierarchy (typeId = 116680003)
  - From sct2_Relationship where typeId = IS_A

(:Concept)-[:HAS_FINDING_SITE|HAS_CAUSATIVE_AGENT|...]->(:Concept)
  - SNOMED defining relationships (non-ISA)
  - Relationship label derived from typeId concept name

(:Concept)-[:MAPS_TO_ICD10]->(:Icd10Code)
  - From SNOMED UK ExtendedMap refsets (refsetId for ICD-10)
  - Properties: map_group, map_priority, map_rule, map_advice

(:Concept)-[:MAPS_TO_READ]->(:ReadCode)
  - From SNOMED UK SimpleMap (mapTarget = Read code)
  - Or from DMWB data migration maps

(:UmlsConcept)-[:SAME_AS]->(:Concept)
  - UMLS CUI linked to SNOMED concept via SCUI in MRCONSO
  - Crosswalk between UMLS and SNOMED worlds

(:UmlsConcept)-[:HAS_ATOM]->(:Term)
  - UMLS atoms that are SNOMED descriptions (SAB=SNOMEDCT_US/UK)

(:DrugConcept)-[:IS_A]->(:Concept)
  - dm+d concepts linked to SNOMED hierarchy

(:SurfaceForm)-[:MATCHES]->(:Concept)
  - Surface forms from clinical text mapped to SNOMED concepts
  - Properties: match_method (exact | fuzzy | umls_api | manual)
```

### 4.3 Indexes

```cypher
CREATE INDEX term_normalized FOR (t:Term) ON (t.normalized_form);
CREATE FULLTEXT INDEX term_fulltext FOR (t:Term) ON EACH [t.surface_form];
CREATE INDEX concept_id FOR (c:Concept) ON (c.id);
CREATE INDEX umls_cui FOR (u:UmlsConcept) ON (u.cui);
CREATE INDEX icd10_code FOR (i:Icd10Code) ON (i.code);
CREATE INDEX read_code FOR (r:ReadCode) ON (r.code);
CREATE INDEX surface_normalized FOR (s:SurfaceForm) ON (s.normalized);
CREATE INDEX drug_id FOR (d:DrugConcept) ON (d.id);
```

---

## 5. File Inventory and Column Reference

All files are in `external_content/`. Sizes are approximate.

### 5.1 SNOMED UK Clinical Edition (RF2, tab-delimited, header row)

Base path: `trud-snomed-uk-clinical-edition/`

Four directories (we use **Snapshot** for initial load — current state, smaller files):

| Directory | Content |
|-----------|---------|
| `SnomedCT_InternationalRF2_PRODUCTION_20250801T120000Z/` | International core |
| `SnomedCT_UKClinicalRF2_PRODUCTION_20260211T000001Z/` | UK clinical overlay |
| `SnomedCT_UKClinicalRefsetsRF2_PRODUCTION_20260211T000001Z/` | UK clinical refsets |
| `SnomedCT_UKEditionRF2_PRODUCTION_20260211T000001Z/` | UK edition |

Each has `Full/`, `Snapshot/`, `Delta/` subdirs with `Terminology/` and `Refset/` folders.

#### Core Terminology Files

**sct2_Concept** — one row per concept version

| Column | Example | Notes |
|--------|---------|-------|
| id | 100005 | SNOMED concept ID |
| effectiveTime | 20020131 | YYYYMMDD |
| active | 0 or 1 | |
| moduleId | 900000000000207008 | |
| definitionStatusId | 900000000000074008 | primitive/defined |

Sizes: INT Snapshot 31MB, UKCL Snapshot 6.7MB

**sct2_Description** — one row per description (term) version

| Column | Example | Notes |
|--------|---------|-------|
| id | 101013 | Description ID |
| effectiveTime | 20020131 | |
| active | 1 | |
| moduleId | 900000000000207008 | |
| conceptId | 126813005 | FK to Concept |
| languageCode | en | |
| typeId | 900000000000013009 | FSN=900000000000003001, SY=900000000000013009 |
| term | Neoplasm of anterior aspect of epiglottis | The actual text |
| caseSignificanceId | 900000000000020002 | |

Sizes: INT Snapshot 224MB, UKCL Snapshot 37MB

**sct2_Relationship** — defining relationships (IS_A hierarchy + attributes)

| Column | Example | Notes |
|--------|---------|-------|
| id | 100022 | Relationship ID |
| effectiveTime | 20020131 | |
| active | 1 | |
| moduleId | 900000000000207008 | |
| sourceId | 100000000 | Source concept |
| destinationId | 102272007 | Target concept |
| relationshipGroup | 0 | |
| typeId | 116680003 | IS_A=116680003 |
| characteristicTypeId | 900000000000011006 | |
| modifierId | 900000000000451002 | |

Sizes: INT Snapshot 393MB, UKCL Snapshot 36MB

**Key typeId values:**
- `116680003` = Is a (hierarchy)
- `363698007` = Finding site
- `246075003` = Causative agent
- `370135005` = Pathological process
- `405813007` = Procedure site

#### Language Refset

**der2_cRefset_Language** — determines Preferred Term vs Acceptable Synonym

| Column | Notes |
|--------|-------|
| id | Refset member UUID |
| effectiveTime | |
| active | |
| moduleId | |
| refsetId | 900000000000508004=GB English, 900000000000509007=US English |
| referencedComponentId | FK to Description ID |
| acceptabilityId | 900000000000548007=Preferred, 900000000000549004=Acceptable |

Sizes: UKCL Snapshot 56MB, UKED Snapshot 181MB

#### Map Refsets

**der2_iisssccRefset_ExtendedMap (INT)** — SNOMED → ICD-10 (WHO)

| Column | Example | Notes |
|--------|---------|-------|
| id | UUID | |
| effectiveTime | 20150731 | |
| active | 1 | |
| moduleId | 449080006 | |
| refsetId | 447562003 | ICD-10 map refset |
| referencedComponentId | 211339002 | SNOMED concept ID (source) |
| mapGroup | 1 | |
| mapPriority | 1 | |
| mapRule | TRUE | Conditional mapping rule |
| mapAdvice | ALWAYS S80.8 | |
| mapTarget | S80.8 | ICD-10 code (target) |
| correlationId | 447561005 | |
| mapCategoryId | 447637006 | |

Sizes: INT Snapshot 35MB

**der2_iisssciRefset_ExtendedMap (UKCL)** — SNOMED → ICD-10 (UK edition, much larger)

Same columns except last is `mapBlock` instead of `mapCategoryId`.

Sizes: UKCL Snapshot **329MB**, UKCL Full **827MB**

**der2_sRefset_SimpleMap** — simple 1:1 maps (SNOMED → CTV3 Read codes)

| Column | Notes |
|--------|-------|
| id | UUID |
| effectiveTime | |
| active | |
| moduleId | |
| refsetId | 900000000000497000 = CTV3 simple map |
| referencedComponentId | SNOMED concept ID |
| mapTarget | Target code (CTV3 Read code, e.g. "2371.") |

Sizes: INT Snapshot 56MB, UKCL Snapshot 18KB

### 5.2 UMLS Metathesaurus (RRF, pipe-delimited, NO header row)

Base path: `umls/2025AB/META/`

**MRCONSO.RRF** — all concept names/atoms (960MB)

| Position | Column | Type | Notes |
|----------|--------|------|-------|
| 0 | CUI | char(8) | Concept Unique Identifier |
| 1 | LAT | char(3) | Language (ENG, etc.) |
| 2 | TS | char(1) | Term status |
| 3 | LUI | char(10) | Lexical Unique Identifier |
| 4 | STT | char(3) | String type |
| 5 | SUI | char(10) | String Unique Identifier |
| 6 | ISPREF | char(1) | Y = preferred for this LUI |
| 7 | AUI | char(9) | Atom Unique Identifier (PK) |
| 8 | SAUI | char(50) | Source-asserted atom ID |
| 9 | SCUI | char(100) | Source-asserted concept ID (= SNOMED conceptId for SNOMEDCT_US/UK) |
| 10 | SDUI | char(100) | Source-asserted descriptor ID |
| 11 | SAB | char(40) | Source abbreviation (SNOMEDCT_US, ICD10, etc.) |
| 12 | TTY | char(40) | Term type (PT, SY, FN, etc.) |
| 13 | CODE | char(100) | Source code |
| 14 | STR | char(3000) | String (the actual term text) |
| 15 | SRL | integer | Source restriction level |
| 16 | SUPPRESS | char(1) | Suppressed flag |
| 17 | CVF | integer | Content view flag |

**Key SAB values for filtering:**
- SNOMEDCT_US, SNOMEDCT_UK — SNOMED
- ICD10, ICD10CM, ICD10PCS — ICD-10 variants
- RXNORM — drugs
- LNC — LOINC

**Critical:** SCUI field (position 9) contains the SNOMED conceptId when SAB=SNOMEDCT_US/UK. This is the CUI→SNOMED crosswalk.

**MRSTY.RRF** — semantic types per CUI (153MB)

| Position | Column | Notes |
|----------|--------|-------|
| 0 | CUI | |
| 1 | TUI | Type Unique Identifier (e.g. T116) |
| 2 | STN | Semantic tree number |
| 3 | STY | Semantic type name (e.g. "Amino Acid, Peptide, or Protein") |
| 4 | ATUI | |
| 5 | CVF | |

**MRREL.RRF** — relationships between concepts (2.1GB — very large)

| Position | Column | Notes |
|----------|--------|-------|
| 0 | CUI1 | |
| 1 | AUI1 | |
| 2 | STYPE1 | |
| 3 | REL | Relationship (RB, RN, SY, etc.) |
| 4 | CUI2 | |
| 5 | AUI2 | |
| 6 | STYPE2 | |
| 7 | RELA | Relationship attribute (e.g. "entry_version_of") |
| 8 | RUI | Relationship UI (PK) |
| 9 | SRUI | |
| 10 | SAB | Source |
| 11 | SL | |
| 12 | RG | |
| 13 | DIR | |
| 14 | SUPPRESS | |
| 15 | CVF | |

**Decision:** Use SNOMED RF2 relationships instead of MRREL for the hierarchy. Only load MRREL for cross-terminology relationships if needed.

**MRDEF.RRF** — definitions (77MB)

| Position | Column | Notes |
|----------|--------|-------|
| 0 | CUI | |
| 1 | AUI | |
| 2 | ATUI | |
| 3 | SATUI | |
| 4 | SAB | |
| 5 | DEF | Definition text |
| 6 | SUPPRESS | |
| 7 | CVF | |

**MRXW_ENG.RRF** — English word index (1.0GB)
Columns: `WD|CUI|LUI|SUI` — index from word → (CUI, LUI, SUI)

**MRXNW_ENG.RRF** — normalised English word index (1.1GB)
Columns: `NWD|CUI|LUI|SUI` — same but normalised words

**MRXNS_ENG.RRF** — normalised string index (645MB)
Columns: `NSTR|CUI|LUI|SUI` — full normalised string → identifiers

**MRRANK.RRF** — source/term type ranking (6.6KB)
Columns: `RANK|SAB|TTY|SUPPRESS`

**MRSAB.RRF** — source metadata (134KB)

**Oracle loading scripts present:** `*.ctl` files (Oracle SQL*Loader format), `oracle_indexes.sql`

### 5.3 SPECIALIST Lexicon

File: `umls/LEXICON.txt` (56MB)

Unit-record format (curly braces delimited, NOT tabular):

```
{base=cotton roll gingivitis
spelling_variant=cotton-roll gingivitis
entry=E0000001
    cat=noun
    variants=glreg
    variants=uncount
}
```

Key fields per record:
- `base=` — canonical surface form
- `spelling_variant=` — alternate spelling
- `entry=` — EUI identifier
- `cat=` — part of speech (noun, verb, adj, etc.)
- `variants=` — inflection pattern
- `acronym_of=expansion|EUI`
- `abbreviation_of=expansion|EUI`

**Use for:** Abbreviation/acronym expansion, spelling normalisation, lemmatisation rules.

### 5.4 SNOMED CT Drug Extension (dm+d)

Base path: `trud-snomed-ct-drug-extension/`

XML files with SNOMED concept IDs:

| File | Content | Key Elements |
|------|---------|-------------|
| f_vtm2_*.xml | Virtual Therapeutic Moieties | VTMID (SNOMED ID), NM (name) |
| f_vmp2_*.xml | Virtual Medicinal Products | VPID, NM, VTMID (parent) |
| f_vmpp2_*.xml | VMP Packs | VPPID, NM, VPID |
| f_amp2_*.xml | Actual Medicinal Products | APID, NM, VPID |
| f_ampp2_*.xml | AMP Packs | APPID, NM, APID |
| f_ingredient2_*.xml | Ingredients | ISID, NM |
| f_lookup2_*.xml | Lookup tables | Routes, forms, units |

Example VTM record: `VTMID=777067000, NM=Paracetamol, VTMIDPREV=90332006`

### 5.5 Data Migration Workbench (Access .mdb)

Base path: `trud-snomed-data-migration/`

| File | Size | Content |
|------|------|---------|
| DMWB NHS SNOMED.mdb | 705MB | Full SNOMED content in Access format |
| DMWB NHS READ.mdb | 684MB | Read codes v2 and CTV3 |
| DMWB NHS Data Migration Maps.mdb | 211MB | Cross-terminology mappings |
| DMWB NHS SNOMED Query Table.mdb | 1.7GB | Precomputed query tables |
| DMWB NHS SNOMED Transitive Closure.mdb | 761MB | IS_A transitive closure |
| DMWB NHS SNOMED Lexicon.mdb | 487MB | SNOMED lexicon |
| DMWB NHS SNOMED History.mdb | 321MB | Concept history |
| DMWB NHS Public Code Usage.mdb | 222MB | Code usage statistics |

**Access strategy:** Use `mdbtools` (Linux) or `pyodbc`/`pypyodbc` to extract tables to CSV, then stream-load. Primary use is Read codes (since `trud-read-codes-v2/` and `trud-ctv3/` directories are empty).

### 5.6 Read Codes / CTV3

The directories `trud-read-codes-v2/`, `trud-read-code-clinical-terms-v3/`, and `trud-ctv3/` are **empty**. Read code content lives in:
1. `DMWB NHS READ.mdb` (Access database)
2. SNOMED SimpleMap refsets (CTV3 codes as mapTarget)
3. SNOMED UK extended maps

### 5.7 Surface Form Sources

| Source | Size | Content |
|--------|------|---------|
| known_terms.json | 116KB | ~3,400 curated clinical surface forms |
| encounter_analysis.json | 230KB | Unmatched terms, abbreviations, sample phrases from encounters |
| clinical_term_analysis.json | 1.1MB | Read code usage with descriptions and counts |

---

## 6. Data Load Phases

### Phase 1: SNOMED UK Core (Snapshot files)

**Source:** INT + UKCL Snapshot files
**Target:** `(:Concept)`, `(:Term)`, `(:Concept)-[:IS_A]->(:Concept)`, `(:Term)-[:DESCRIBES]->(:Concept)`

1. Load INT `sct2_Concept_Snapshot` (31MB) → `(:Concept)` nodes
2. Load UKCL `sct2_Concept_UKCLSnapshot` (6.7MB) → MERGE additional/updated concepts
3. Load INT `sct2_Description_Snapshot` (224MB) → `(:Term)` nodes + `[:DESCRIBES]` rels
4. Load UKCL `sct2_Description_UKCLSnapshot` (37MB) → MERGE additional UK terms
5. Load Language refset (UKCL 56MB + UKED 181MB) → SET `acceptability` on `[:DESCRIBES]`
6. Load INT `sct2_Relationship_Snapshot` (393MB) → `[:IS_A]` and `[:HAS_*]` relationships
7. Load UKCL `sct2_Relationship_UKCLSnapshot` (36MB) → additional UK relationships

**Estimated rows:** ~500K concepts, ~1.5M descriptions, ~2M relationships

### Phase 2: SNOMED Maps → ICD-10 and Read

**Source:** ExtendedMap + SimpleMap Snapshot files
**Target:** `(:Icd10Code)`, `(:ReadCode)`, mapping relationships

1. Load INT ExtendedMap Snapshot (35MB) → `(:Concept)-[:MAPS_TO_ICD10]->(:Icd10Code)`
2. Load UKCL ExtendedMap Snapshot (329MB) → same, UK-specific ICD-10 maps
3. Load SimpleMap Snapshot (56MB + 18KB) → `(:Concept)-[:MAPS_TO_READ]->(:ReadCode)` for CTV3

**Filter:** `refsetId` determines the target terminology scheme.

### Phase 3: UMLS Crosswalk

**Source:** MRCONSO.RRF (960MB), MRSTY.RRF (153MB)
**Target:** `(:UmlsConcept)`, `[:SAME_AS]` to SNOMED concepts

**Strategy:** Stream MRCONSO filtering by `LAT=ENG` and relevant SABs:
1. For SAB in (SNOMEDCT_US, SNOMEDCT_UK): extract CUI↔SCUI mapping → `(:UmlsConcept)-[:SAME_AS]->(:Concept)` where SCUI = SNOMED conceptId
2. For SAB in (ICD10, ICD10CM): enrich `(:Icd10Code)` with CUI crosswalk
3. Load MRSTY: add semantic types to `(:UmlsConcept)`
4. Load MRXW_ENG/MRXNW_ENG word indexes as additional `(:Term)` surface forms linked via CUI→SNOMED

**Do NOT load:** Full MRREL (2.1GB) — hierarchy comes from SNOMED RF2. Full MRSAT (2.3GB) — attributes not needed initially.

### Phase 4: Read/CTV3 from DMWB

**Source:** DMWB NHS READ.mdb, DMWB NHS Data Migration Maps.mdb
**Target:** `(:ReadCode)` nodes, `[:MAPS_TO_READ]` relationships

**Strategy:** Export key tables from .mdb to CSV, then stream-load. Supplement SimpleMap data from Phase 2.

### Phase 5: Drug Extension (dm+d)

**Source:** XML files in `trud-snomed-ct-drug-extension/`
**Target:** `(:DrugConcept)` nodes

Parse XML, create drug concepts linked to SNOMED hierarchy.

### Phase 6: Surface Forms and SPECIALIST Lexicon

**Source:** known_terms.json, encounter_analysis.json, clinical_term_analysis.json, LEXICON.txt
**Target:** `(:SurfaceForm)` nodes, `[:MATCHES]` to existing `(:Concept)` nodes

1. Extract surface forms from each source
2. Normalise (lowercase, strip semantic tags like `(finding)`)
3. Match against existing `(:Term).normalized_form` (exact)
4. Fuzzy match for near-misses
5. UMLS API fallback for unmatched clinical terms
6. Stage remaining unmatched for manual review

---

## 7. Loader Design Principles

1. **Streaming:** Read files line-by-line; never `read()` entire file
2. **Batching:** `UNWIND` + `MERGE` in batches of 5K–10K rows per transaction
3. **Idempotency:** `MERGE` on unique keys; safe to re-run
4. **Progress:** Log rows processed and elapsed time; support resume via marker file
5. **Header validation:** Verify column names before processing (RF2 has headers; RRF does not — validate column count against MRCONSO.ctl schema)
6. **Filter early:** Skip inactive rows, non-English rows, irrelevant SABs during streaming (before sending to Neo4j)

### Loader module structure

```
scripts/loaders/
├── __init__.py
├── base.py              # Shared: streaming, batching, Neo4j session management
├── snomed_concept.py    # Phase 1: sct2_Concept → (:Concept)
├── snomed_description.py # Phase 1: sct2_Description → (:Term)-[:DESCRIBES]->(:Concept)
├── snomed_relationship.py # Phase 1: sct2_Relationship → [:IS_A] and attribute rels
├── snomed_language.py   # Phase 1: Language refset → acceptability on [:DESCRIBES]
├── snomed_map.py        # Phase 2: ExtendedMap/SimpleMap → ICD-10/Read
├── umls_crosswalk.py    # Phase 3: MRCONSO + MRSTY → (:UmlsConcept)
├── dmwb_read.py         # Phase 4: DMWB .mdb export → (:ReadCode)
├── drug_extension.py    # Phase 5: dm+d XML → (:DrugConcept)
├── surface_forms.py     # Phase 6: known_terms, encounters, lexicon → (:SurfaceForm)
└── run_all.py           # Orchestrator: runs phases in order
```

### Example: SNOMED Description loader (pseudocode)

```python
async def load_descriptions(driver, filepath, batch_size=5000):
    batch = []
    async with driver.session() as session:
        for row in stream_rf2(filepath):  # generator, yields dict per row
            if row["active"] != "1":
                continue
            batch.append({
                "desc_id": row["id"],
                "concept_id": row["conceptId"],
                "term": row["term"],
                "normalized": normalize(row["term"]),
                "type_id": row["typeId"],
                "lang": row["languageCode"],
            })
            if len(batch) >= batch_size:
                await session.execute_write(merge_descriptions_tx, batch)
                batch.clear()
        if batch:
            await session.execute_write(merge_descriptions_tx, batch)

MERGE_CYPHER = """
UNWIND $rows AS r
MERGE (t:Term {id: r.desc_id})
SET t.surface_form = r.term,
    t.normalized_form = r.normalized,
    t.term_type = r.type_id,
    t.language_code = r.lang,
    t.active = true
WITH t, r
MERGE (c:Concept {id: r.concept_id})
MERGE (t)-[:DESCRIBES]->(c)
"""
```

### Example: UMLS MRCONSO filter (pseudocode)

```python
RELEVANT_SABS = {"SNOMEDCT_US", "SNOMEDCT_UK", "ICD10", "ICD10CM"}

def stream_mrconso_filtered(filepath):
    for line in open(filepath, encoding="utf-8"):
        fields = line.rstrip("\n").split("|")
        if fields[1] != "ENG":       # LAT — English only
            continue
        if fields[11] not in RELEVANT_SABS:  # SAB
            continue
        if fields[16] in ("O", "E"):  # SUPPRESS — skip obsolete/editorial
            continue
        yield {
            "cui": fields[0],
            "sab": fields[11],
            "tty": fields[12],
            "code": fields[13],
            "term": fields[14],
            "scui": fields[9],        # SNOMED conceptId when SAB=SNOMEDCT_*
        }
```

---

## 8. spaCy Integration

### Phase A: Build spaCy Knowledge Base from Neo4j

After Neo4j is populated, export a spaCy-compatible Knowledge Base:

1. Query all `(:Concept)` with their preferred `(:Term)` → build entity catalog
2. Generate entity vectors (using spaCy embeddings or bio-embeddings)
3. Build `KnowledgeBase` object with entity aliases (surface forms) and prior probabilities
4. Serialize KB to disk for fast loading

### Phase B: Custom EntityLinker pipeline component

```python
@Language.factory("neo4j_entity_linker")
class Neo4jEntityLinker:
    def __init__(self, nlp, name, kb_path, neo4j_uri):
        self.kb = KnowledgeBase(...)  # local, fast
        self.neo4j = AsyncDriver(...)  # fallback

    def __call__(self, doc):
        for ent in doc.ents:
            candidates = self.kb.get_candidates(ent.text)
            if candidates:
                # Score and select best match from local KB
                best = max(candidates, key=lambda c: c.prior_prob)
                ent.kb_id_ = best.entity_id
            else:
                # Fallback: query Neo4j
                result = self.query_neo4j(ent.text)
                if result:
                    ent.kb_id_ = result["snomed_code"]
        return doc
```

### Phase C: Neo4j fallback query

```cypher
MATCH (t:Term)-[:DESCRIBES]->(c:Concept)
WHERE t.normalized_form = $normalized
OPTIONAL MATCH (c)-[:MAPS_TO_ICD10]->(icd:Icd10Code)
RETURN c.id AS snomed_code, c.fsn AS snomed_fsn,
       collect(DISTINCT icd.code) AS icd10_codes
LIMIT 1
```

For fuzzy/phrase matching:

```cypher
CALL db.index.fulltext.queryNodes("term_fulltext", $phrase)
YIELD node, score
MATCH (node)-[:DESCRIBES]->(c:Concept)
WHERE c.active = true
RETURN c.id AS snomed_code, c.fsn AS snomed_fsn, score
ORDER BY score DESC
LIMIT 5
```

### Output per entity

```json
{
  "text": "diabetes mellitus",
  "snomed_code": "73211009",
  "snomed_fsn": "Diabetes mellitus (disorder)",
  "snomed_pt": "Diabetes mellitus",
  "icd10_codes": ["E14.9", "E11.9"],
  "read_code": "C10..",
  "cui": "C0011849",
  "source": "local_kb",
  "linker_score": 0.95,
  "confidence": 0.92,
  "is_negated": false,
  "is_uncertain": false,
  "is_historical": true,
  "is_hypothetical": false,
  "is_family": false,
  "is_resolved": false,
  "section_category": "past_medical_history",
  "is_abbreviation": false,
  "value": null,
  "unit": null,
  "measurement_type": null
}
```

### KB Export and Index Building

After terminology load (Phases 1-6), run `scripts/build_index.py` to:
1. Export the Neo4j terminology graph to Entity JSONL (`data/entities.jsonl`)
2. Fit a TF-IDF character 3-gram vectorizer over all alias strings
3. Build an nmslib HNSW approximate nearest neighbour index
4. Save 4 artifacts: `nmslib_index.bin`, `tfidf_vectorizer.joblib`,
   `tfidf_vectors.npz`, `concept_aliases.json`

The entity linker loads these artifacts at startup for sub-millisecond lookups.
Neo4j is then used only as a fallback for terms not resolved by the local index.

---

## 9. Size Estimates and Loading Time

| Phase | Data Volume | Estimated Neo4j Nodes | Notes |
|-------|-------------|----------------------|-------|
| 1. SNOMED Core | ~550MB (Snapshots) | ~500K Concept, ~1.5M Term, ~2M rels | Largest by node count |
| 2. SNOMED Maps | ~420MB | ~80K Icd10Code, ~200K ReadCode | Many:many mappings |
| 3. UMLS Crosswalk | ~1.1GB (filtered) | ~400K UmlsConcept | Filter reduces MRCONSO significantly |
| 4. Read/CTV3 | ~900MB (.mdb) | ~100K ReadCode (enrichment) | Requires mdb export |
| 5. dm+d | ~2MB (XML) | ~20K DrugConcept | Fast |
| 6. Surface Forms | ~1.5MB + 56MB lexicon | ~50K SurfaceForm | Matching phase is slow |

Total estimated: ~2.5M nodes, ~5M relationships. Well within Neo4j Community Edition limits.

---

## 10. Out of Scope (for now)

- Full UMLS MRREL (2.1GB) — hierarchy from SNOMED RF2 is sufficient
- Full UMLS MRSAT (2.3GB) — concept attributes not needed for entity linking
- SNOMED OWL expressions and StatedRelationships — core Relationship file covers IS_A + attributes
- SPECIALIST Lexicon inflection rules as a runtime component (extract surface forms only)
- DMWB Query Table / Transitive Closure (precomputed in Neo4j via Cypher)
- Full MRHIER (542MB) — use SNOMED IS_A chain instead

---

## 11. Next Steps (Implementation Order)

1. **Set up Neo4j** — Docker container with APOC plugin, create constraints and indexes
2. **Build base loader** — `scripts/loaders/base.py` with streaming, batching, progress logging
3. **Phase 1: SNOMED loader** — Concept + Description + Language refset + Relationship
4. **Phase 2: Map loader** — ExtendedMap + SimpleMap → ICD-10 and Read codes
5. **Phase 3: UMLS crosswalk** — MRCONSO (filtered) + MRSTY → UmlsConcept nodes
6. **Phase 4: DMWB export** — Extract Read codes from .mdb to CSV, then load
7. **Phase 5: dm+d loader** — Parse XML, create DrugConcept nodes
8. **Phase 6: Surface forms** — Load known_terms, encounters, lexicon; match to concepts
9. **Build spaCy KB** — Export from Neo4j → Entity JSONL → TF-IDF + ANN index (`scripts/build_index.py`)
10. **Build spaCy pipeline** — medspaCy + custom components with UK GP rules (`nlp/pipeline.py`)
11. **Validation** — Test against known_terms.json and encounter_analysis.json
