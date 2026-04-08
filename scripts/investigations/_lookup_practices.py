from libs.neo4j_client.client import PatientGraphClient
c = PatientGraphClient()
rows = c.run(
    "MATCH (o:Organization) WHERE o.id IN ['C82070', 'C82061'] "
    "RETURN o.id AS id, o.name AS name, o.ods_code AS ods"
)
for r in rows:
    print(r)
c.close()
