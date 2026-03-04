"""
LLM Edge Discovery Pipeline
Converted from InferConnBot.ipynb for production use

This script uses a 3-stage LLM ensemble to discover semantic relationships in graph data:
1. Binary classification (Should edge exist?)
2. Edge type classification (What relationship type?)
3. Confidence rating (How strong is the connection?)
"""

import argparse
import getpass
import json
import os
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

from arango import ArangoClient, ServerVersionError, DocumentUpdateError
from ollama import Client as OllamaClient
from tqdm import tqdm


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def get_timestamp(str_format: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Get current timestamp as formatted string."""
    return datetime.now().strftime(str_format)


def without(d: dict, keys: list) -> dict:
    """Return dictionary without specified keys."""
    new_d = d.copy()
    for key in keys:
        new_d.pop(key, None)
    return new_d


# ============================================================================
# ARANGO CONNECTION FUNCTIONS
# ============================================================================

def connect_to_arango_client(host: str) -> Optional[ArangoClient]:
    """Connect to ArangoDB client."""
    try:
        client = ArangoClient(hosts=host)
        return client
    except Exception as e:
        print(f'{get_timestamp()} -- Could not connect to ArangoDB client at "{host}": {e}')
        return None


def connect_to_arango_db(
    client: ArangoClient, 
    db_name: str, 
    username: str, 
    password: Optional[str], 
    max_retries: int = 3
):
    """Connect to ArangoDB database with retry logic."""
    retries = 0
    if password is None:
        password = getpass.getpass(
            f'Please enter the password for user {username} for access to the {db_name} database: '
        )
        
    while retries < max_retries:
        try:
            db = client.db(db_name, username=username, password=password)
            vers = db.version()
            print(f'{get_timestamp()} -- Successfully connected to database {db_name} running version {vers}.')
            return db
        except (ConnectionAbortedError, ServerVersionError) as e:
            retries += 1
            print(f'{get_timestamp()} -- Connection refused for db {db_name}.')
            if retries < max_retries:
                password = getpass.getpass(f'Input password to try again: ')
        except Exception as e:
            print(f'\n**** {type(e)}: {e} ****\n')
            retries += 1
            print(f'{get_timestamp()} -- Could not connect to db "{db_name}".')
    
    return None


# ============================================================================
# GRAPH QUERY FUNCTIONS
# ============================================================================

def get_graph_edges(db, aql, graph_name: str, include_node_docs: bool = True) -> List[Dict]:
    """
    Retrieve all edges from the graph with optional node document inclusion.
    
    Returns list of edge dictionaries with structure:
    {
        '_id': 'EDGE_TYPE/key',
        '_from': 'Collection/key',
        '_to': 'Collection/key',
        '_from_node': {...} if include_node_docs,
        '_to_node': {...} if include_node_docs,
        ...edge attributes...
    }
    """
    if include_node_docs:
        query = f"""
        FOR edge IN GRAPH_EDGES('{graph_name}', {{}}, {{}})
            LET from_doc = DOCUMENT(edge._from)
            LET to_doc = DOCUMENT(edge._to)
            RETURN MERGE(edge, {{
                _from_node: from_doc,
                _to_node: to_doc
            }})
        """
    else:
        query = f"""
        FOR edge IN GRAPH_EDGES('{graph_name}', {{}}, {{}})
            RETURN edge
        """
    
    cursor = aql.execute(query)
    edges = list(cursor)
    
    print(f'{get_timestamp()} -- Retrieved {len(edges)} edges from graph "{graph_name}"')
    return edges


def get_all_node_pairs(db, aql, collections: List[str]) -> List[Dict]:
    """
    Get all possible node pairs from specified collections for edge discovery.
    
    Returns list of dicts with structure:
    {
        'src_node': {...full node doc...},
        'pair_node': {...full node doc...}
    }
    """
    # Build query to get all nodes from specified collections
    # Note: ArangoDB UNION requires array syntax
    collection_queries = [f'(FOR n IN {coll} RETURN n)' for coll in collections]
    
    query = f"""
    LET nodes = UNION(
        {', '.join(collection_queries)}
    )
    FOR src IN nodes
        FOR pair IN nodes
            FILTER src._id != pair._id
            LIMIT 1000
            RETURN {{
                src_node: src,
                pair_node: pair
            }}
    """
    
    cursor = aql.execute(query)
    pairs = list(cursor)
    
    print(f'{get_timestamp()} -- Generated {len(pairs)} node pairs for analysis')
    return pairs


# ============================================================================
# LLM PROMPTING FUNCTIONS
# ============================================================================

def prompt_and_response(
    ollama_client: OllamaClient,
    model: str,
    prompt: str,
    quiet: bool = True,
    options: dict = None
) -> Optional[str]:
    """Send prompt to Ollama and get response."""
    try:
        response = ollama_client.generate(
            model=model,
            prompt=prompt,
            options=options or {}
        )
        
        if not quiet:
            print(f"Response: {response['response']}")
        
        return response['response'].strip()
    except Exception as e:
        print(f"Error calling Ollama: {e}")
        return None


def part1_prompt(
    edge_pairs: List[Dict],
    ollama_client: OllamaClient,
    model: str = 'gemma3:27b-it-qat',
    quiet: bool = True,
    options: dict = None,
    src_node_key: str = 'src_node',
    pair_node_key: str = 'pair_node'
) -> List[Dict]:
    """
    Stage 1: Binary classification - Should edge exist?
    
    Uses fast model to filter candidates quickly.
    """
    part1_responses = []
    options = options or {'temperature': 0.8}
    
    pairings = [
        {
            'src_node': edge[src_node_key],
            'pair_node': edge[pair_node_key]
        }
        for edge in edge_pairs 
        if edge.get(src_node_key) and edge.get(pair_node_key)
    ]
    
    for node_pair in tqdm(pairings, desc='Stage 1: Binary Classification', disable=quiet):
        prompt = f"""Act as a data analyzer. Consider the following data for a graph network, as a source node and a destination node:
{json.dumps(node_pair, indent=2)}

After considering attributes, values, and contexts, answer the following question: 
Should an edge exist between these two nodes? Err on the side of skepticism.
Answers should be in the form of True or False.

Do not provide any conversation, only the boolean True/False as your answer.
"""
        
        response = prompt_and_response(ollama_client, model, prompt, quiet=quiet, options=options)
        
        if response:
            is_connected = response.lower() in ['true', 'yes', 't', 'y']
            part1_responses.append({
                'src_node': node_pair['src_node'],
                'pair_node': node_pair['pair_node'],
                'is_connected': is_connected,
                'raw_response': response
            })
    
    connected_count = sum(1 for r in part1_responses if r['is_connected'])
    print(f'{get_timestamp()} -- Stage 1 complete: {connected_count}/{len(part1_responses)} pairs passed filter')
    
    return part1_responses


def part2_prompt(
    part1_responses: List[Dict],
    ollama_client: OllamaClient,
    model: str = 'llama3.3:70b',
    quiet: bool = True,
    options: dict = None
) -> List[Dict]:
    """
    Stage 2: Edge type classification - What relationship type?
    
    Uses stronger reasoning model to classify relationship.
    """
    part2_responses = []
    options = options or {'temperature': 0.8}
    
    # Only process pairs that passed Stage 1
    pairings = [
        {
            'src_node': edge['src_node'],
            'pair_node': edge['pair_node']
        }
        for edge in part1_responses 
        if edge['is_connected']
    ]
    
    for node_pair in tqdm(pairings, desc='Stage 2: Edge Type Classification', disable=quiet):
        prompt = f"""
Act as a data analyzer for cybersecurity graph relationships.

Given these two nodes:
{json.dumps(node_pair, indent=2)}

Analyze their attributes to determine the relationship type.

**Edge Type Definitions:**
- LEADS_TO: Sequential relationship where source directly precedes destination in time/workflow
- REFERENCES: Source cites or refers to destination for context (not execution)
- PRODUCES: Source creates destination as an output artifact
- CONTAINS: Destination is a part of source
- COLLABORATION_WITH: Destination collaborated with another team to produce Source artifact

**Analysis Instructions:**
1. Identify matching field values (e.g., IDs, names, references)
2. Determine causality and sequence (does one trigger the other?)
3. Choose the MOST appropriate edge type from the list above

**CRITICAL: You MUST respond in EXACTLY this format:**
edge_type|explanation

**Valid edge types (choose ONE):**
LEADS_TO, REFERENCES, PRODUCES, CONTAINS, COLLABORATION_WITH

**Example responses:**
REFERENCES|The source artifact references this TTP ID for attack context
LEADS_TO|The planning step leads to the development step in workflow sequence

**DO NOT include any other text. Start your response with one of the valid edge types followed by | and then the explanation.**

Provide your answer:
"""
        
        response = prompt_and_response(ollama_client, model, prompt, quiet=quiet, options=options)
        
        if response:
            # Parse response (format: "EDGE_TYPE|explanation")
            parts = response.split('|', 1)
            
            if len(parts) >= 2:
                edge_type = parts[0].strip().upper()
                explanation = parts[1].strip()
            else:
                # Fallback: Try to extract edge type from beginning of response
                response_upper = response.strip().upper()
                valid_types = ['LEADS_TO', 'REFERENCES', 'PRODUCES', 'CONTAINS', 'COLLABORATION_WITH']
                edge_type = 'UNKNOWN'
                explanation = response
                
                for valid_type in valid_types:
                    if response_upper.startswith(valid_type):
                        edge_type = valid_type
                        # Remove the edge type from explanation
                        explanation = response[len(valid_type):].strip()
                        if explanation.startswith('|'):
                            explanation = explanation[1:].strip()
                        break
            
            # Validate edge type is one of the allowed types
            valid_types = ['LEADS_TO', 'REFERENCES', 'PRODUCES', 'CONTAINS', 'COLLABORATION_WITH']
            if edge_type not in valid_types:
                if not quiet:
                    print(f'Warning: Invalid edge type "{edge_type}" from response: {response[:100]}...')
                    print(f'Attempting to extract valid type...')
                
                # Try to find a valid type in the response
                found_type = False
                for valid_type in valid_types:
                    if valid_type in response.upper():
                        edge_type = valid_type
                        found_type = True
                        if not quiet:
                            print(f'Extracted edge type: {edge_type}')
                        break
                
                if not found_type:
                    edge_type = 'REFERENCES'  # Default fallback
                    if not quiet:
                        print(f'Using default edge type: {edge_type}')
            
            part2_responses.append({
                'src_node': node_pair['src_node'],
                'pair_node': node_pair['pair_node'],
                'edge_type': edge_type,
                'explanation': explanation,
                'raw_response': response
            })
    
    print(f'{get_timestamp()} -- Stage 2 complete: {len(part2_responses)} edge types classified')
    
    return part2_responses


def part3_prompt(
    part2_responses: List[Dict],
    ollama_client: OllamaClient,
    model: str = 'gemma3:27b-it-qat',
    quiet: bool = True,
    options: dict = None
) -> List[Dict]:
    """
    Stage 3: Confidence rating - How strong is the connection?
    
    Uses fast model to validate Stage 2 results with confidence scores.
    """
    part3_responses = []
    options = options or {'temperature': 0.8}
    
    for i in tqdm(range(len(part2_responses)), desc='Stage 3: Confidence Rating', disable=quiet):
        edge_data = part2_responses[i]
        node_pair = {
            'src_node': edge_data['src_node'],
            'pair_node': edge_data['pair_node']
        }
        
        prompt = f"""
Act as a data analyzer. Consider the following data for a graph network, as a source node and a destination node:
{json.dumps(node_pair, indent=2)}

A connection of type "{edge_data['edge_type']}" has been suggested with this explanation:
"{edge_data['explanation']}"

Rate the strength and accuracy of this connection from 1-10, with:
- 1 meaning no connection should exist or the connection is incorrect/invalid
- 10 being a very strong, accurate connection

Answers should be in the form of an integer between 1 and 10.

Example output: "9"

Think through this problem and then provide me ONLY the conclusion as an integer. Do not show your reasoning process in the final answer.
"""
        
        response = prompt_and_response(ollama_client, model, prompt, quiet=quiet, options=options)
        
        if response:
            try:
                # Extract numeric rating
                conn_strength = int(''.join(filter(str.isdigit, response)) or '0')
                conn_strength = max(1, min(10, conn_strength))  # Clamp to 1-10
            except ValueError:
                conn_strength = 0
            
            part3_responses.append({
                'src_node': edge_data['src_node'],
                'pair_node': edge_data['pair_node'],
                'edge_type': edge_data['edge_type'],
                'explanation': edge_data['explanation'],
                'conn_strength': conn_strength,
                'raw_response': response
            })
    
    avg_strength = sum(r['conn_strength'] for r in part3_responses) / len(part3_responses) if part3_responses else 0
    print(f'{get_timestamp()} -- Stage 3 complete: Average confidence {avg_strength:.1f}/10')
    
    return part3_responses


# ============================================================================
# EDGE VERIFICATION AND INSERTION
# ============================================================================

def get_edge_if_exists(collection, edge_key: str) -> Optional[Dict]:
    """Check if edge already exists in collection."""
    try:
        return collection.get(edge_key)
    except:
        return None


def verify_edges(
    suggested_edges: List[Dict],
    db,
    auto_accept_partial: bool = False
) -> Tuple[List[Dict], List[Dict]]:
    """
    Manually verify suggested edges before insertion.
    
    Args:
        suggested_edges: List of edge suggestions from LLM
        db: ArangoDB database instance
        auto_accept_partial: If True, auto-accept edges that already exist with different attributes
        
    Returns:
        (verified_edges, denied_edges)
    """
    verified_edges = []
    denied_edges = []
    y_responses = ['y', 'yes']
    
    for edge_data in tqdm(suggested_edges, desc='Verifying edges'):
        # Create edge document structure
        src_id = edge_data['src_node']['_id']
        pair_id = edge_data['pair_node']['_id']
        edge_type = edge_data['edge_type']
        edge_key = f"{src_id}_to_{pair_id}".replace('/', ':')
        
        suggested_edge = {
            'type': edge_type,
            '_key': edge_key,
            '_from': src_id,
            '_to': pair_id,
            'explanation': edge_data['explanation'],
            'conn_strength': edge_data['conn_strength'],
            'src_node': edge_data['src_node'],
            'pair_node': edge_data['pair_node'],
            'discovered_by': 'llm_ensemble',
            'discovered_at': datetime.now().isoformat()
        }
        
        print(f'\n{json.dumps(without(suggested_edge, ["src_node", "pair_node"]), indent=2, default=str)}')
        
        # Check if edge already exists
        try:
            edge_coll = db.collection(edge_type)
            existing_edge = get_edge_if_exists(edge_coll, edge_key)
            
            if existing_edge:
                print(f'Edge already exists in collection "{edge_type}"')
                if auto_accept_partial:
                    verified_edges.append(suggested_edge)
                    print('Auto-accepted (partial match)')
                    continue
        except:
            print(f'Collection "{edge_type}" does not exist (will be created on insert)')
        
        # Prompt for verification
        verification = input('Verify this suggested edge? (y/n): ')
        print('\n')
        
        if verification.lower() in y_responses:
            verified_edges.append(suggested_edge)
        else:
            denied_edges.append(suggested_edge)
    
    return verified_edges, denied_edges


def add_verified_edges(verified_edges: List[Dict], db) -> int:
    """
    Insert verified edges into ArangoDB.
    
    Returns count of successfully inserted edges.
    """
    inserted_count = 0
    failed_edges = []
    
    for edge in tqdm(verified_edges, desc='Inserting edges'):
        try:
            edge_type = edge['type']
            edge_key = edge.get('_key', 'unknown')
            
            # Validate edge type is a valid collection name
            # ArangoDB collection names must start with letter/underscore and contain only alphanumeric/_/-
            valid_types = ['LEADS_TO', 'REFERENCES', 'PRODUCES', 'CONTAINS', 'COLLABORATION_WITH']
            if edge_type not in valid_types:
                print(f'{get_timestamp()} -- Invalid edge type "{edge_type}" for edge {edge_key}')
                print(f'{get_timestamp()} -- Attempting to find valid type in edge data...')
                
                # Try to extract a valid type from the explanation or raw response
                found_valid = False
                for valid_type in valid_types:
                    if valid_type in str(edge.get('explanation', '')).upper():
                        edge_type = valid_type
                        edge['type'] = valid_type
                        found_valid = True
                        print(f'{get_timestamp()} -- Using extracted type: {edge_type}')
                        break
                
                if not found_valid:
                    print(f'{get_timestamp()} -- Could not find valid type, skipping edge {edge_key}')
                    failed_edges.append({
                        'edge': edge_key,
                        'reason': f'Invalid edge type: {edge_type}'
                    })
                    continue
            
            # Get or create edge collection
            try:
                if not db.has_collection(edge_type):
                    print(f'{get_timestamp()} -- Creating edge collection: {edge_type}')
                    db.create_collection(edge_type, edge=True)
                
                collection = db.collection(edge_type)
            except Exception as e:
                print(f'{get_timestamp()} -- Error creating/accessing collection "{edge_type}": {e}')
                failed_edges.append({
                    'edge': edge_key,
                    'reason': f'Collection error: {str(e)}'
                })
                continue
            
            # Clean edge document (remove metadata used for verification)
            clean_edge = without(edge, ['src_node', 'pair_node', 'status', 'type'])
            
            # Try update first, then insert
            try:
                collection.update(clean_edge)
                print(f'{get_timestamp()} -- Updated existing edge: {edge_key}')
                inserted_count += 1
            except DocumentUpdateError:
                try:
                    collection.insert(clean_edge)
                    print(f'{get_timestamp()} -- Inserted new edge: {edge_key}')
                    inserted_count += 1
                except Exception as insert_error:
                    print(f'{get_timestamp()} -- Error inserting edge {edge_key}: {insert_error}')
                    failed_edges.append({
                        'edge': edge_key,
                        'reason': f'Insert error: {str(insert_error)}'
                    })
            
        except Exception as e:
            print(f'{get_timestamp()} -- Unexpected error processing edge {edge.get("_key", "unknown")}: {e}')
            failed_edges.append({
                'edge': edge.get('_key', 'unknown'),
                'reason': f'Unexpected error: {str(e)}'
            })
    
    # Print summary
    print(f'\n{get_timestamp()} -- Insertion complete:')
    print(f'{get_timestamp()} -- Successfully inserted: {inserted_count}/{len(verified_edges)} edges')
    if failed_edges:
        print(f'{get_timestamp()} -- Failed: {len(failed_edges)} edges')
        for failed in failed_edges[:5]:  # Show first 5 failures
            print(f'{get_timestamp()} --   {failed["edge"]}: {failed["reason"]}')
        if len(failed_edges) > 5:
            print(f'{get_timestamp()} --   ... and {len(failed_edges) - 5} more')
    
    return inserted_count


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        prog='llm_edge_discovery.py',
        description='Discover semantic relationships in graph data using LLM ensemble'
    )
    
    # Database arguments
    parser.add_argument('--arango-host', default='http://localhost:8529',
                       help='ArangoDB host URL')
    parser.add_argument('--db-name', default='AUTO_DB',
                       help='ArangoDB database name')
    parser.add_argument('--graph-name', default='protograph_kg',
                       help='ArangoDB graph name')
    parser.add_argument('--username', default='root',
                       help='ArangoDB username')
    parser.add_argument('--password', default=None,
                       help='ArangoDB password (will prompt if not provided)')
    
    # Ollama arguments
    parser.add_argument('--ollama-host', default='http://localhost:11434',
                       help='Ollama API host URL')
    parser.add_argument('--model1', default='gemma3:27b-it-qat',
                       help='Model for Stage 1 (binary) and Stage 3 (confidence)')
    parser.add_argument('--model2', default='llama3.3:70b',
                       help='Model for Stage 2 (classification)')
    parser.add_argument('--temperature1', type=float, default=0.8,
                       help='Temperature for model1')
    parser.add_argument('--temperature2', type=float, default=0.8,
                       help='Temperature for model2')
    
    # Processing arguments
    parser.add_argument('--conn-threshold', type=int, default=7,
                       help='Minimum confidence score (1-10) to suggest edge')
    parser.add_argument('--collections', nargs='+',
                       default=['Process', 'PlanningStep', 'DevelopmentStep', 
                               'ExecutionStep', 'SprintLogArtifact', 
                               'ExecutionPlanArtifact', 'TTPArtifact'],
                       help='Node collections to analyze')
    parser.add_argument('--auto-accept', action='store_true',
                       help='Auto-accept edges without manual verification')
    parser.add_argument('--quiet', action='store_true',
                       help='Suppress detailed output')
    
    # Output arguments
    parser.add_argument('--output-file', 
                       help='Save suggestions to JSON file')
    
    args = parser.parse_args()
    
    print("="*80)
    print("LLM EDGE DISCOVERY PIPELINE")
    print("="*80)
    print(f"Database: {args.db_name}")
    print(f"Graph: {args.graph_name}")
    print(f"Models: {args.model1} + {args.model2}")
    print(f"Confidence threshold: {args.conn_threshold}/10")
    print(f"Collections: {', '.join(args.collections)}")
    print("="*80)
    print()
    
    # Connect to ArangoDB
    print(f'{get_timestamp()} -- Connecting to ArangoDB...')
    client = connect_to_arango_client(args.arango_host)
    if not client:
        print("Failed to connect to ArangoDB client. Exiting.")
        return 1
    
    db = connect_to_arango_db(client, args.db_name, args.username, args.password)
    if not db:
        print("Failed to connect to ArangoDB database. Exiting.")
        return 1
    
    aql = db.aql
    
    # Connect to Ollama
    print(f'{get_timestamp()} -- Connecting to Ollama at {args.ollama_host}...')
    ollama_client = OllamaClient(host=args.ollama_host)
    
    # Get node pairs for analysis
    print(f'{get_timestamp()} -- Generating node pairs from collections...')
    edge_pairs = get_all_node_pairs(db, aql, args.collections)
    
    if not edge_pairs:
        print("No node pairs found. Check your collections. Exiting.")
        return 1
    
    # Run 3-stage LLM inference
    print(f'\n{get_timestamp()} -- Starting 3-stage LLM ensemble...\n')
    
    # Stage 1: Binary classification
    part1_responses = part1_prompt(
        edge_pairs,
        ollama_client,
        model=args.model1,
        quiet=args.quiet,
        options={'temperature': args.temperature1}
    )
    
    # Stage 2: Edge type classification
    part2_responses = part2_prompt(
        part1_responses,
        ollama_client,
        model=args.model2,
        quiet=args.quiet,
        options={'temperature': args.temperature2}
    )
    
    # Stage 3: Confidence rating
    part3_responses = part3_prompt(
        part2_responses,
        ollama_client,
        model=args.model1,
        quiet=args.quiet,
        options={'temperature': args.temperature1}
    )
    
    # Filter by confidence threshold
    suggested_edges = [
        edge for edge in part3_responses
        if edge['explanation'] != 'NO CONNECTION' 
        and edge['conn_strength'] >= args.conn_threshold
    ]
    
    print(f'\n{get_timestamp()} -- Filtered to {len(suggested_edges)} suggestions above threshold')
    
    if not suggested_edges:
        print("No edges met the confidence threshold. Try lowering --conn-threshold.")
        return 0
    
    # Save suggestions if requested
    if args.output_file:
        with open(args.output_file, 'w') as f:
            json.dump(suggested_edges, f, indent=2, default=str)
        print(f'{get_timestamp()} -- Saved suggestions to {args.output_file}')
    
    # Verify edges
    if args.auto_accept:
        # Skip verification - send all to UI for review
        print(f'\n{get_timestamp()} -- Auto-accept mode: Skipping terminal verification')
        print(f'{get_timestamp()} -- All {len(suggested_edges)} suggestions saved to {args.output_file}')
        print(f'{get_timestamp()} -- Open your UI to review and approve connections')
        verified = []  # Don't insert edges yet
        denied = []
    else:
        # Manual terminal verification
        print(f'\n{get_timestamp()} -- Verifying edges...\n')
        verified, denied = verify_edges(
            suggested_edges,
            db,
            auto_accept_partial=False
        )
    
    print(f'\n{get_timestamp()} -- Verification complete:')
    print(f'  ✓ Verified: {len(verified)}')
    print(f'  ✗ Denied: {len(denied)}')
    
    # Insert verified edges (only if manual verification was done)
    if verified:
        print(f'\n{get_timestamp()} -- Inserting verified edges...')
        inserted_count = add_verified_edges(verified, db)
        print(f'\n{get_timestamp()} -- Successfully inserted {inserted_count}/{len(verified)} edges')
        
        # Save edge keys for reference
        edge_keys = [edge['_key'] for edge in verified]
        with open('new_edge_keys.txt', 'a') as f:
            f.write('\n'.join(edge_keys) + '\n')
        print(f'{get_timestamp()} -- Saved edge keys to new_edge_keys.txt')
    elif args.auto_accept:
        print(f'\n{get_timestamp()} -- Edges will be created when approved in UI')
        print(f'{get_timestamp()} -- Visit your React app and click "Review" button')
    
    print("\n" + "="*80)
    print("PIPELINE COMPLETE")
    print("="*80)
    
    return 0


if __name__ == "__main__":
    exit(main())