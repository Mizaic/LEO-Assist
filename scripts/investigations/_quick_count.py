import sqlite3
from pathlib import Path

db = sqlite3.connect(Path(__file__).parent / "encounter_audit" / "encounter_audit.db")
done = db.execute("SELECT COUNT(*) FROM encounters WHERE status='done'").fetchone()[0]
pending = db.execute(
    "SELECT COUNT(*) FROM encounters WHERE status='pending'"
).fetchone()[0]
sf = db.execute("SELECT COUNT(*) FROM surface_form_gaps").fetchone()[0]
print(f"Encounters done: {done:,}  pending: {pending}")
print(f"Surface form gaps so far: {sf:,}")
db.close()
