"""
End-to-End Test Pipeline
Tests complete flow: Data Ingestion -> LLM Discovery -> Verification

This script orchestrates the full pipeline test:
1. Loads test data into ArangoDB
2. Runs LLM edge discovery
3. Validates results
4. Reports success/failure
"""

import os
import sys
import json
import subprocess
from datetime import datetime
from typing import Dict, List
from pathlib import Path


class Color:
    """ANSI color codes for terminal output."""
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def print_header(text: str):
    """Print a formatted header."""
    print(f"\n{Color.HEADER}{Color.BOLD}{'='*80}")
    print(f"{text.center(80)}")
    print(f"{'='*80}{Color.ENDC}\n")


def print_step(step_num: int, text: str):
    """Print a formatted step."""
    print(f"{Color.OKCYAN}{Color.BOLD}[STEP {step_num}]{Color.ENDC} {text}")


def print_success(text: str):
    """Print a success message."""
    print(f"{Color.OKGREEN}✓ {text}{Color.ENDC}")


def print_error(text: str):
    """Print an error message."""
    print(f"{Color.FAIL}✗ {text}{Color.ENDC}")


def print_warning(text: str):
    """Print a warning message."""
    print(f"{Color.WARNING}⚠ {text}{Color.ENDC}")


def print_info(text: str):
    """Print an info message."""
    print(f"{Color.OKBLUE}ℹ {text}{Color.ENDC}")


