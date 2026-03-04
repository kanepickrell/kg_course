"""
Power BI Push Module - Enhanced Version
Handles authentication with Azure AD and pushing data to Power BI datasets
"""

import os
import requests
import json
from dotenv import load_dotenv
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Azure AD Configuration
TENANT_ID = os.getenv("TENANT_ID")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
WORKSPACE_ID = os.getenv("POWERBI_WORKSPACE_ID")
DATASET_ID = os.getenv("POWERBI_DATASET_ID")

# Power BI API Configuration
AUTHORITY_URL = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
POWERBI_SCOPE = "https://analysis.windows.net/powerbi/api/.default"
POWERBI_API_BASE = "https://api.powerbi.com/v1.0/myorg"

# Cache for access token (simple in-memory cache)
_token_cache = {
    "token": None,
    "expires_at": None
}


def validate_config() -> bool:
    """
    Validate that all required configuration is present
    
    Returns:
        bool: True if config is valid, False otherwise
    """
    required_vars = {
        "TENANT_ID": TENANT_ID,
        "CLIENT_ID": CLIENT_ID,
        "CLIENT_SECRET": CLIENT_SECRET,
        "POWERBI_WORKSPACE_ID": WORKSPACE_ID,
        "POWERBI_DATASET_ID": DATASET_ID
    }
    
    missing = [k for k, v in required_vars.items() if not v or v in ["your_password", "<your_secret_value>"]]
    
    if missing:
        logger.error(f"Missing or invalid configuration: {', '.join(missing)}")
        logger.error("Please update your .env file with real values")
        return False
    
    return True


def get_access_token(force_refresh: bool = False) -> Optional[str]:
    """
    Get OAuth2 access token from Azure AD using client credentials flow
    Implements simple caching to avoid unnecessary token requests
    
    Args:
        force_refresh: Force getting a new token even if cached one exists
    
    Returns:
        str: Bearer token for Power BI API, or None if failed
        
    Raises:
        Exception: If token acquisition fails
    """
    # Check cache first (unless force refresh)
    if not force_refresh and _token_cache["token"]:
        if _token_cache["expires_at"] and datetime.now() < _token_cache["expires_at"]:
            logger.info("Using cached access token")
            return _token_cache["token"]
    
    # Validate configuration
    if not validate_config():
        raise ValueError("Invalid or missing configuration. Check your .env file")
    
    logger.info("🔐 Requesting new access token from Azure AD...")
    logger.debug(f"   Tenant ID: {TENANT_ID}")
    logger.debug(f"   Client ID: {CLIENT_ID}")
    logger.debug(f"   Authority: {AUTHORITY_URL}")
    
    payload = {
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "scope": POWERBI_SCOPE,
    }
    
    try:
        response = requests.post(AUTHORITY_URL, data=payload, timeout=30)
        
        # Log the request for debugging
        logger.debug(f"Token request status: {response.status_code}")
        
        if response.status_code == 200:
            token_data = response.json()
            access_token = token_data.get("access_token")
            expires_in = token_data.get("expires_in", 3600)
            
            if not access_token:
                raise ValueError("No access_token in response from Azure AD")
            
            # Cache the token (with 5 minute buffer before expiration)
            from datetime import timedelta
            _token_cache["token"] = access_token
            _token_cache["expires_at"] = datetime.now() + timedelta(seconds=expires_in - 300)
            
            logger.info(f"✅ Successfully obtained access token (expires in {expires_in}s)")
            return access_token
        else:
            error_msg = f"Failed to get token: {response.status_code}"
            error_detail = response.text
            logger.error(error_msg)
            logger.error(f"Response: {error_detail}")
            
            # Provide helpful error messages
            if response.status_code == 400:
                logger.error("Common causes:")
                logger.error("  - Invalid CLIENT_ID or CLIENT_SECRET")
                logger.error("  - App not properly registered in Azure AD")
                logger.error("  - Check that TENANT_ID is correct")
            elif response.status_code == 401:
                logger.error("Authentication failed - verify your CLIENT_SECRET")
            
            raise Exception(f"{error_msg}: {error_detail}")
            
    except requests.exceptions.Timeout:
        logger.error("Request timed out - check network connectivity")
        raise
    except requests.exceptions.ProxyError as e:
        logger.error(f"Proxy error: {e}")
        logger.error("You may be behind a firewall blocking Azure AD")
        logger.error("Solutions:")
        logger.error("  1. Whitelist: login.microsoftonline.com")
        logger.error("  2. Use VPN with external access")
        logger.error("  3. Run from a machine with internet access")
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise


