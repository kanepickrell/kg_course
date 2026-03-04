import json

# Load your existing file
with open('taxonomies/mitre_techniques.json', 'r') as f:
    data = json.load(f)

# Convert to bulk import format
bulk_terms = []
for term in data['terms']:
    bulk_terms.append({
        "uri": term['uri'],
        "label": term['label'],
        "aliases": [term.get('technique_name', '')] + term.get('aliases', []),
        "definition": term.get('definition', ''),
        "broader": term.get('broader')
    })

# Output
print(json.dumps(bulk_terms, indent=2))

# Or save to file
with open('mitre_techniques_bulk.json', 'w') as f:
    json.dump(bulk_terms, f, indent=2)
    print(f"\nSaved {len(bulk_terms)} terms to mitre_techniques_bulk.json")