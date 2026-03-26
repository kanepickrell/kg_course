"""Tool signatures for Coverage Analyst. Auto-generated — for reference only.



agent.py imports the tool class directly. Edit agent.py to change behaviour.

"""

from typing import Any, Dict, List, Optional



def get_library_module_by_id(key: str):
    """Retrieve a single Library Module artifact by its graph key.  ->  Optional[Library Module]"""
    raise NotImplementedError('get_library_module_by_id')


def list_library_modules(search: str | None, limit: int):
    """List Library Module artifacts with optional text search.  ->  List[Library Module]"""
    raise NotImplementedError('list_library_modules')


def get_execution_sequence_by_id(key: str):
    """Retrieve a single Execution Sequence artifact by its graph key.  ->  Optional[Execution Sequence]"""
    raise NotImplementedError('get_execution_sequence_by_id')


def list_execution_sequences(search: str | None, limit: int):
    """List Execution Sequence artifacts with optional text search.  ->  List[Execution Sequence]"""
    raise NotImplementedError('list_execution_sequences')


def get_ttp_by_id(key: str):
    """Retrieve a single TTP artifact by its graph key.  ->  Optional[TTP]"""
    raise NotImplementedError('get_ttp_by_id')


def list_ttps(search: str | None, limit: int):
    """List TTP artifacts with optional text search.  ->  List[TTP]"""
    raise NotImplementedError('list_ttps')

