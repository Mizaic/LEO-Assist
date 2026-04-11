import sys

sys.path.insert(0, ".")
from dotenv import load_dotenv

load_dotenv("secrets/.env.config", override=False)
load_dotenv("secrets/.env", override=False)
from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()
from libs.neo4j_client.client import PatientGraphClient

c = PatientGraphClient()

# Check what relationships the ncda-cancer-types ValueSet has
rows = c.run(
    "MATCH (vs:ValueSet {id: 'ncda-cancer-types'})-[r]->(n) RETURN type(r) AS rel, labels(n) AS nlabels, keys(n) AS props LIMIT 5"
)
print("Relationships from ncda-cancer-types:", rows)

# Check what properties the ValueSet itself has
rows2 = c.run(
    "MATCH (vs:ValueSet {id: 'ncda-cancer-types'}) RETURN keys(vs) AS props, vs AS node"
)
print("ValueSet props:", rows2)

# Maybe concepts are stored directly as properties of the ValueSet?
rows3 = c.run(
    "MATCH (vs:ValueSet {id: 'ncda-cancer-types'}) RETURN vs.concepts AS concepts LIMIT 1"
)
print("vs.concepts:", rows3[:1] if rows3 else "none")
c.close()
