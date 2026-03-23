from libs.neo4j_client.client import PatientGraphClient

with PatientGraphClient().session() as s:
    r = s.run(
        "MATCH (t:TrainingLabel) WHERE t.include = true "
        "AND t.text IS NOT NULL AND t.entities_json IS NOT NULL "
        "RETURN count(t) AS total, "
        "count(CASE WHEN t.audited_at IS NOT NULL THEN 1 END) AS already_audited"
    )
    row = r.single()
    total = row["total"]
    audited = row["already_audited"]
    print(f"Total eligible: {total}")
    print(f"Already audited: {audited}")
    print(f"Remaining: {total - audited}")
