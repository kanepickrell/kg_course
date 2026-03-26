"""Tool signatures for Campaign Planner. Auto-generated — for reference only.



agent.py imports the tool class directly. Edit agent.py to change behaviour.

"""

from typing import Any, Dict, List, Optional



def get_library_module_by_id(key: str):
    """Retrieve a single Library Module artifact by its graph key.  ->  Optional[Library Module]"""
    raise NotImplementedError('get_library_module_by_id')


def list_library_modules(search: str | None, limit: int):
    """List Library Module artifacts with optional text search.  ->  List[Library Module]"""
    raise NotImplementedError('list_library_modules')


def get_ttp_by_id(key: str):
    """Retrieve a single TTP artifact by its graph key.  ->  Optional[TTP]"""
    raise NotImplementedError('get_ttp_by_id')


def list_ttps(search: str | None, limit: int):
    """List TTP artifacts with optional text search.  ->  List[TTP]"""
    raise NotImplementedError('list_ttps')


def get_execution_sequence_by_id(key: str):
    """Retrieve a single Execution Sequence artifact by its graph key.  ->  Optional[Execution Sequence]"""
    raise NotImplementedError('get_execution_sequence_by_id')


def list_execution_sequences(search: str | None, limit: int):
    """List Execution Sequence artifacts with optional text search.  ->  List[Execution Sequence]"""
    raise NotImplementedError('list_execution_sequences')


def exec_build_campaign(tactic: str, max_modules: str):
    """Build a campaign by selecting Library Modules that cover a given MITRE tactic.  ->  Dict[str, Any]"""
    raise NotImplementedError('exec_build_campaign')


def exec_get_coverage_gaps(tactic: str):
    """Identify TTPs within a tactic that have no corresponding Library Module.  ->  Dict[str, Any]"""
    raise NotImplementedError('exec_get_coverage_gaps')


def exec_suggest_sequence(objective: str):
    """Suggest an Execution Sequence that matches a given campaign objective.  ->  Dict[str, Any]"""
    raise NotImplementedError('exec_suggest_sequence')


def exec_list_tactics_with_coverage():
    """List all MITRE tactics present in the graph with their module counts.  ->  Dict[str, Any]"""
    raise NotImplementedError('exec_list_tactics_with_coverage')


def exec_get_module_details(module_name: str):
    """Retrieve full details for a specific Library Module by name.  ->  Dict[str, Any]"""
    raise NotImplementedError('exec_get_module_details')


def program_start():
    """Start the registered program using the configured execution context.  ->  ExecutionStatus"""
    raise NotImplementedError('program_start')


def program_stop():
    """Stop the running program cleanly.  ->  ExecutionStatus"""
    raise NotImplementedError('program_stop')


def program_status():
    """Check if the program is running and return last N lines of stdout.  ->  ExecutionStatus"""
    raise NotImplementedError('program_status')