def push_to_powerbi(rows: List[Dict[str, Any]], table_name: str = "Table1") -> bool:
    """
    Push rows of data to Power BI dataset
    
    Args:
        rows: List of dictionaries containing row data
        table_name: Name of the table in the dataset (default: "Table1")
    
    Returns:
        bool: True if successful, False otherwise
    """
    if not rows:
        logger.warning("No rows to push")
        return False
    
    logger.info(f"📤 Pushing {len(rows)} row(s) to Power BI...")
    
    try:
        # Get access token
        token = get_access_token()
        if not token:
            logger.error("Failed to obtain access token")
            return False
        
        # Construct endpoint
        endpoint = (
            f"{POWERBI_API_BASE}/groups/{WORKSPACE_ID}/"
            f"datasets/{DATASET_ID}/tables/{table_name}/rows"
        )
        
        logger.debug(f"Endpoint: {endpoint}")
        logger.debug(f"Row data: {json.dumps(rows, indent=2)}")
        
        # Prepare headers and payload
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        payload = {"rows": rows}
        
        # Make request
        response = requests.post(endpoint, headers=headers, json=payload, timeout=30)
        
        if response.status_code == 200:
            logger.info(f"✅ Successfully pushed {len(rows)} row(s) to Power BI!")
            return True
        else:
            logger.error(f"❌ Push failed: {response.status_code}")
            logger.error(f"Response: {response.text}")
            
            # Provide helpful error messages
            if response.status_code == 400:
                logger.error("Common causes:")
                logger.error("  - Table doesn't exist (check table name)")
                logger.error("  - Column mismatch between data and dataset schema")
                logger.error("  - Dataset might be in DirectQuery mode (must be Push)")
            elif response.status_code == 404:
                logger.error("Dataset or table not found:")
                logger.error(f"  - Verify DATASET_ID: {DATASET_ID}")
                logger.error(f"  - Verify table name: {table_name}")
            elif response.status_code == 401:
                logger.error("Unauthorized - token may be invalid or expired")
                # Try refreshing token
                logger.info("Attempting to refresh token...")
                token = get_access_token(force_refresh=True)
                if token:
                    return push_to_powerbi(rows, table_name)  # Retry with new token
            
            return False
            
    except Exception as e:
        logger.error(f"Exception during push: {str(e)}")
        return False


