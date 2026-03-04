from arango import ArangoClient
from discovery import OntologyRelationshipResolver

client = ArangoClient(hosts='http://localhost:8529')
db = client.db('AUTO_DB', username='root', password='devpass')

resolver = OntologyRelationshipResolver(db)

# Pairs with ONLY ONE valid relationship
print('=== Single-option pairs ===')
pairs = [
    ('LibraryModule', 'RobotLog'),
    ('DevelopmentStory', 'Person'),
    ('Person', 'Team'),
    ('RobotLog', 'LibraryModule'),
]
for src, tgt in pairs:
    rels = resolver.get_valid_relationships(src, tgt)
    labels = [r['label'] for r in rels]
    print(f'{src} -> {tgt}: {labels}')

# Pairs with MULTIPLE valid relationships (via inheritance)
print('')
print('=== Multi-option pairs (inheritance) ===')
multi_pairs = [
    ('LibraryModule', 'LibraryModule'),
    ('MitreAttack', 'MitreAttack'),
    ('DevelopmentStory', 'DevelopmentStory'),
]
for src, tgt in multi_pairs:
    rels = resolver.get_valid_relationships(src, tgt)
    labels = [r['label'] for r in rels]
    print(f'{src} -> {tgt}: {labels}')
