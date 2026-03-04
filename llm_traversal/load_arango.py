import json
import argparse
import getpass
import re
from arango import ArangoClient
from arango.exceptions import ArangoServerError, ArangoClientError, ServerVersionError
from datetime import datetime


def get_timestamp(str_format: str = "%Y-%m-%d %H:%M:%S"):
    return datetime.now().strftime(str_format)


def connect_to_arango_client(host: str):
    try:
        client = ArangoClient(hosts=host)
    except:
        print(f'{get_timestamp()} -- Could not connect to ArangoDB client at "{host}"')
        return None
    
    return client


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
            password = getpass.getpass(f'Input password to try again:  ')
        except Exception as e:
            print(f'\n**** {type(e)}: {e} ****\n')
            retries += 1
            print(f'{get_timestamp()} -- Could not connect to db "{db_name}".')
    
    return None
    

def is_simple_attr_type(attr_type):
    primitive_types = ['Text', 'Datetime', 'Boolean', 'Number', 'Email', 'IPAddress']
    if attr_type.startswith('List'):
        match = re.search('List\[(.*)\]', s)
        list_type_options = match.group(1).split('|') if match else []
        if all(is_simple_attr_type(re.search('(.*)<(.*)>', opt).group(1)) for opt in list_type_options):
            return True, "list"
        else:
            return False, "list"
    elif attr_type.startswith('JSON'):
        json_str = re.search('JSON{(.*)}', s)
        json_dict = json.loads(json_str)
        if all(is_simple_attr_type(v) for k,v in json_dict.items()):
            return True, "json"
        else:
            return False, "json"
    elif attr_type in primitive_types:
        return True, "single"

    return False, "single"
        

def get_collection(db, collection_name: str, create_on_absence: bool = True):
    if db.has_collection(collection_name):
        return db.collection(collection_name)
    elif create_on_absence:
        print(f'{get_timestamp()} -- Collection "{collection_name}" was not found; creating new Collection.')
        return db.create_collection(collection_name)
    else:
        print(f'{get_timestamp()} -- Collection "{collection_name}" was not found and a new Collection was NOT created.')
        return None
  

def print_insert_success(success: dict, custom_message: str = None):
    message = custom_message
    is_success = success['success']
    key = success['_key']
    collection = success['type']
    
    if message is None:
        if is_success == True:
            message = f'Document {key} was successfully inserted into {collection}.'
        else:
            message = f'Failed to insert document {key} into {collection}.'
    
    print(f'{get_timestamp()} -- {message}')


def print_insert_success_list(successes: dict, custom_message: str = None, fail_only: bool = False):
    for success in successes:
        if not (fail_only and success['success']):
            print_insert_success(success, custom_message=custom_message)


def add_doc_to_collection(document: dict, collection, replace_if_exists: bool = False, overwrite_mode: str = 'update', debug: bool = False):
    success = False
    doc_type = document.pop('type')
    if collection.get(document) is None:
        if debug:
            print(f'{get_timestamp()} -- Inserting document {document["_key"]} into {collection}...')
        success = collection.insert(document, silent=True)       
        
    else:
        if replace_if_exists:
            if debug:
                print(f'{get_timestamp()} -- Document with _key {document["_key"]} already exists. Replacing it with new document:\n{json.dumps(document, indent=4)}')
            success = collection.insert(document, overwrite_mode=overwrite_mode, keep_none=True, silent=True)
            
        else:
            if debug:
                print(f'{get_timestamp()} -- Document with _key {document["_key"]} already exists.')
            success = True
    
    return {'_key': document['_key'], 'type': doc_type, 'success': success}


def insert_docs(raw_docs: list[dict], db, replace_if_exists: bool = False, overwrite_mode: str = 'update', debug: bool = False, create_collection_on_absence: bool = True):
    # take the documents with 'type' still in them as the collection name and insert them into their collection/type
    successes = []
    for doc in raw_docs:
        if doc is None:
            successes.append({'_key': None, 'type': None, 'success': False})
            pass
        doc_type = doc['type']
        collection = get_collection(db, doc_type, create_on_absence=create_collection_on_absence)
        if collection is None:
            if debug:
                print(f'{get_timestamp()} -- Collection not found for document {doc["_key"]} with type {doc_type}.')
            successes.append({'_key': doc['_key'], 'type': doc_type, 'success': False})
        else:          
            try:
                success = add_doc_to_collection(doc, collection, replace_if_exists=replace_if_exists, overwrite_mode=overwrite_mode)
                successes.append(success)
            except Exception as e:
                if debug:
                    print(f'{type(e)}: {e}\nDocument:\n')
                    print(doc)
            
    return successes