def delete_rows(table_name: str = "Table1") -> bool:
    """
    Delete all rows from a Power BI table
    Useful for clearing old data before pushing new data
    
    Args:
        table_name: Name of the table to clear
    
    Returns:
        bool: True if successful, False otherwise
    """
    logger.info(f"🗑️  Deleting all rows from {table_name}...")
    
    try:
        token = get_access_token()
        if not token:
            return False
        
        endpoint = (
            f"{POWERBI_API_BASE}/groups/{WORKSPACE_ID}/"
            f"datasets/{DATASET_ID}/tables/{table_name}/rows"
        )
        
        headers = {"Authorization": f"Bearer {token}"}
        
        response = requests.delete(endpoint, headers=headers, timeout=30)
        
        if response.status_code == 200:
            logger.info(f"✅ Successfully deleted rows from {table_name}")
            return True
        else:
            logger.error(f"❌ Delete failed: {response.status_code}")
            logger.error(f"Response: {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"Exception during delete: {str(e)}")
        return False


def trigger_refresh() -> bool:
    """
    Trigger a refresh of the Power BI dataset
    Note: This only works for certain dataset types
    
    Returns:
        bool: True if successful, False otherwise
    """
    logger.info("🔄 Triggering dataset refresh...")
    
    try:
        token = get_access_token()
        if not token:
            return False
        
        endpoint = f"{POWERBI_API_BASE}/groups/{WORKSPACE_ID}/datasets/{DATASET_ID}/refreshes"
        
        headers = {"Authorization": f"Bearer {token}"}
        
        response = requests.post(endpoint, headers=headers, timeout=30)
        
        if response.status_code in [200, 202]:
            logger.info("✅ Refresh triggered successfully")
            return True
        else:
            logger.warning(f"Refresh trigger status: {response.status_code}")
            logger.debug(f"Response: {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"Exception during refresh: {str(e)}")
        return False


def get_dataset_info() -> Optional[Dict]:
    """
    Get information about the configured Power BI dataset
    
    Returns:
        dict: Dataset information, or None if failed
    """
    logger.info("📊 Fetching dataset information...")
    
    try:
        token = get_access_token()
        if not token:
            return None
        
        endpoint = f"{POWERBI_API_BASE}/groups/{WORKSPACE_ID}/datasets/{DATASET_ID}"
        
        headers = {"Authorization": f"Bearer {token}"}
        
        response = requests.get(endpoint, headers=headers, timeout=30)
        
        if response.status_code == 200:
            dataset = response.json()
            logger.info(f"✅ Dataset: {dataset.get('name', 'Unknown')}")
            logger.info(f"   Created: {dataset.get('createdDate', 'Unknown')}")
            logger.info(f"   Mode: {dataset.get('defaultMode', 'Unknown')}")
            return dataset
        else:
            logger.error(f"Failed to get dataset info: {response.status_code}")
            return None
            
    except Exception as e:
        logger.error(f"Exception: {str(e)}")
        return None


def get_dataset_tables() -> Optional[List[Dict]]:
    """
    Get list of tables in the configured Power BI dataset
    
    Returns:
        list: List of table definitions, or None if failed
    """
    logger.info("📋 Fetching dataset tables...")
    
    try:
        token = get_access_token()
        if not token:
            return None
        
        endpoint = f"{POWERBI_API_BASE}/groups/{WORKSPACE_ID}/datasets/{DATASET_ID}/tables"
        
        headers = {"Authorization": f"Bearer {token}"}
        
        response = requests.get(endpoint, headers=headers, timeout=30)
        
        if response.status_code == 200:
            tables = response.json().get("value", [])
            logger.info(f"✅ Found {len(tables)} table(s)")
            
            for table in tables:
                logger.info(f"   Table: {table.get('name')}")
                columns = table.get('columns', [])
                logger.info(f"   Columns: {', '.join([c['name'] for c in columns])}")
            
            return tables
        else:
            logger.error(f"Failed to get tables: {response.status_code}")
            return None
            
    except Exception as e:
        logger.error(f"Exception: {str(e)}")
        return None


# Example usage and testing
if __name__ == "__main__":
    print("\n" + "="*60)
    print("Power BI Push Module - Test")
    print("="*60 + "\n")
    
    # Test 1: Configuration check
    print("1. Checking configuration...")
    if validate_config():
        print("✅ Configuration valid\n")
    else:
        print("❌ Configuration invalid - fix your .env file\n")
        exit(1)
    
    # Test 2: Get access token
    print("2. Testing Azure AD authentication...")
    try:
        token = get_access_token()
        print(f"✅ Token obtained: {token[:20]}...\n")
    except Exception as e:
        print(f"❌ Failed: {e}\n")
        exit(1)
    
    # Test 3: Get dataset info
    print("3. Testing dataset access...")
    dataset = get_dataset_info()
    print()
    
    # Test 4: Get tables
    print("4. Testing table access...")
    tables = get_dataset_tables()
    print()
    
    # Test 5: Push test data
    print("5. Testing data push...")
    test_rows = [{
        "Source Team": "Test",
        "Target Team": "Verification",
        "Coupling Score": 99.99,
        "Connection Count": 1,
        "Last Updated": datetime.now().isoformat()
    }]
    
    success = push_to_powerbi(test_rows)
    
    if success:
        print("\n✅ ALL TESTS PASSED!")
        print("Check your Power BI report for the test row")
    else:
        print("\n❌ Push test failed")
        print("Review the errors above and fix configuration")
    
    print("\n" + "="*60 + "\n")