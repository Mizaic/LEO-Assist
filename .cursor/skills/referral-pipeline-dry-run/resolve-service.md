# Resolve organisation and :Service

MCP graphs (do not mix):

- Dev: `user-leo-neo4j` / `user-user-leo-neo4j`
  (`run_cypher_knowledge` for `:Service`, `run_cypher_patient`
  for referrals and DocRefs)
- Prod: `user-neo4j-mcp` (`read-cypher`)

Live RC9 / BedsFT service lookup uses **prod**. Say which graph
each result came from. If the chosen MCP fails, stop.

Do not hard-code a service catalogue. Names and RC branding drift.

## After they name an org

Find `:Service` nodes for that trust or site. Match on `s.name` and
the linked organisation when it exists.

```cypher
MATCH (s:Service)
OPTIONAL MATCH (s)-[:PROVIDES_SERVICE_FOR]->(o:Organization)
WITH s, o
WHERE toLower(s.name) CONTAINS $org
   OR toLower(coalesce(o.name, '')) CONTAINS $org
RETURN s.id AS id,
       s.name AS name,
       s.clinicalType AS clinicalType,
       o.name AS org
ORDER BY s.name
```

`$org` examples: `bedford`, `bedsft`, `rc9`, `l&d`, `luton`.

Many L&D RC9 nodes have a name but no org link. Name match still
counts. Say so if the org edge is missing.

## After they name a specialty or clinic

Search name, `clinicalType`, and live referral specialty / clinic type.

```cypher
MATCH (s:Service)
OPTIONAL MATCH (s)-[:PROVIDES_SERVICE_FOR]->(o:Organization)
WITH s, o
WHERE (
    toLower(s.name) CONTAINS $q
    OR toLower(coalesce(s.clinicalType, '')) CONTAINS $q
    OR EXISTS {
        MATCH (s)<-[:FOR_SERVICE]-(rr:ReferralRequest)
        WHERE toLower(coalesce(rr.specialty, '')) CONTAINS $q
           OR toLower(coalesce(rr.clinicType, '')) CONTAINS $q
    }
)
AND (
    $org = ''
    OR toLower(s.name) CONTAINS $org
    OR toLower(coalesce(o.name, '')) CONTAINS $org
)
OPTIONAL MATCH (s)<-[:FOR_SERVICE]-(rr:ReferralRequest)
OPTIONAL MATCH (s)<-[:FOR_SERVICE]-(rr2:ReferralRequest)
  -[:HAS_DOCUMENT]->(dr:DocumentReference)-[:HAS_CHUNK]->(c)
RETURN s.id AS id,
       s.name AS name,
       s.clinicalType AS clinicalType,
       o.name AS org,
       count(DISTINCT rr) AS referrals,
       count(DISTINCT c) AS chunks
ORDER BY referrals DESC, s.name
```

`$q` examples: `lower gi`, `colorectal`, `gi and liver`, `hepat`,
`gastro`. Pass `$org` when they already named a site.

Also search the e-RS specialty `GI_AND_LIVER_MEDICINE_AND_SURGERY`
when they asked for routine GI or Liver. Those referrals often sit
on RC1-named services, not RC9.

## Show matches like this

For each row: `id`, name, `clinicalType`, org (or "no org link"),
referral count, chunk count.

Group when it helps: 2WW vs routine, RC9 vs RC1, Bedford vs L&D,
age band, RAS vs A&G.

Then ask: "Which service id should I use?"

## Do not treat these as the same service

- RC9 2WW Lower GI age bands (`8011574` 80+, `8011575` 18-29,
  `7957488` 30-79, `8012315` consultant-only)
- RC1 colorectal Lower GI (`133993`) -- routine / established,
  not 2WW
- RC1 gastro / upper GI / hepatology / gall bladder
- L&D `124511` "GI and Liver" -- name only, 0 referrals

## Sample size vs service name

If the user said a number and a specialty, ask both:

1. Is the number a **sample size** or an **age-band service**?
2. Which confirmed `:Service.id`?

Default sample size after a service is confirmed: 5. Use their
number only when they said it is a count.