def create_edge(edge_type, key, from_node_key, to_node_key, src_attr, dest_attr):
    return {'type': edge_type, '_key': key, '_from': from_node_key, '_to': to_node_key, 'src_attr': src_attr, 'dest_attr': dest_attr}


def handle_process(process: dict, debug: bool = False):
    # assign the step dicts to a temp var
    proc_steps = process['steps']
    
    # change the steps value to a list of the step keys/names
    process['steps'] = [f"{step['type']}/{step['_key']}" for step in process['steps']]
    
    # Ensure the type key exists so we later know to load it into the Process collection
    if not 'type' in process:
        process['type'] = 'Process'
    
    # debug
    if debug:
        print(process)
        print()
    
    return process, proc_steps


def handle_step(step: dict, process: dict, edges: list, debug: bool = False):
    # connect the process to the step
    process_key = f"Process/{process['_key']}"
    step_key = f"{step['type']}/{step['_key']}"
    edge_key = f'{process_key}_to_{step_key}'.replace('/', ':')
    new_edges = []
    if not any(edge.get('_key') == edge_key for edge in edges):
        new_edges.append(create_edge('CONTAINS', edge_key, process_key, step_key, 'steps', '_key'))
    
    if step['is_initial_step']:
        edge_key = f'{process_key}_startswith_{step_key}'.replace('/', ':')
        new_edges.append(create_edge('STARTS_WITH', edge_key, process_key, step_key, 'steps', '_key'))
    
    # Connect the step to the next steps
    for next_step in step['next_steps']:
        edge_key = f'{step_key}_to_{next_step}'.replace('/', ':')
        if not any(edge.get('_key') == edge_key for edge in edges):
            new_edges.append(create_edge('LEADS_TO', edge_key, step_key, next_step, 'next_steps', '_key'))
            
    # assign the artifacts to a temp var
    step_artifacts = step['artifacts']
    
    # change the artifacts to a list of artifact _keys
    step['artifacts'] = [f"{artifact['type']}/{artifact['_key']}" for artifact in step['artifacts']]
    
    # debug
    if debug:
        print(step)
        print()    
    
    return step, new_edges, step_artifacts, step_key


def handle_artifact(artifact: dict, step_key: str, edges: list, debug: bool = False):        
    # connect the step to its artifacts
    # If artifact type is TTPArtifact we want a REFERENCES type instead of PRODUCES
    art_edge_type = 'REFERENCES' if (artifact['type'] == 'TTPArtifact') else 'PRODUCES'
    artifact_key = f"{artifact['type']}/{artifact['_key']}"
    edge_key = f"{step_key}_to_{artifact_key}".replace('/', ':')
    new_edges = []
    if not any(edge.get('_key') == edge_key for edge in edges):
        new_edges.append(create_edge(art_edge_type, edge_key, step_key, artifact_key, 'artifacts', '_key'))
        
    if 'ttp_id' in artifact:
        # connect artifact to ttp
        ttp_key = f"TTPArtifact/{artifact['ttp_id']}"
        edge_key = f"{artifact_key}_to_{ttp_key}".replace('/', ':')
        if not any(edge.get('_key') == edge_key for edge in edges):
            new_edges.append(create_edge('REFERENCES', edge_key, artifact_key, ttp_key, 'ttp_id', '_key'))
        
    if 'ttp_ids' in artifact:
        # connect artifact to all ttps
        for ttp in artifact['ttp_ids']:
            ttp_key = f"TTPArtifact/{ttp}"
            edge_key = f"{artifact_key}_to_{ttp_key}".replace('/', ':')
            if not any(edge.get('_key') == edge_key for edge in edges):
                new_edges.append(create_edge('REFERENCES', edge_key, artifact_key, ttp_key, 'ttp_ids', '_key'))
                
    return artifact, new_edges