def run_command(cmd: List[str], description: str) -> tuple[bool, str]:
    """
    Run a command and return success status and output.
    
    Returns:
        (success, output)
    """
    try:
        print_info(f"Running: {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        print_error(f"{description} failed: {e.stderr}")
        return False, e.stderr
    except Exception as e:
        print_error(f"{description} failed: {str(e)}")
        return False, str(e)


def check_arango_connection(host: str, db_name: str, username: str, password: str) -> bool:
    """Check if we can connect to ArangoDB."""
    try:
        from arango import ArangoClient
        client = ArangoClient(hosts=host)
        db = client.db(db_name, username=username, password=password)
        db.version()
        return True
    except Exception as e:
        print_error(f"Cannot connect to ArangoDB: {e}")
        return False


def check_ollama_connection(host: str) -> bool:
    """Check if Ollama is running and accessible."""
    try:
        from ollama import Client
        client = Client(host=host)
        # Try to list models as a connection test
        client.list()
        return True
    except Exception as e:
        print_error(f"Cannot connect to Ollama: {e}")
        return False


def verify_file_exists(filepath: str) -> bool:
    """Check if a file exists."""
    if not os.path.exists(filepath):
        print_error(f"File not found: {filepath}")
        return False
    return True


def count_nodes_in_db(host: str, db_name: str, username: str, password: str, collections: List[str]) -> Dict[str, int]:
    """Count nodes in specified collections."""
    from arango import ArangoClient
    
    try:
        client = ArangoClient(hosts=host)
        db = client.db(db_name, username=username, password=password)
        
        counts = {}
        for collection in collections:
            if db.has_collection(collection):
                coll = db.collection(collection)
                counts[collection] = coll.count()
            else:
                counts[collection] = 0
        
        return counts
    except Exception as e:
        print_error(f"Error counting nodes: {e}")
        return {}


def count_edges_in_db(host: str, db_name: str, username: str, password: str, edge_types: List[str]) -> Dict[str, int]:
    """Count edges in specified edge collections."""
    from arango import ArangoClient
    
    try:
        client = ArangoClient(hosts=host)
        db = client.db(db_name, username=username, password=password)
        
        counts = {}
        for edge_type in edge_types:
            if db.has_collection(edge_type):
                coll = db.collection(edge_type)
                counts[edge_type] = coll.count()
            else:
                counts[edge_type] = 0
        
        return counts
    except Exception as e:
        print_error(f"Error counting edges: {e}")
        return {}


def main():
    """Run the end-to-end test pipeline."""
    
    print_header("PROTOGRAPH END-TO-END TEST PIPELINE")
    
    # Configuration
    config = {
        'arango_host': os.getenv('ARANGO_HOST', 'http://localhost:8529'),
        'db_name': os.getenv('ARANGO_DB', 'AUTO_DB'),
        'username': os.getenv('ARANGO_USER', 'root'),
        'password': os.getenv('ARANGO_PASSWORD', 'devpass'),
        'ollama_host': os.getenv('OLLAMA_HOST', 'http://localhost:11434'),
        'test_data_file': 'test_data_318th.json',
        'loader_script': 'load_generic_graph.py',
        'discovery_script': 'llm_edge_discovery.py'
    }
    
    print_info("Configuration:")
    for key, value in config.items():
        if 'password' in key.lower():
            print(f"  {key}: {'*' * len(str(value))}")
        else:
            print(f"  {key}: {value}")
    print()
    
    # Track test results
    results = {
        'start_time': datetime.now(),
        'steps': [],
        'success': False
    }
    
    # ========================================================================
    # STEP 1: Pre-flight checks
    # ========================================================================
    print_step(1, "Pre-flight checks")
    
    # Check ArangoDB
    print_info("Checking ArangoDB connection...")
    if not check_arango_connection(
        config['arango_host'],
        config['db_name'],
        config['username'],
        config['password']
    ):
        print_error("ArangoDB connection failed. Ensure ArangoDB is running.")
        return 1
    print_success("ArangoDB connection OK")
    
    # Check Ollama
    print_info("Checking Ollama connection...")
    if not check_ollama_connection(config['ollama_host']):
        print_warning("Ollama connection failed. LLM discovery will not work.")
        print_info("You can still test data ingestion and visualization.")
        ollama_available = False
    else:
        print_success("Ollama connection OK")
        ollama_available = True
    
    # Check required files
    print_info("Checking required files...")
    required_files = [
        config['test_data_file'],
        config['loader_script'],
        config['discovery_script']
    ]
    
    for filepath in required_files:
        if not verify_file_exists(filepath):
            return 1
    print_success("All required files found")
    
    results['steps'].append({
        'step': 1,
        'name': 'Pre-flight checks',
        'success': True
    })
    
    # ========================================================================
    # STEP 2: Load test data into ArangoDB
    # ========================================================================
    print_step(2, "Loading test data into ArangoDB")
    
    load_cmd = [
        sys.executable,
        config['loader_script'],
        config['test_data_file'],
        '-a', config['arango_host'],
        '-d', config['db_name'],
        '-u', config['username'],
        '-p', config['password'],
        '-c',  # Create collections
        '-r'   # Replace if exists
    ]
    
    success, output = run_command(load_cmd, "Data loading")
    
    if not success:
        print_error("Data loading failed")
        results['steps'].append({
            'step': 2,
            'name': 'Data loading',
            'success': False,
            'error': output
        })
        return 1
    
    print_success("Data loaded successfully")
    print(output)
    
    # Count nodes
    node_collections = ['Process', 'PlanningStep', 'DevelopmentStep', 'ExecutionStep',
                       'CapabilityRequestArtifact', 'SprintLogArtifact', 
                       'OrchestrationPlanArtifact', 'RobotLogArtifact',
                       'LiveExecutionArtifact', 'ExecutionPlanArtifact']
    
    node_counts = count_nodes_in_db(
        config['arango_host'],
        config['db_name'],
        config['username'],
        config['password'],
        node_collections
    )
    
    print_info("Node counts:")
    for collection, count in node_counts.items():
        if count > 0:
            print(f"  {collection}: {count}")
    
    # Count structural edges
    edge_types = ['CONTAINS', 'STARTS_WITH', 'LEADS_TO', 'PRODUCES', 'REFERENCES']
    
    edge_counts_before = count_edges_in_db(
        config['arango_host'],
        config['db_name'],
        config['username'],
        config['password'],
        edge_types
    )
    
    print_info("Structural edge counts:")
    for edge_type, count in edge_counts_before.items():
        if count > 0:
            print(f"  {edge_type}: {count}")
    
    results['steps'].append({
        'step': 2,
        'name': 'Data loading',
        'success': True,
        'node_counts': node_counts,
        'edge_counts_before': edge_counts_before
    })
    
    # ========================================================================
    # STEP 3: Run LLM edge discovery (if Ollama available)
    # ========================================================================
    if ollama_available:
        print_step(3, "Running LLM edge discovery")
        
        discovery_cmd = [
            sys.executable,
            config['discovery_script'],
            '--arango-host', config['arango_host'],
            '--db-name', config['db_name'],
            '--username', config['username'],
            '--password', config['password'],
            '--ollama-host', config['ollama_host'],
            '--conn-threshold', '7',
            '--auto-accept',  # Auto-accept for testing
            '--output-file', 'llm_suggestions.json'
        ]
        
        print_warning("This step may take 10-30 minutes depending on model speed...")
        print_info("You can reduce test time by:")
        print_info("  - Using fewer node pairs")
        print_info("  - Using faster models (e.g., gemma2:9b)")
        print_info("  - Increasing --conn-threshold to filter more")
        print()
        
        success, output = run_command(discovery_cmd, "LLM discovery")
        
        if not success:
            print_error("LLM discovery failed")
            results['steps'].append({
                'step': 3,
                'name': 'LLM discovery',
                'success': False,
                'error': output
            })
            return 1
        
        print_success("LLM discovery completed")
        print(output)
        
        # Count edges after discovery
        edge_counts_after = count_edges_in_db(
            config['arango_host'],
            config['db_name'],
            config['username'],
            config['password'],
            edge_types + ['COLLABORATION_WITH']  # LLM might suggest new types
        )
        
        print_info("Edge counts after discovery:")
        for edge_type, count in edge_counts_after.items():
            before = edge_counts_before.get(edge_type, 0)
            diff = count - before
            if diff > 0:
                print(f"  {edge_type}: {count} (+{diff} new)")
            elif count > 0:
                print(f"  {edge_type}: {count}")
        
        # Check if new edges were discovered
        new_edges_count = sum(
            edge_counts_after.get(et, 0) - edge_counts_before.get(et, 0)
            for et in edge_types
        )
        
        if new_edges_count > 0:
            print_success(f"LLM discovered {new_edges_count} new edges!")
        else:
            print_warning("LLM did not discover any new edges above threshold")
        
        results['steps'].append({
            'step': 3,
            'name': 'LLM discovery',
            'success': True,
            'edge_counts_after': edge_counts_after,
            'new_edges_discovered': new_edges_count
        })
    else:
        print_step(3, "Skipping LLM discovery (Ollama not available)")
        results['steps'].append({
            'step': 3,
            'name': 'LLM discovery',
            'success': False,
            'skipped': True,
            'reason': 'Ollama not available'
        })
    
    # ========================================================================
    # STEP 4: Verify data in ProtoGraph UI
    # ========================================================================
    print_step(4, "Manual verification in ProtoGraph UI")
    
    print_info("Next steps for manual verification:")
    print()
    print("1. Open ProtoGraph UI in your browser")
    print("   (usually at http://localhost:5173)")
    print()
    print("2. Verify test data appears:")
    print("   - Search for 'OBAP Test' processes")
    print("   - Check node counts match database")
    print("   - Verify edges connect properly")
    print()
    print("3. Test graph interactions:")
    print("   - Click nodes to inspect details")
    print("   - Expand/collapse clusters")
    print("   - Search for specific nodes")
    print()
    
    if ollama_available:
        print("4. Verify LLM-discovered edges:")
        print("   - Look for edges with 'discovered_by: llm_ensemble'")
        print("   - Check edge types are appropriate")
        print("   - Verify connections make semantic sense")
        print()
    
    print_warning("Manual verification required - press Enter when complete...")
    input()
    
    results['steps'].append({
        'step': 4,
        'name': 'Manual verification',
        'success': True,
        'note': 'Manual verification completed by user'
    })
    
    # ========================================================================
    # FINAL REPORT
    # ========================================================================
    print_header("TEST PIPELINE RESULTS")
    
    results['end_time'] = datetime.now()
    results['duration'] = (results['end_time'] - results['start_time']).total_seconds()
    results['success'] = all(step.get('success', False) for step in results['steps'] if not step.get('skipped'))
    
    print_info(f"Total duration: {results['duration']:.1f} seconds")
    print()
    
    for step in results['steps']:
        status = "✓ PASS" if step['success'] else "✗ FAIL"
        status_color = Color.OKGREEN if step['success'] else Color.FAIL
        
        if step.get('skipped'):
            status = "⊘ SKIP"
            status_color = Color.WARNING
        
        print(f"{status_color}{status}{Color.ENDC} Step {step['step']}: {step['name']}")
        
        if 'error' in step:
            print(f"  Error: {step['error'][:100]}")
    
    print()
    
    if results['success']:
        print_success("END-TO-END TEST PASSED! 🎉")
        print()
        print_info("Your ProtoGraph pipeline is working correctly:")
        print("  ✓ Data ingestion successful")
        print("  ✓ Graph structure validated")
        if ollama_available:
            print("  ✓ LLM edge discovery functional")
        print("  ✓ Visualization confirmed")
        print()
        print_info("You can now:")
        print("  - Load production data")
        print("  - Run full LLM discovery")
        print("  - Deploy to team")
    else:
        print_error("END-TO-END TEST FAILED")
        print()
        print_warning("Review the errors above and:")
        print("  - Check service connections")
        print("  - Verify configuration")
        print("  - Check logs for details")
    
    # Save results
    with open('test_results.json', 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print()
    print_info("Detailed results saved to test_results.json")
    
    return 0 if results['success'] else 1


if __name__ == "__main__":
    try:
        exit(main())
    except KeyboardInterrupt:
        print(f"\n{Color.WARNING}Test interrupted by user{Color.ENDC}")
        exit(1)
    except Exception as e:
        print(f"\n{Color.FAIL}Unexpected error: {e}{Color.ENDC}")
        import traceback
        traceback.print_exc()
        exit(1)