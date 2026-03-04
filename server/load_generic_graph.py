"""
Generic Graph Data Loader
Handles loading any hierarchical JSON data into ArangoDB with automatic edge creation

Supports:
- Custom node types
- Nested relationships
- Array references
- Automatic edge collection creation
"""

import json
import argparse
import getpass
import re
from typing import List, Dict, Any, Optional, Tuple
from arango import ArangoClient
from arango.exceptions import ArangoServerError, ArangoClientError, ServerVersionError
from datetime import datetime


def get_timestamp(str_format: str = "%Y-%m-%d %H:%M:%S") -> str:
    return datetime.now().strftime(str_format)


def connect_to_arango_client(host: str):
    try:
        client = ArangoClient(hosts=host)
        return client
    except Exception as e:
        print(f'{get_timestamp()} -- Could not connect to ArangoDB client at "{host}": {e}')
        return None


def connect_to_arango_db(client: ArangoClient, db_name: str, username: str, password: str, max_retries: int = 3): 
    retries = 0
    if password is None:
        password = getpass.getpass(f'Please enter the password for user {username} for access to the {db_name} database: ')
        
    while retries < max_retries:
        try:
            db = client.db(db_name, username=username, password=password)     
            vers = db.version()
            print(f'{get_timestamp()} -- Successfully connected to database {db_name} running version {vers}.')
            return db
        except (ConnectionAbortedError, ServerVersionError) as e:
            retries += 1
            print(f'{get_timestamp()} -- Connection refused for db {db_name}.')
            password = getpass.getpass(f'Input password to try again: ')
        except Exception as e:
            print(f'\n**** {type(e)}: {e} ****\n')
            retries += 1
            print(f'{get_timestamp()} -- Could not connect to db "{db_name}".')
    
    return None


def get_collection(db, collection_name: str, create_on_absence: bool = True, is_edge_collection: bool = False):
    if db.has_collection(collection_name):
        return db.collection(collection_name)
    elif create_on_absence:
        print(f'{get_timestamp()} -- Collection "{collection_name}" was not found; creating new Collection.')
        return db.create_collection(collection_name, edge=is_edge_collection)
    else:
        print(f'{get_timestamp()} -- Collection "{collection_name}" was not found and a new Collection was NOT created.')
        return None


def insert_document(document: dict, collection, replace_if_exists: bool = False, overwrite_mode: str = 'update', debug: bool = False):
    """Insert or update a document in ArangoDB."""
    success = False
    doc_type = document.pop('type')
    
    if collection.get(document) is None:
        if debug:
            print(f'{get_timestamp()} -- Inserting document {document["_key"]} into {collection.name}...')
        success = collection.insert(document, silent=True)       
    else:
        if replace_if_exists:
            if debug:
                print(f'{get_timestamp()} -- Document with _key {document["_key"]} already exists. Replacing...')
            success = collection.insert(document, overwrite_mode=overwrite_mode, keep_none=True, silent=True)
        else:
            if debug:
                print(f'{get_timestamp()} -- Document with _key {document["_key"]} already exists.')
            success = True
    
    return {'_key': document['_key'], 'type': doc_type, 'success': success}


def create_edge(edge_type: str, key: str, from_node_key: str, to_node_key: str, src_attr: str = None, dest_attr: str = None):
    """Create an edge document."""
    edge = {
        'type': edge_type,
        '_key': key,
        '_from': from_node_key,
        '_to': to_node_key
    }
    
    if src_attr:
        edge['src_attr'] = src_attr
    if dest_attr:
        edge['dest_attr'] = dest_attr
    
    return edge


