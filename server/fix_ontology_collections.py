from arango import ArangoClient
import os

ARANGO_HOST = os.getenv("ARANGO_HOST", "http://localhost:8529")
ARANGO_USER = os.getenv("ARANGO_USER", "root")
ARANGO_PASSWORD = os.getenv("ARANGO_PASSWORD", "devpass")
ARANGO_DB = os.getenv("ARANGO_DB", "AUTO_DB")

client = ArangoClient(hosts=ARANGO_HOST)
db = client.db(ARANGO_DB, username=ARANGO_USER, password=ARANGO_PASSWORD)

# Use names WITHOUT leading underscore
collections = [
    ("ontology_concepts", False),
    ("taxonomy_schemes", False),
    ("taxonomy_terms", False),
    ("relationship_types", False),
    ("ontology_edges", True),  # Edge collection
]

for name, is_edge in collections:
    if not db.has_collection(name):
        db.create_collection(name, edge=is_edge)
        print(f"✓ Created: {name}")
    else:
        print(f"  Already exists: {name}")

print("\nDone!")