def handle_node(node, schema, create_edges=True):
    node_type = node['type']
    nodes = []
    edges = []

    for attr in node.keys():
        is_simple, attr_format = is_simple_attr_type(schema[node_type][attr]['type'])
        if not is_simple:
            if isinstance(node[attr], dict):
                nodes.append(handle_node(attr, schema, create_edges=create_edges))
                if attr_format == 'list':
                    node[attr] = 
                node[attr] = 
            


def handle_docs_from_file(json_file, schema, debug=False, create_edges=True):
    with open(json_file, 'r') as file:
        data = json.load(file)
    
    nodes = []
    edges = []
    node_schema = schema['node_collections']
    edge_schema = schema['edge_collections']

    for node in data['nodes']:
        handle_node(node, node_schema, create_edges=create_edges)
        
    
    for process in process_data['processes']:
        # debug
        if debug:
            print(f'Process: {process["name"]}')
        ### create process dict to insert ###
        proc_node, proc_steps = handle_process(process, debug=debug)
        nodes.append(proc_node)
        
        ### create step dicts to insert
        for step in proc_steps:
            step_node, step_edges, step_artifacts, step_key = handle_step(step, process, edges, debug=debug)
            nodes.append(step_node)
            edges.extend(step_edges)
            
            # create artifact dicts to insert
            for artifact in step_artifacts:
                art_node, art_edges = handle_artifact(artifact, step_key, edges, debug=debug)
                nodes.append(art_node)
                edges.extend(art_edges)
            
    # debug
    if debug:
        print(json.dumps(edges, indent=4))
    
    return nodes, edges
    

def main():
    ### get arguments ###
    parser = argparse.ArgumentParser(
                    prog='load_arango.py',
                    description='Loads a list of nodes and/or edges from a JSON file into the appropriate ArangoDB Collections.')
                    
    parser.add_argument('input_file', help='The JSON file containing the data.')
    parser.add_argument('-a', '--arangodb-host', help='The host address and port of the ArangoDB instance.', default='http://localhost:8529')
    parser.add_argument('-d', '--db-name', help='The name of the database within the ArangoDB instance to interact with.', default='Process')
    parser.add_argument('-u', '--username', help='The username to sign into the ArangoDB database.', default='root')
    parser.add_argument('-p', '--password', help='The password to sign into the ArangoDB database.', default=None)
    parser.add_argument('-c', '--create-collection-on-absence', help='Create collection if it does not exist.', action="store_true")
    parser.add_argument('-r', '--replace', help='Replace the document if it already exists.', action="store_true")
    parser.add_argument('--debug', action='store_true', help='Allow debug printing to stdout.')
    
    args = parser.parse_args()

    ### Ingest the data ###
    input_file = args.input_file
    host = args.arangodb_host
    db_name = args.db_name
    username = args.username
    password = args.password 
    debug = args.debug
    create_collection_on_absence = args.create_collection_on_absence
    replace = args.replace
    
    client = connect_to_arango_client(host)
    db = connect_to_arango_db(client, db_name, username, password)
    if db is None:
        print(f'Could not connect to {db_name} at {host} as {username}. Exiting now.')
        return 0
    
    nodes, edges = handle_docs_from_file(input_file, debug)
    
    node_successes = insert_docs(nodes, db, replace_if_exists=replace, create_collection_on_absence=create_collection_on_absence, debug=debug)
    edge_successes = insert_docs(edges, db, replace_if_exists=replace, create_collection_on_absence=create_collection_on_absence, debug=debug)

    
    print(f'\nNode insert results ({len([n for n in node_successes if n["success"] == True])}/{len(node_successes)} loaded successfully):\n{print_insert_success_list(node_successes, fail_only=True)}')
    print(f'Edge insert results ({len([e for e in edge_successes if e["success"] == True])}/{len(edge_successes)} loaded successfully):\n{print_insert_success_list(edge_successes, fail_only=True)}')
    

if __name__=="__main__":
    main()