class GenericGraphLoader:
    """
    Generic loader that can handle any JSON structure and convert it to a graph.
    
    Automatically detects:
    - Node references (objects with _key or _id)
    - Array references (lists of node references)
    - Nested objects (become separate nodes with edges)
    """
    
    def __init__(self, db, debug: bool = False):
        self.db = db
        self.debug = debug
        self.nodes = []
        self.edges = []
        self.edge_keys_seen = set()
    
    def detect_node_reference(self, value: Any) -> Optional[str]:
        """
        Detect if a value is a reference to another node.
        Returns the node ID if it's a reference, None otherwise.
        """
        if isinstance(value, dict):
            # Check for _key or _id
            if '_key' in value and 'type' in value:
                return f"{value['type']}/{value['_key']}"
            elif '_id' in value:
                return value['_id']
        elif isinstance(value, str):
            # Check if it's a Collection/key format
            if '/' in value and not value.startswith('http'):
                return value
        
        return None
    
    def add_edge_if_new(self, edge: dict):
        """Add edge only if we haven't seen this connection before."""
        edge_key = edge['_key']
        if edge_key not in self.edge_keys_seen:
            self.edges.append(edge)
            self.edge_keys_seen.add(edge_key)
    
    def process_value(
        self, 
        parent_id: str, 
        attr_name: str, 
        value: Any, 
        edge_type: str = 'REFERENCES'
    ):
        """
        Process a value from a node, creating edges as needed.
        
        Handles:
        - Single node references
        - Arrays of node references
        - Nested objects (creates new nodes)
        """
        # Handle single node reference
        node_ref = self.detect_node_reference(value)
        if node_ref:
            edge_key = f"{parent_id}_to_{node_ref}".replace('/', ':')
            edge = create_edge(edge_type, edge_key, parent_id, node_ref, attr_name, '_key')
            self.add_edge_if_new(edge)
            return
        
        # Handle array of references
        if isinstance(value, list):
            for item in value:
                item_ref = self.detect_node_reference(item)
                if item_ref:
                    edge_key = f"{parent_id}_to_{item_ref}".replace('/', ':')
                    edge = create_edge(edge_type, edge_key, parent_id, item_ref, attr_name, '_key')
                    self.add_edge_if_new(edge)
                elif isinstance(item, dict) and '_key' not in item:
                    # Nested object without _key - process recursively
                    self.process_nested_object(parent_id, attr_name, item)
        
        # Handle nested object
        elif isinstance(value, dict) and '_key' not in value:
            self.process_nested_object(parent_id, attr_name, value)
    
    def process_nested_object(self, parent_id: str, attr_name: str, obj: dict):
        """Process a nested object, looking for references within it."""
        for key, val in obj.items():
            self.process_value(parent_id, f"{attr_name}.{key}", val)
    
    def load_node(self, node: dict, parent_id: Optional[str] = None, parent_attr: Optional[str] = None) -> str:
        """
        Load a node and process its attributes for edges.
        
        Returns the node's full ID (Collection/key).
        """
        if 'type' not in node:
            raise ValueError(f"Node missing 'type' field: {node.get('_key', 'unknown')}")
        
        node_type = node['type']
        node_id = f"{node_type}/{node['_key']}"
        
        # Create a clean copy for insertion (remove nested objects)
        clean_node = node.copy()
        
        # Process attributes to find edges
        for attr_name, attr_value in list(node.items()):
            if attr_name in ['_key', 'type']:
                continue
            
            # Determine edge type based on attribute name patterns
            edge_type = self.infer_edge_type(attr_name, attr_value)
            
            # Process the value for references
            self.process_value(node_id, attr_name, attr_value, edge_type)
            
            # Convert complex nested objects to references in clean_node
            if isinstance(attr_value, list):
                refs = []
                for item in attr_value:
                    ref = self.detect_node_reference(item)
                    if ref:
                        refs.append(ref)
                if refs:
                    clean_node[attr_name] = refs
            elif isinstance(attr_value, dict):
                ref = self.detect_node_reference(attr_value)
                if ref:
                    clean_node[attr_name] = ref
        
        # Add node to list
        self.nodes.append(clean_node)
        
        # Create edge from parent if specified
        if parent_id and parent_attr:
            edge_key = f"{parent_id}_to_{node_id}".replace('/', ':')
            edge_type = self.infer_edge_type(parent_attr, node)
            edge = create_edge(edge_type, edge_key, parent_id, node_id, parent_attr, '_key')
            self.add_edge_if_new(edge)
        
        return node_id
    
    def infer_edge_type(self, attr_name: str, value: Any) -> str:
        """
        Infer the edge type based on attribute name and value.
        
        Common patterns:
        - steps, next_steps -> LEADS_TO
        - artifacts, outputs -> PRODUCES
        - ttp_id, ttp_ids -> REFERENCES
        - parent, contains -> CONTAINS
        """
        attr_lower = attr_name.lower()
        
        if 'next' in attr_lower or 'step' in attr_lower:
            return 'LEADS_TO'
        elif 'artifact' in attr_lower or 'output' in attr_lower or 'produce' in attr_lower:
            return 'PRODUCES'
        elif 'ttp' in attr_lower or 'reference' in attr_lower or 'refer' in attr_lower:
            return 'REFERENCES'
        elif 'contain' in attr_lower or 'child' in attr_lower or 'member' in attr_lower:
            return 'CONTAINS'
        elif 'collab' in attr_lower or 'team' in attr_lower:
            return 'COLLABORATION_WITH'
        else:
            return 'REFERENCES'  # Default fallback
    
    def load_from_dict(self, data: dict):
        """
        Load graph data from a dictionary.
        
        Expected structure (flexible):
        {
            "collection_name": [
                {"_key": "...", "type": "...", ...},
                ...
            ],
            ...
        }
        
        OR for hierarchical data:
        {
            "root_nodes": [
                {
                    "_key": "...",
                    "type": "...",
                    "children": [...]
                }
            ]
        }
        """
        # Handle hierarchical structures (like processes with nested steps)
        if 'processes' in data:
            self.load_hierarchical_processes(data['processes'])
        else:
            # Handle flat collection structure
            for collection_name, items in data.items():
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict) and '_key' in item:
                            if 'type' not in item:
                                item['type'] = collection_name
                            self.load_node(item)
    
    def load_hierarchical_processes(self, processes: List[dict]):
        """
        Load the 318th-specific hierarchical process structure.
        
        Structure: Process -> steps[] -> artifacts[]
        """
        for process in processes:
            # Ensure type is set
            if 'type' not in process:
                process['type'] = 'Process'
            
            # Extract steps
            steps = process.get('steps', [])
            
            # Convert steps to references
            step_refs = []
            for step in steps:
                if 'type' in step and '_key' in step:
                    step_refs.append(f"{step['type']}/{step['_key']}")
            
            # Update process with step references
            process_copy = process.copy()
            process_copy['steps'] = step_refs
            
            # Load process node
            process_id = self.load_node(process_copy)
            
            # Process each step
            for step in steps:
                # Extract artifacts
                artifacts = step.get('artifacts', [])
                
                # Convert artifacts to references
                artifact_refs = []
                for artifact in artifacts:
                    if 'type' in artifact and '_key' in artifact:
                        artifact_refs.append(f"{artifact['type']}/{artifact['_key']}")
                
                # Update step with artifact references
                step_copy = step.copy()
                step_copy['artifacts'] = artifact_refs
                
                # Load step node
                step_id = self.load_node(step_copy, parent_id=process_id, parent_attr='steps')
                
                # Create STARTS_WITH edge if initial step
                if step.get('is_initial_step'):
                    edge_key = f"{process_id}_startswith_{step_id}".replace('/', ':')
                    edge = create_edge('STARTS_WITH', edge_key, process_id, step_id, 'steps', '_key')
                    self.add_edge_if_new(edge)
                
                # Process next_steps to create LEADS_TO edges
                for next_step_ref in step.get('next_steps', []):
                    edge_key = f"{step_id}_to_{next_step_ref}".replace('/', ':')
                    edge = create_edge('LEADS_TO', edge_key, step_id, next_step_ref, 'next_steps', '_key')
                    self.add_edge_if_new(edge)
                
                # Load artifacts
                for artifact in artifacts:
                    artifact_id = self.load_node(artifact, parent_id=step_id, parent_attr='artifacts')
                    
                    # Handle TTP references
                    if 'ttp_id' in artifact:
                        ttp_ref = f"TTPArtifact/{artifact['ttp_id']}"
                        edge_key = f"{artifact_id}_to_{ttp_ref}".replace('/', ':')
                        edge = create_edge('REFERENCES', edge_key, artifact_id, ttp_ref, 'ttp_id', '_key')
                        self.add_edge_if_new(edge)
                    
                    if 'ttp_ids' in artifact:
                        for ttp_id in artifact['ttp_ids']:
                            ttp_ref = f"TTPArtifact/{ttp_id}"
                            edge_key = f"{artifact_id}_to_{ttp_ref}".replace('/', ':')
                            edge = create_edge('REFERENCES', edge_key, artifact_id, ttp_ref, 'ttp_ids', '_key')
                            self.add_edge_if_new(edge)
    
    def insert_to_db(self, replace: bool = False, create_collections: bool = True):
        """Insert all loaded nodes and edges into ArangoDB."""
        node_success = []
        edge_success = []
        
        print(f'{get_timestamp()} -- Inserting {len(self.nodes)} nodes...')
        
        # Insert nodes
        for node in self.nodes:
            doc_type = node['type']
            collection = get_collection(self.db, doc_type, create_on_absence=create_collections, is_edge_collection=False)
            
            if collection:
                result = insert_document(node, collection, replace_if_exists=replace, debug=self.debug)
                node_success.append(result)
        
        print(f'{get_timestamp()} -- Inserting {len(self.edges)} edges...')
        
        # Insert edges
        for edge in self.edges:
            edge_type = edge['type']
            collection = get_collection(self.db, edge_type, create_on_absence=create_collections, is_edge_collection=True)
            
            if collection:
                result = insert_document(edge, collection, replace_if_exists=replace, debug=self.debug)
                edge_success.append(result)
        
        # Report results
        nodes_inserted = sum(1 for r in node_success if r['success'])
        edges_inserted = sum(1 for r in edge_success if r['success'])
        
        print(f'\n{get_timestamp()} -- Insert Results:')
        print(f'  Nodes: {nodes_inserted}/{len(self.nodes)} inserted')
        print(f'  Edges: {edges_inserted}/{len(self.edges)} inserted')
        
        return node_success, edge_success


