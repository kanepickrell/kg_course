"""Typed tool set for Crypto Helper. Auto-generated — add domain logic here."""
from typing import Any, Dict, List, Optional

def get_thing_by_id(key: str):
    """
    Retrieve a single Thing artifact by its graph key.
    Return type: Optional[Thing]
    """
    raise NotImplementedError('Implement get_thing_by_id in tools.py')

def list_things(search: str | None, limit: int):
    """
    List Thing artifacts with optional text search.
    Return type: List[Thing]
    """
    raise NotImplementedError('Implement list_things in tools.py')

def exec_hash_string(text: str, algorithm: str):
    """
    Hash a string using the specified algorithm.
    Return type: dict
    """
    import importlib, os, sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    mod = importlib.import_module('crypto_tools')
    cls = getattr(mod, 'CryptoTools', None)
    if cls is None:
        raise RuntimeError(f'Class 'CryptoTools' not found in 'crypto_tools'')
    return cls().hash_string(text=text, algorithm=algorithm)

def exec_base64_encode(text: str):
    """
    Encode a plain-text string to standard base64.
    Return type: dict
    """
    import importlib, os, sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    mod = importlib.import_module('crypto_tools')
    cls = getattr(mod, 'CryptoTools', None)
    if cls is None:
        raise RuntimeError(f'Class 'CryptoTools' not found in 'crypto_tools'')
    return cls().base64_encode(text=text)

def exec_base64_decode(text: str):
    """
    Decode a base64 string back to plain text.
    Return type: dict
    """
    import importlib, os, sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    mod = importlib.import_module('crypto_tools')
    cls = getattr(mod, 'CryptoTools', None)
    if cls is None:
        raise RuntimeError(f'Class 'CryptoTools' not found in 'crypto_tools'')
    return cls().base64_decode(text=text)

def exec_generate_password(length: str):
    """
    Generate a cryptographically secure random password.
    Return type: dict
    """
    import importlib, os, sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    mod = importlib.import_module('crypto_tools')
    cls = getattr(mod, 'CryptoTools', None)
    if cls is None:
        raise RuntimeError(f'Class 'CryptoTools' not found in 'crypto_tools'')
    return cls().generate_password(length=length)

def program_start():
    """
    Start the registered program using the configured execution context.
    Return type: ExecutionStatus
    """
    raise NotImplementedError('Implement program_start in tools.py')

def program_stop():
    """
    Stop the running program cleanly.
    Return type: ExecutionStatus
    """
    raise NotImplementedError('Implement program_stop in tools.py')

def program_status():
    """
    Check if the program is running and return last N lines of stdout.
    Return type: ExecutionStatus
    """
    raise NotImplementedError('Implement program_status in tools.py')

