from datetime import datetime

def calculate_team_coupling():
    """
    Mock data generator for Power BI integration.
    Replace this later with your real ArangoDB logic.
    """
    rows = [
        {
            "Source Team": "Automation",
            "Target Team": "OPFOR",
            "Coupling Score": 85.7,
            "Connection Count": 4,
            "Last Updated": datetime.now().isoformat()
        },
        {
            "Source Team": "Range",
            "Target Team": "Content Dev",
            "Coupling Score": 92.4,
            "Connection Count": 3,
            "Last Updated": datetime.now().isoformat()
        },
        {
            "Source Team": "Automation",
            "Target Team": "Range",
            "Coupling Score": 88.9,
            "Connection Count": 5,
            "Last Updated": datetime.now().isoformat()
        }
    ]
    return rows