def main():
    parser = argparse.ArgumentParser(
        prog='load_generic_graph.py',
        description='Load generic graph data into ArangoDB with automatic edge detection'
    )
    
    parser.add_argument('input_file', help='JSON file containing graph data')
    parser.add_argument('-a', '--arango-host', default='http://localhost:8529',
                       help='ArangoDB host URL')
    parser.add_argument('-d', '--db-name', default='AUTO_DB',
                       help='Database name')
    parser.add_argument('-u', '--username', default='root',
                       help='Database username')
    parser.add_argument('-p', '--password', default=None,
                       help='Database password')
    parser.add_argument('-c', '--create-collections', action='store_true',
                       help='Create collections if they don\'t exist')
    parser.add_argument('-r', '--replace', action='store_true',
                       help='Replace existing documents')
    parser.add_argument('--debug', action='store_true',
                       help='Enable debug output')
    
    args = parser.parse_args()
    
    print("="*80)
    print("GENERIC GRAPH LOADER")
    print("="*80)
    print(f"Input file: {args.input_file}")
    print(f"Database: {args.db_name}")
    print(f"Replace existing: {args.replace}")
    print("="*80)
    print()
    
    # Connect to database
    client = connect_to_arango_client(args.arango_host)
    if not client:
        return 1
    
    db = connect_to_arango_db(client, args.db_name, args.username, args.password)
    if not db:
        return 1
    
    # Load data from file
    print(f'{get_timestamp()} -- Loading data from {args.input_file}...')
    with open(args.input_file, 'r') as f:
        data = json.load(f)
    
    # Process and load graph
    loader = GenericGraphLoader(db, debug=args.debug)
    loader.load_from_dict(data)
    
    print(f'{get_timestamp()} -- Processed {len(loader.nodes)} nodes and {len(loader.edges)} edges')
    
    # Insert into database
    loader.insert_to_db(replace=args.replace, create_collections=args.create_collections)
    
    print("\n" + "="*80)
    print("LOADING COMPLETE")
    print("="*80)
    
    return 0


if __name__ == "__main__":
    exit(main())