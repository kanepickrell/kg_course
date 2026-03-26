"""Tool signatures for Linux Helper. Auto-generated — for reference only.



agent.py imports the tool class directly. Edit agent.py to change behaviour.

"""

from typing import Any, Dict, List, Optional



def get_thing_by_id(key: str):
    """Retrieve a single Thing artifact by its graph key.  ->  Optional[Thing]"""
    raise NotImplementedError('get_thing_by_id')


def list_things(search: str | None, limit: int):
    """List Thing artifacts with optional text search.  ->  List[Thing]"""
    raise NotImplementedError('list_things')


def exec_add_numbers(a: str, b: str):
    """Add two numbers together and return the result.  ->  dict"""
    raise NotImplementedError('exec_add_numbers')


def exec_reverse_text(text: str):
    """Reverse a string of text.  ->  dict"""
    raise NotImplementedError('exec_reverse_text')


def exec_list_files(directory: str):
    """List files in a directory.  ->  dict"""
    raise NotImplementedError('exec_list_files')


def program_start():
    """Start the registered program using the configured execution context.  ->  ExecutionStatus"""
    raise NotImplementedError('program_start')


def program_stop():
    """Stop the running program cleanly.  ->  ExecutionStatus"""
    raise NotImplementedError('program_stop')


def program_status():
    """Check if the program is running and return last N lines of stdout.  ->  ExecutionStatus"""
    raise NotImplementedError('program_status')

