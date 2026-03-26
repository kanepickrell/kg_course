"""Tool signatures for Crypto Helper. Auto-generated — for reference only.



agent.py imports the tool class directly. Edit agent.py to change behaviour.

"""

from typing import Any, Dict, List, Optional



def get_thing_by_id(key: str):
    """Retrieve a single Thing artifact by its graph key.  ->  Optional[Thing]"""
    raise NotImplementedError('get_thing_by_id')


def list_things(search: str | None, limit: int):
    """List Thing artifacts with optional text search.  ->  List[Thing]"""
    raise NotImplementedError('list_things')


def exec_hash_string(text: str, algorithm: str):
    """Hash a string using the specified algorithm.  ->  dict"""
    raise NotImplementedError('exec_hash_string')


def exec_base64_encode(text: str):
    """Encode a plain-text string to standard base64.  ->  dict"""
    raise NotImplementedError('exec_base64_encode')


def exec_base64_decode(text: str):
    """Decode a base64 string back to plain text.  ->  dict"""
    raise NotImplementedError('exec_base64_decode')


def exec_generate_password(length: str):
    """Generate a cryptographically secure random password.  ->  dict"""
    raise NotImplementedError('exec_generate_password')


def program_start():
    """Start the registered program using the configured execution context.  ->  ExecutionStatus"""
    raise NotImplementedError('program_start')


def program_stop():
    """Stop the running program cleanly.  ->  ExecutionStatus"""
    raise NotImplementedError('program_stop')


def program_status():
    """Check if the program is running and return last N lines of stdout.  ->  ExecutionStatus"""
    raise NotImplementedError('program_status')

