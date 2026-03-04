import os
import requests
import json
import logging

logger = logging.getLogger(__name__)
POWERBI_PUSH_URL = os.getenv("POWERBI_PUSH_URL")
TABLE_NAME = os.getenv("POWERBI_TABLE_NAME", "RealTimeData")

def push_to_powerbi_stream(rows):
    """
    Push rows to a Power BI streaming dataset via the direct API key URL.
    """
    if not POWERBI_PUSH_URL:
        logger.error("POWERBI_PUSH_URL not set")
        return False

    payload = {"rows": rows}
    headers = {"Content-Type": "application/json"}

    try:
        r = requests.post(POWERBI_PUSH_URL, headers=headers, json=payload, timeout=15)
        if r.status_code in (200, 202):
            logger.info(f"✅ Successfully pushed {len(rows)} row(s) to Power BI")
            return True
        else:
            logger.error(f"❌ Push failed: {r.status_code} -> {r.text}")
            return False
    except Exception as e:
        logger.error(f"Exception pushing to Power BI: {e}")
        return False
    

