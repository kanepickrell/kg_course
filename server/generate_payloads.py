#!/usr/bin/env python3
"""
Generate all 33 LibraryModule payload JSON files for Lumen/Operator.
Based on Schema v3 from hunt_1.resource analysis (Jan 23, 2026).

Run from: ~/repos/kg_course/server/
  python3 generate_payloads.py
"""

import json
import os

OUTPUT_DIR = "./data/payloads"

MODULES = {

    # ── INFRASTRUCTURE ────────────────────────────────────────────────────────

    "cs-start-c2": {
        "_key": "cs-start-c2",
        "name": "Start C2 Server",
        "description": "Connect to Cobalt Strike teamserver and initialize C2 infrastructure",
        "executionType": "cobalt_strike",
        "estimatedDuration": 30,
        "inputs": [],
        "outputs": [
            {"id": "c2_ready", "label": "C2 Ready", "type": "boolean", "description": "C2 server is initialized"}
        ],
        "parameters": [
            {"id": "csIp",   "label": "CS IP",       "type": "string",  "required": True,  "placeholder": "10.50.100.5",      "default": "${CS_IP}"},
            {"id": "csUser", "label": "CS User",      "type": "string",  "required": True,  "placeholder": "operator",         "default": "${CS_USER}"},
            {"id": "csPass", "label": "CS Password",  "type": "string",  "required": True,  "placeholder": "password",         "default": "${CS_PASS}"},
            {"id": "csDir",  "label": "CS Directory", "type": "string",  "required": True,  "placeholder": "/opt/cobaltstrike", "default": "${CS_DIR}"},
            {"id": "csPort", "label": "CS Port",      "type": "number",  "required": True,  "placeholder": "50050",            "default": "${CS_PORT}"},
        ],
        "requirements": {"c2Server": False, "listeners": [], "payloads": [], "libraries": ["hunt_1.resource"]},
        "robotFramework": {
            "keyword": "Setup C2",
            "isSuiteSetup": True,
            "resources": ["hunt_1.resource"],
            "keywordArgs": [
                {"globalSetting": "CS_IP",       "argName": "ip",           "position": 1},
                {"globalSetting": "CS_USER",      "argName": "user",         "position": 2},
                {"globalSetting": "CS_PASS",      "argName": "password",     "position": 3},
                {"globalSetting": "CS_DIR",       "argName": "cs_dir",       "position": 4},
                {"globalSetting": "CS_PORT",      "argName": "port",         "position": 5},
                {"globalSetting": "ARTIFACT_DIR", "argName": "data_dir",     "position": 6},
                {"globalSetting": "DEBUG_MODE",   "argName": "debug",        "position": 7},
                {"globalSetting": "SUDO_NEEDED",  "argName": "sudo_required","position": 8},
            ],
            "pythonCall": "Start C2",
            "documentation": "Start C2 team server",
            "tags": ["infrastructure", "c2"],
        }
    },

    "cs-stop-c2": {
        "_key": "cs-stop-c2",
        "name": "Stop C2 Server",
        "description": "Disconnect from teamserver and remove listeners - teardown C2 infrastructure",
        "executionType": "cobalt_strike",
        "estimatedDuration": 15,
        "inputs": [
            {"id": "c2_ready", "label": "C2 Ready", "type": "boolean", "required": False}
        ],
        "outputs": [],
        "parameters": [
            {"id": "listenerName", "label": "Listener to Remove", "type": "string", "required": False, "default": "${HTTP_LISTENER}", "placeholder": "HTTP"},
        ],
        "requirements": {"c2Server": True, "listeners": [], "payloads": [], "libraries": ["hunt_1.resource"]},
        "robotFramework": {
            "keyword": "Teardown C2",
            "isSuiteTeardown": True,
            "resources": ["hunt_1.resource"],
            "keywordArgs": [],
            "pythonCalls": ["Remove Listener", "Stop C2"],
            "documentation": "Remove listeners and stop C2",
            "tags": ["infrastructure", "teardown"],
        }
    },

    # ── COMMAND & CONTROL ─────────────────────────────────────────────────────

    "cs-create-listener": {
        "_key": "cs-create-listener",
        "name": "Create Listener",
        "description": "Create an HTTP, HTTPS, or SMB listener on the Cobalt Strike teamserver for beacon callbacks",
        "executionType": "cobalt_strike",
        "estimatedDuration": 10,
        "inputs": [
            {"id": "c2_ready", "label": "C2 Ready", "type": "boolean", "required": True}
        ],
        "outputs": [
            {"id": "listener_active", "label": "Listener Active", "type": "boolean", "description": "Listener is ready to receive beacons"}
        ],
        "parameters": [
            {"id": "listenerName", "label": "Listener Name", "type": "string",  "required": True, "placeholder": "HTTP",       "default": "HTTP",         "outputVariable": "HTTP_LISTENER"},
            {"id": "listenerPort", "label": "Port",          "type": "number",  "required": True, "placeholder": "80",         "default": 80,             "outputVariable": "HTTP_LISTENER_PORT"},
            {"id": "listenerType", "label": "Listener Type", "type": "select",  "required": True, "options": ["Beacon_HTTP", "Beacon_HTTPS", "Beacon_SMB"], "default": "Beacon_HTTP", "outputVariable": "HTTP_LISTENER_TYPE"},
        ],
        "requirements": {"c2Server": True, "listeners": [], "payloads": [], "libraries": ["hunt_1.resource"]},
        "robotFramework": {
            "keyword": "Create Listener",
            "resources": ["hunt_1.resource"],
            "keywordArgs": [
                {"param": "listenerName", "position": 1, "variableRef": True,  "variableName": "HTTP_LISTENER"},
                {"param": "listenerPort", "position": 2, "variableRef": True,  "variableName": "HTTP_LISTENER_PORT"},
                {"param": "listenerType", "position": 3, "variableRef": True,  "variableName": "HTTP_LISTENER_TYPE"},
                {"globalSetting": "CS_IP", "position": 4, "variableRef": True},
            ],
            "variables": [
                {"name": "HTTP_LISTENER",      "fromParam": "listenerName", "scope": "suite"},
                {"name": "HTTP_LISTENER_PORT", "fromParam": "listenerPort", "scope": "suite"},
                {"name": "HTTP_LISTENER_TYPE", "fromParam": "listenerType", "scope": "suite"},
            ],
            "pythonCall": "Create Listener",
            "preKeywordLog": "=== Creating Listener: ${HTTP_LISTENER} ===",
            "documentation": "Create Scenario Listeners",
            "tags": ["c2", "listener"],
        }
    },

    "cs-get-session-by-ip": {
        "_key": "cs-get-session-by-ip",
        "name": "Get Session By IP",
        "description": "Retrieve active beacon sessions for a target IP from the teamserver",
        "executionType": "cobalt_strike",
        "estimatedDuration": 5,
        "inputs": [
            {"id": "c2_ready", "label": "C2 Ready", "type": "boolean", "required": True}
        ],
        "outputs": [
            {"id": "session", "label": "Beacon Session", "type": "session", "description": "Active beacon session object"}
        ],
        "parameters": [
            {"id": "targetIp", "label": "Target IP", "type": "string", "required": True, "placeholder": "${TARGET1}", "default": "${TARGET1}"},
        ],
        "requirements": {"c2Server": True, "listeners": [], "payloads": [], "libraries": ["hunt_1.resource"]},
        "robotFramework": {
            "keyword": "Get Sessions By Ip",
            "resources": ["hunt_1.resource"],
            "keywordArgs": [
                {"param": "targetIp", "position": 1, "variableRef": False},
            ],
            "captureOutput": "CURRENT_SESSION",
            "variables": [
                {"name": "CURRENT_SESSION", "fromParam": "targetIp", "scope": "local"},
            ],
            "pythonCall": "Get Sessions By Ip",
            "documentation": "Retrieve beacon sessions by target IP",
            "tags": ["c2", "session"],
        }
    },

    "cs-session-sleep": {
        "_key": "cs-session-sleep",
        "name": "Session Sleep",
        "description": "Set beacon sleep timer and jitter percentage to control callback frequency and evade detection",
        "executionType": "cobalt_strike",
        "estimatedDuration": 5,
        "inputs": [
            {"id": "session", "label": "Beacon Session", "type": "session", "required": True}
        ],
        "outputs": [
            {"id": "session", "label": "Beacon Session", "type": "session", "description": "Session with updated sleep"}
        ],
        "parameters": [
            {"id": "sleepTime", "label": "Sleep Time (seconds)", "type": "number", "required": True,  "placeholder": "60",  "default": 60},
            {"id": "jitter",    "label": "Jitter %",             "type": "number", "required": False, "placeholder": "20",  "default": 20},
        ],
        "requirements": {"c2Server": True, "listeners": [], "payloads": [], "libraries": ["hunt_1.resource"]},
        "robotFramework": {
            "keyword": "Session Sleep",
            "resources": ["hunt_1.resource"],
            "keywordArgs": [
                {"param": "session",   "position": 1, "sessionVariable": "CURRENT_SESSION"},
                {"param": "sleepTime", "position": 2, "variableRef": False},
                {"param": "jitter",    "position": 3, "variableRef": False},
            ],
            "pythonCall": "Session Sleep",
            "documentation": "Set beacon sleep and jitter",
            "tags": ["c2", "evasion"],
        }
    },

    "cs-kill-session": {
        "_key": "cs-kill-session",
        "name": "Kill Session",
        "description": "Terminate an active beacon session on the teamserver",
        "executionType": "cobalt_strike",
        "estimatedDuration": 5,
        "inputs": [
            {"id": "session", "label": "Beacon Session", "type": "session", "required": True}
        ],
        "outputs": [],
        "parameters": [
            {"id": "session", "label": "Session", "type": "string", "required": True, "placeholder": "${CURRENT_SESSION}", "default": "${CURRENT_SESSION}"},
        ],
        "requirements": {"c2Server": True, "listeners": [], "payloads": [], "libraries": ["hunt_1.resource"]},
        "robotFramework": {
            "keyword": "Kill Session",
            "resources": ["hunt_1.resource"],
            "keywordArgs": [
                {"param": "session", "position": 1, "sessionVariable": "CURRENT_SESSION"},
            ],
            "pythonCall": "Kill Session",
            "documentation": "Terminate beacon session",
            "tags": ["c2", "cleanup"],
        }
    },

    # ── RESOURCE DEVELOPMENT ──────────────────────────────────────────────────

    "cs-generate-payload": {
        "_key": "cs-generate-payload",
        "name": "Generate Payload",
        "description": "Generate a Cobalt Strike beacon payload (EXE, DLL, shellcode) bound to a listener",
        "executionType": "cobalt_strike",
        "estimatedDuration": 15,
        "inputs": [
            {"id": "listener_active", "label": "Listener Active", "type": "boolean", "required": True}
        ],
        "outputs": [
            {"id": "payload_ready", "label": "Payload Ready", "type": "boolean", "description": "Payload generated and staged"}
        ],
        "parameters": [
            {"id": "payloadName",     "label": "Payload Name",     "type": "string", "required": True,  "placeholder": "update",       "default": "update",        "outputVariable": "HTTP_PAYLOAD_NAME"},
            {"id": "payloadTemplate", "label": "Template",         "type": "select", "required": True,  "options": ["windows/beacon_http/reverse_http", "windows/beacon_https/reverse_https"], "default": "windows/beacon_http/reverse_http"},
            {"id": "payloadFormat",   "label": "Format",           "type": "select", "required": True,  "options": ["exe", "dll", "raw"], "default": "exe"},
            {"id": "outputPath",      "label": "Output Path",      "type": "string", "required": False, "placeholder": "${WORKDIR}",   "default": "${WORKDIR}"},
        ],
        "requirements": {"c2Server": True, "listeners": ["HTTP"], "payloads": [], "libraries": ["hunt_1.resource"]},
        "robotFramework": {
            "keyword": "Create Payload",
            "resources": ["hunt_1.resource"],
            "keywordArgs": [
                {"param": "payloadName",     "position": 1, "variableRef": True, "variableName": "HTTP_PAYLOAD_NAME"},
                {"globalSetting": "CS_IP",   "position": 2, "variableRef": True},
                {"param": "listenerName",    "position": 3, "variableRef": True, "variableName": "HTTP_LISTENER"},
            ],
            "variables": [
                {"name": "HTTP_PAYLOAD_NAME", "fromParam": "payloadName", "scope": "suite"},
            ],
            "pythonCall": "Create Payload",
            "preKeywordLog": "=== Generating Payload: ${HTTP_PAYLOAD_NAME} ===",
            "documentation": "Generate beacon payload",
            "tags": ["payload", "c2"],
        }
    },

    # ── INITIAL ACCESS ────────────────────────────────────────────────────────

    "cs-initial-access": {
        "_key": "cs-initial-access",
        "name": "Initial Access via SCP/SSH",
        "description": "Copy beacon payload to target via SCP then execute via SSH to establish initial foothold",
        "executionType": "cobalt_strike",
        "estimatedDuration": 30,
        "inputs": [
            {"id": "payload_ready", "label": "Payload Ready", "type": "boolean", "required": True}
        ],
        "outputs": [
            {"id": "session", "label": "Initial Beacon", "type": "session", "description": "First beacon from target"}
        ],
        "parameters": [
            {"id": "targetIp",    "label": "Target IP",     "type": "string", "required": True, "placeholder": "${TARGET1}", "default": "${TARGET1}"},
            {"id": "targetUser",  "label": "Target User",   "type": "string", "required": True, "placeholder": "${REG_USER.username}", "default": "${REG_USER.username}"},
            {"id": "targetPass",  "label": "Target Pass",   "type": "string", "required": True, "placeholder": "${REG_USER.password}", "default": "${REG_USER.password}"},
            {"id": "payloadName", "label": "Payload Name",  "type": "string", "required": True, "placeholder": "${HTTP_PAYLOAD_NAME}", "default": "${HTTP_PAYLOAD_NAME}"},
        ],
        "requirements": {"c2Server": True, "listeners": ["HTTP"], "payloads": ["update"], "libraries": ["hunt_1.resource"]},
        "robotFramework": {
            "keyword": "Initial Access",
            "resources": ["hunt_1.resource"],
            "compositeKeyword": True,
            "keywordArgs": [
                {"param": "targetIp",   "position": 1, "variableRef": False},
                {"param": "targetUser", "position": 2, "variableRef": False},
                {"param": "targetPass", "position": 3, "variableRef": False},
            ],
            "captureOutput": "LOCAL_INITIAL_BEACON",
            "pythonCall": "Initial Access",
            "documentation": "SCP payload to target and execute via SSH",
            "tags": ["initial-access", "ssh"],
        }
    },

    "cs-upload-file": {
        "_key": "cs-upload-file",
        "name": "Upload File",
        "description": "Upload a file from operator machine to target via Cobalt Strike beacon channel",
        "executionType": "cobalt_strike",
        "estimatedDuration": 15,
        "inputs": [
            {"id": "session", "label": "Beacon Session", "type": "session", "required": True}
        ],
        "outputs": [
            {"id": "session", "label": "Beacon Session", "type": "session", "description": "Session after upload"}
        ],
        "parameters": [
            {"id": "localPath",  "label": "Local File Path",  "type": "string", "required": True, "placeholder": "${WORKDIR}update.exe", "default": "${WORKDIR}update.exe"},
            {"id": "remotePath", "label": "Remote Path",      "type": "string", "required": True, "placeholder": "C:\\Windows\\Temp\\",  "default": "C:\\Windows\\Temp\\"},
        ],
        "requirements": {"c2Server": True, "listeners": [], "payloads": [], "libraries": ["hunt_1.resource"]},
        "robotFramework": {
            "keyword": "Upload File",
            "resources": ["hunt_1.resource"],
            "keywordArgs": [
                {"param": "session",    "position": 1, "sessionVariable": "CURRENT_SESSION"},
                {"param": "localPath",  "position": 2, "variableRef": False},
                {"param": "remotePath", "position": 3, "variableRef": False},
            ],
            "pythonCall": "cobaltstrike.Upload File",
            "documentation": "Upload file via beacon",
            "tags": ["upload", "file"],
        }
    },

    # ── DISCOVERY ─────────────────────────────────────────────────────────────

    "cs-getuid": {
        "_key": "cs-getuid",
        "name": "Get UID",
        "description": "Get the current user identity from an active beacon session",
        "executionType": "cobalt_strike",
        "estimatedDuration": 5,
        "inputs": [
            {"id": "session", "label": "Beacon Session", "type": "session", "required": True}
        ],
        "outputs": [
            {"id": "uid_result", "label": "UID Result", "type": "string", "description": "Current user identity string"}
        ],
        "parameters": [
            {"id": "session", "label": "Session", "type": "string", "required": True, "placeholder": "${CURRENT_SESSION}", "default": "${CURRENT_SESSION}"},
        ],
        "requirements": {"c2Server": True, "listeners": [], "payloads": [], "libraries": ["hunt_1.resource"]},
        "robotFramework": {
            "keyword": "GetUID",
            "resources": ["hunt_1.resource"],
            "keywordArgs": [
                {"param": "session", "position": 1, "sessionVariable": "CURRENT_SESSION"},
            ],
            "captureOutput": "UID_RESULT",
            "pythonCall": "run Getuid",
            "postKeywordLog": "=== UID: ${UID_RESULT} ===",
            "documentation": "Get current user identity",
            "tags": ["discovery", "identity"],
        }
    },

    "cs-get-processes": {
        "_key": "cs-get-processes",
        "name": "Get Processes",
        "description": "List all running processes on target via beacon using tasklist",
        "executionType": "cobalt_strike",
        "estimatedDuration": 10,
        "inputs": [
            {"id": "session", "label": "Beacon Session", "type": "session", "required": True}
        ],
        "outputs": [
            {"id": "process_list", "label": "Process List", "type": "string", "description": "Running processes output"}
        ],
        "parameters": [
            {"id": "session", "label": "Session", "type": "string", "required": True, "placeholder": "${CURRENT_SESSION}", "default": "${CURRENT_SESSION}"},
        ],
        "requirements": {"c2Server": True, "listeners": [], "payloads": [], "libraries": ["hunt_1.resource"]},
        "robotFramework": {
            "keyword": "Get Processes",
            "resources": ["hunt_1.resource"],
            "keywordArgs": [
                {"param": "session", "position": 1, "sessionVariable": "CURRENT_SESSION"},
            ],
            "captureOutput": "PROCESS_LIST",
            "pythonCall": "Issue Shell Cmd",
            "documentation": "List running processes",
            "tags": ["discovery", "processes"],
        }
    },

    "cs-list-directory": {
        "_key": "cs-list-directory",
        "name": "List Directory",
        "description": "List contents of a directory on target via beacon using dir command",
        "executionType": "cobalt_strike",
        "estimatedDuration": 5,
        "inputs": [
            {"id": "session", "label": "Beacon Session", "type": "session", "required": True}
        ],
        "outputs": [
            {"id": "dir_listing", "label": "Directory Listing", "type": "string", "description": "Directory contents"}
        ],
        "parameters": [
            {"id": "session",   "label": "Session",    "type": "string", "required": True, "placeholder": "${CURRENT_SESSION}", "default": "${CURRENT_SESSION}"},
            {"id": "directory", "label": "Directory",  "type": "string", "required": True, "placeholder": "C:\\Users\\",        "default": "C:\\Users\\"},
        ],
        "requirements": {"c2Server": True, "listeners": [], "payloads": [], "libraries": ["hunt_1.resource"]},
        "robotFramework": {
            "keyword": "List Directory",
            "resources": ["hunt_1.resource"],
            "keywordArgs": [
                {"param": "session",   "position": 1, "sessionVariable": "CURRENT_SESSION"},
                {"param": "directory", "position": 2, "variableRef": False},
            ],
            "pythonCall": "Issue Shell Cmd",
            "documentation": "List directory contents",
            "tags": ["discovery", "filesystem"],
        }
    },

    "cs-network-enumerate": {
        "_key": "cs-network-enumerate",
        "name": "Network Enumerate",
        "description": "Run Cobalt Strike port scan (bportscan) against target IP range to discover open services",
        "executionType": "cobalt_strike",
        "estimatedDuration": 60,
        "inputs": [
            {"id": "session", "label": "Beacon Session", "type": "session", "required": True}
        ],
        "outputs": [
            {"id": "scan_results", "label": "Scan Results", "type": "string", "description": "Open ports and services"}
        ],
        "parameters": [
            {"id": "session",   "label": "Session",       "type": "string", "required": True, "placeholder": "${CURRENT_SESSION}", "default": "${CURRENT_SESSION}"},
            {"id": "ipRange",   "label": "IP Range",      "type": "string", "required": True, "placeholder": "10.0.0.0/24",        "default": "10.0.0.0/24"},
            {"id": "ports",     "label": "Ports",         "type": "string", "required": True, "placeholder": "22,80,443,445,3389", "default": "22,80,443,445,3389"},
            {"id": "discovery", "label": "Discovery Mode","type": "select", "required": True, "options": ["arp", "icmp", "none"],   "default": "arp"},
        ],
        "requirements": {"c2Server": True, "listeners": [], "payloads": [], "libraries": ["hunt_1.resource"]},
        "robotFramework": {
            "keyword": "Network Enumerate",
            "resources": ["hunt_1.resource"],
            "keywordArgs": [
                {"param": "session",   "position": 1, "sessionVariable": "CURRENT_SESSION"},
                {"param": "ipRange",   "position": 2, "variableRef": False},
                {"param": "ports",     "position": 3, "variableRef": False},
                {"param": "discovery", "position": 4, "variableRef": False},
            ],
            "pythonCall": "Run Bportscan",
            "documentation": "Port scan target network range",
            "tags": ["discovery", "network"],
        }
    },

    "cs-get-arp": {
        "_key": "cs-get-arp",
        "name": "Get ARP Table",
        "description": "Retrieve ARP table from target to identify adjacent hosts on the network",
        "executionType": "cobalt_strike",
        "estimatedDuration": 5,
        "inputs": [
            {"id": "session", "label": "Beacon Session", "type": "session", "required": True}
        ],
        "outputs": [
            {"id": "arp_data", "label": "ARP Data", "type": "string", "description": "ARP table output"}
        ],
        "parameters": [
            {"id": "session", "label": "Session", "type": "string", "required": True, "placeholder": "${CURRENT_SESSION}", "default": "${CURRENT_SESSION}"},
        ],
        "requirements": {"c2Server": True, "listeners": [], "payloads": [], "libraries": ["hunt_1.resource"]},
        "robotFramework": {
            "keyword": "Get ARP Data",
            "resources": ["hunt_1.resource"],
            "keywordArgs": [
                {"param": "session", "position": 1, "sessionVariable": "CURRENT_SESSION"},
            ],
            "captureOutput": "ARP_DATA",
            "pythonCall": "Issue Shell Cmd",
            "documentation": "Get ARP table for network discovery",
            "tags": ["discovery", "network"],
        }
    },

    "cs-query-registry": {
        "_key": "cs-query-registry",
        "name": "Query Registry",
        "description": "Query a registry path via beacon to verify persistence keys or enumerate configuration",
        "executionType": "cobalt_strike",
        "estimatedDuration": 5,
        "inputs": [
            {"id": "session", "label": "Beacon Session", "type": "session", "required": True}
        ],
        "outputs": [
            {"id": "reg_result", "label": "Registry Result", "type": "string", "description": "Registry query output"}
        ],
        "parameters": [
            {"id": "session",   "label": "Session",        "type": "string", "required": True, "placeholder": "${CURRENT_SESSION}",       "default": "${CURRENT_SESSION}"},
            {"id": "regPath",   "label": "Registry Path",  "type": "string", "required": True, "placeholder": "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run", "default": "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run"},
        ],
        "requirements": {"c2Server": True, "listeners": [], "payloads": [], "libraries": ["hunt_1.resource"]},
        "robotFramework": {
            "keyword": "Query Registry",
            "resources": ["hunt_1.resource"],
            "keywordArgs": [
                {"param": "session", "position": 1, "sessionVariable": "CURRENT_SESSION"},
                {"param": "regPath", "position": 2, "variableRef": False},
            ],
            "pythonCall": "Issue Shell Cmd",
            "documentation": "Query registry key",
            "tags": ["discovery", "registry"],
        }
    },

    "cs-get-pwd": {
        "_key": "cs-get-pwd",
        "name": "Get Working Directory",
        "description": "Get the current working directory path on target via beacon",
        "executionType": "cobalt_strike",
        "estimatedDuration": 5,
        "inputs": [
            {"id": "session", "label": "Beacon Session", "type": "session", "required": True}
        ],
        "outputs": [
            {"id": "cwd", "label": "Working Directory", "type": "string", "description": "Current working directory path"}
        ],
        "parameters": [
            {"id": "session", "label": "Session", "type": "string", "required": True, "placeholder": "${CURRENT_SESSION}", "default": "${CURRENT_SESSION}"},
        ],
        "requirements": {"c2Server": True, "listeners": [], "payloads": [], "libraries": ["hunt_1.resource"]},
        "robotFramework": {
            "keyword": "Get Working Directory",
            "resources": ["hunt_1.resource"],
            "keywordArgs": [
                {"param": "session", "position": 1, "sessionVariable": "CURRENT_SESSION"},
            ],
            "captureOutput": "CWD",
            "pythonCall": "Issue Shell Cmd",
            "documentation": "Get current working directory",
            "tags": ["discovery", "filesystem"],
        }
    },

    # ── CREDENTIAL ACCESS ─────────────────────────────────────────────────────

    "cs-dump-credentials": {
        "_key": "cs-dump-credentials",
        "name": "Dump Credentials",
        "description": "Dump credentials from LSASS memory using Mimikatz via Cobalt Strike beacon",
        "executionType": "cobalt_strike",
        "estimatedDuration": 15,
        "inputs": [
            {"id": "session", "label": "Beacon Session", "type": "session", "required": True}
        ],
        "outputs": [
            {"id": "credentials", "label": "Credentials", "type": "string", "description": "Dumped credential data"}
        ],
        "parameters": [
            {"id": "session", "label": "Session", "type": "string", "required": True, "placeholder": "${CURRENT_SESSION}", "default": "${CURRENT_SESSION}"},
        ],
        "requirements": {"c2Server": True, "listeners": [], "payloads": [], "elevated": True, "libraries": ["hunt_1.resource"]},
        "robotFramework": {
            "keyword": "Dump Credentials",
            "resources": ["hunt_1.resource"],
            "keywordArgs": [
                {"param": "session", "position": 1, "sessionVariable": "CURRENT_SESSION"},
            ],
            "captureOutput": "CREDENTIAL_OUTPUT",
            "pythonCall": "run Mimikatz",
            "preKeywordLog": "=== Dumping Credentials ===",
            "postKeywordLog": "=== Credential Dump Complete ===",
            "documentation": "Dump credentials via Mimikatz",
            "tags": ["credential-access", "mimikatz"],
        }
    },

    # ── PRIVILEGE ESCALATION ──────────────────────────────────────────────────

    "cs-elevate-spawnas": {
        "_key": "cs-elevate-spawnas",
        "name": "Elevate With Spawnas",
        "description": "Spawn a new beacon process running as a specified domain user to elevate privileges",
        "executionType": "cobalt_strike",
        "estimatedDuration": 15,
        "inputs": [
            {"id": "session", "label": "Beacon Session", "type": "session", "required": True}
        ],
        "outputs": [
            {"id": "elevated_session", "label": "Elevated Session", "type": "session", "description": "New beacon running as target user"}
        ],
        "parameters": [
            {"id": "session",  "label": "Session",         "type": "string", "required": True, "placeholder": "${CURRENT_SESSION}",    "default": "${CURRENT_SESSION}"},
            {"id": "domain",   "label": "Domain",          "type": "string", "required": True, "placeholder": "${DOMAIN1}",            "default": "${DOMAIN1}"},
            {"id": "username", "label": "Username",        "type": "string", "required": True, "placeholder": "${ADMIN_USER.username}", "default": "${ADMIN_USER.username}"},
            {"id": "password", "label": "Password",        "type": "string", "required": True, "placeholder": "${ADMIN_USER.password}", "default": "${ADMIN_USER.password}"},
        ],
        "requirements": {"c2Server": True, "listeners": [], "payloads": [], "libraries": ["hunt_1.resource"]},
        "robotFramework": {
            "keyword": "Elevate With Spawnas",
            "resources": ["hunt_1.resource"],
            "keywordArgs": [
                {"param": "session",  "position": 1, "sessionVariable": "CURRENT_SESSION"},
                {"param": "domain",   "position": 2, "variableRef": False},
                {"param": "username", "position": 3, "variableRef": False},
                {"param": "password", "position": 4, "variableRef": False},
            ],
            "pythonCall": "Run Bspawnas",
            "documentation": "Elevate via spawnas with domain credentials",
            "tags": ["privilege-escalation", "spawnas"],
        }
    },

    "cs-inject-process": {
        "_key": "cs-inject-process",
        "name": "Inject Process",
        "description": "Inject beacon shellcode into a running process by PID to migrate or elevate context",
        "executionType": "cobalt_strike",
        "estimatedDuration": 10,
        "inputs": [
            {"id": "session", "label": "Beacon Session", "type": "session", "required": True}
        ],
        "outputs": [
            {"id": "injected_session", "label": "Injected Session", "type": "session", "description": "Session in new process context"}
        ],
        "parameters": [
            {"id": "session",    "label": "Session",     "type": "string", "required": True, "placeholder": "${CURRENT_SESSION}", "default": "${CURRENT_SESSION}"},
            {"id": "pid",        "label": "Target PID",  "type": "number", "required": True, "placeholder": "1234",              "default": 1234},
            {"id": "listener",   "label": "Listener",    "type": "string", "required": True, "placeholder": "${HTTP_LISTENER}",  "default": "${HTTP_LISTENER}"},
        ],
        "requirements": {"c2Server": True, "listeners": [], "payloads": [], "libraries": ["hunt_1.resource"]},
        "robotFramework": {
            "keyword": "Inject Process",
            "resources": ["hunt_1.resource"],
            "keywordArgs": [
                {"param": "session",  "position": 1, "sessionVariable": "CURRENT_SESSION"},
                {"param": "pid",      "position": 2, "variableRef": False},
                {"param": "listener", "position": 3, "variableRef": True, "variableName": "HTTP_LISTENER"},
            ],
            "pythonCall": "run Binject",
            "documentation": "Inject beacon into process by PID",
            "tags": ["privilege-escalation", "injection"],
        }
    },

    # ── LATERAL MOVEMENT ──────────────────────────────────────────────────────

    "cs-lateral-psexec": {
        "_key": "cs-lateral-psexec",
        "name": "Lateral Move PsExec64",
        "description": "Move laterally to a target host using PsExec via Cobalt Strike bjump - spawns SYSTEM beacon",
        "executionType": "cobalt_strike",
        "estimatedDuration": 20,
        "inputs": [
            {"id": "session", "label": "Beacon Session", "type": "session", "required": True}
        ],
        "outputs": [
            {"id": "lateral_session", "label": "Lateral Session", "type": "session", "description": "New beacon on lateral target as SYSTEM"}
        ],
        "parameters": [
            {"id": "session",    "label": "Session",          "type": "string", "required": True, "placeholder": "${CURRENT_SESSION}", "default": "${CURRENT_SESSION}"},
            {"id": "targetIp",   "label": "Target IP",        "type": "string", "required": True, "placeholder": "${TARGET2}",         "default": "${TARGET2}"},
            {"id": "listener",   "label": "Listener",         "type": "string", "required": True, "placeholder": "${HTTP_LISTENER}",   "default": "${HTTP_LISTENER}"},
        ],
        "requirements": {"c2Server": True, "listeners": ["HTTP"], "payloads": [], "libraries": ["hunt_1.resource"]},
        "robotFramework": {
            "keyword": "Lateral Move (PSExec)",
            "resources": ["hunt_1.resource"],
            "keywordArgs": [
                {"param": "session",  "position": 1, "sessionVariable": "CURRENT_SESSION"},
                {"param": "targetIp", "position": 2, "variableRef": False},
                {"param": "listener", "position": 3, "variableRef": True, "variableName": "HTTP_LISTENER"},
            ],
            "pythonCall": "Run Bjump",
            "preKeywordLog": "=== Lateral Move PSExec → ${TARGET2} ===",
            "documentation": "Lateral movement via PsExec64",
            "tags": ["lateral-movement", "psexec"],
        }
    },

    "cs-lateral-winrm": {
        "_key": "cs-lateral-winrm",
        "name": "Lateral Move WinRM",
        "description": "Move laterally to a target host using WinRM via Cobalt Strike bjump",
        "executionType": "cobalt_strike",
        "estimatedDuration": 15,
        "inputs": [
            {"id": "session", "label": "Beacon Session", "type": "session", "required": True}
        ],
        "outputs": [
            {"id": "lateral_session", "label": "Lateral Session", "type": "session", "description": "New beacon on lateral target via WinRM"}
        ],
        "parameters": [
            {"id": "session",  "label": "Session",  "type": "string", "required": True, "placeholder": "${CURRENT_SESSION}", "default": "${CURRENT_SESSION}"},
            {"id": "targetIp", "label": "Target IP", "type": "string", "required": True, "placeholder": "${TARGET2}",         "default": "${TARGET2}"},
            {"id": "listener", "label": "Listener",  "type": "string", "required": True, "placeholder": "${HTTP_LISTENER}",   "default": "${HTTP_LISTENER}"},
        ],
        "requirements": {"c2Server": True, "listeners": ["HTTP"], "payloads": [], "libraries": ["hunt_1.resource"]},
        "robotFramework": {
            "keyword": "Lateral Move (WinRM)",
            "resources": ["hunt_1.resource"],
            "keywordArgs": [
                {"param": "session",  "position": 1, "sessionVariable": "CURRENT_SESSION"},
                {"param": "targetIp", "position": 2, "variableRef": False},
                {"param": "listener", "position": 3, "variableRef": True, "variableName": "HTTP_LISTENER"},
            ],
            "pythonCall": "Run Bjump",
            "documentation": "Lateral movement via WinRM",
            "tags": ["lateral-movement", "winrm"],
        }
    },

    # ── PERSISTENCE ───────────────────────────────────────────────────────────

    "cs-persistence-registry": {
        "_key": "cs-persistence-registry",
        "name": "Persistence via Registry",
        "description": "Establish persistence by adding beacon path to HKCU Run registry key via reg add command",
        "executionType": "cobalt_strike",
        "estimatedDuration": 10,
        "inputs": [
            {"id": "session", "label": "Beacon Session", "type": "session", "required": True}
        ],
        "outputs": [
            {"id": "persistence_set", "label": "Persistence Set", "type": "boolean", "description": "Registry key written"}
        ],
        "parameters": [
            {"id": "session",     "label": "Session",       "type": "string", "required": True,  "placeholder": "${CURRENT_SESSION}",               "default": "${CURRENT_SESSION}"},
            {"id": "regKeyName",  "label": "Key Name",      "type": "string", "required": True,  "placeholder": "WindowsUpdate",                    "default": "WindowsUpdate"},
            {"id": "payloadPath", "label": "Payload Path",  "type": "string", "required": True,  "placeholder": "C:\\Users\\Public\\update.exe",     "default": "C:\\Users\\Public\\update.exe"},
            {"id": "regHive",     "label": "Registry Hive", "type": "select", "required": False, "options": ["HKCU", "HKLM"], "default": "HKCU"},
        ],
        "requirements": {"c2Server": True, "listeners": [], "payloads": [], "libraries": ["hunt_1.resource"]},
        "robotFramework": {
            "keyword": "Persistence (Registry)",
            "resources": ["hunt_1.resource"],
            "keywordArgs": [
                {"param": "session",     "position": 1, "sessionVariable": "CURRENT_SESSION"},
                {"param": "regKeyName",  "position": 2, "variableRef": False},
                {"param": "payloadPath", "position": 3, "variableRef": False},
                {"param": "regHive",     "position": 4, "variableRef": False},
            ],
            "variables": [
                {"name": "PERSISTENCE_KEY", "fromParam": "regKeyName", "scope": "local"},
            ],
            "pythonCall": "Issue Shell Cmd",
            "preKeywordLog": "=== Setting Registry Persistence: ${PERSISTENCE_KEY} ===",
            "postKeywordLog": "=== Registry Persistence Set ===",
            "documentation": "Registry Run key persistence",
            "tags": ["persistence", "registry"],
        }
    },

    "cs-persistence-schtasks": {
        "_key": "cs-persistence-schtasks",
        "name": "Persistence via Schtasks",
        "description": "Establish persistence by creating a scheduled task that runs beacon at system startup",
        "executionType": "cobalt_strike",
        "estimatedDuration": 10,
        "inputs": [
            {"id": "session", "label": "Beacon Session", "type": "session", "required": True}
        ],
        "outputs": [
            {"id": "task_created", "label": "Task Created", "type": "boolean", "description": "Scheduled task created"}
        ],
        "parameters": [
            {"id": "session",     "label": "Session",      "type": "string", "required": True,  "placeholder": "${CURRENT_SESSION}",           "default": "${CURRENT_SESSION}"},
            {"id": "taskName",    "label": "Task Name",    "type": "string", "required": True,  "placeholder": "WindowsDefenderUpdate",        "default": "WindowsDefenderUpdate"},
            {"id": "payloadPath", "label": "Payload Path", "type": "string", "required": True,  "placeholder": "C:\\Users\\Public\\update.exe", "default": "C:\\Users\\Public\\update.exe"},
            {"id": "schedule",    "label": "Schedule",     "type": "select", "required": False, "options": ["ONSTART", "ONLOGON", "DAILY"],    "default": "ONSTART"},
        ],
        "requirements": {"c2Server": True, "listeners": [], "payloads": [], "libraries": ["hunt_1.resource"]},
        "robotFramework": {
            "keyword": "Persistence (Schtasks)",
            "resources": ["hunt_1.resource"],
            "keywordArgs": [
                {"param": "session",     "position": 1, "sessionVariable": "CURRENT_SESSION"},
                {"param": "taskName",    "position": 2, "variableRef": False},
                {"param": "payloadPath", "position": 3, "variableRef": False},
                {"param": "schedule",    "position": 4, "variableRef": False},
            ],
            "pythonCall": "Issue Shell Cmd",
            "documentation": "Scheduled task persistence",
            "tags": ["persistence", "schtasks"],
        }
    },

    # ── DEFENSE EVASION ───────────────────────────────────────────────────────

    "cs-move-beacon": {
        "_key": "cs-move-beacon",
        "name": "Move Beacon",
        "description": "Move beacon executable to a new location on target using move command to evade detection",
        "executionType": "cobalt_strike",
        "estimatedDuration": 5,
        "inputs": [
            {"id": "session", "label": "Beacon Session", "type": "session", "required": True}
        ],
        "outputs": [
            {"id": "session", "label": "Beacon Session", "type": "session", "description": "Session after move"}
        ],
        "parameters": [
            {"id": "session",     "label": "Session",         "type": "string", "required": True, "placeholder": "${CURRENT_SESSION}",           "default": "${CURRENT_SESSION}"},
            {"id": "sourcePath",  "label": "Source Path",     "type": "string", "required": True, "placeholder": "C:\\Windows\\Temp\\update.exe", "default": "C:\\Windows\\Temp\\update.exe"},
            {"id": "destPath",    "label": "Destination Path","type": "string", "required": True, "placeholder": "C:\\Users\\Public\\update.exe", "default": "C:\\Users\\Public\\update.exe"},
        ],
        "requirements": {"c2Server": True, "listeners": [], "payloads": [], "libraries": ["hunt_1.resource"]},
        "robotFramework": {
            "keyword": "Move Beacon",
            "resources": ["hunt_1.resource"],
            "keywordArgs": [
                {"param": "session",    "position": 1, "sessionVariable": "CURRENT_SESSION"},
                {"param": "sourcePath", "position": 2, "variableRef": False},
                {"param": "destPath",   "position": 3, "variableRef": False},
            ],
            "pythonCall": "Issue Shell Cmd",
            "documentation": "Move beacon to evade detection",
            "tags": ["defense-evasion", "move"],
        }
    },

    "cs-delete-file": {
        "_key": "cs-delete-file",
        "name": "Delete File",
        "description": "Delete a file on target via beacon to remove artifacts and cover tracks",
        "executionType": "cobalt_strike",
        "estimatedDuration": 5,
        "inputs": [
            {"id": "session", "label": "Beacon Session", "type": "session", "required": True}
        ],
        "outputs": [
            {"id": "session", "label": "Beacon Session", "type": "session", "description": "Session after delete"}
        ],
        "parameters": [
            {"id": "session",  "label": "Session",    "type": "string", "required": True, "placeholder": "${CURRENT_SESSION}",           "default": "${CURRENT_SESSION}"},
            {"id": "filePath", "label": "File Path",  "type": "string", "required": True, "placeholder": "C:\\Windows\\Temp\\update.exe", "default": "C:\\Windows\\Temp\\update.exe"},
        ],
        "requirements": {"c2Server": True, "listeners": [], "payloads": [], "libraries": ["hunt_1.resource"]},
        "robotFramework": {
            "keyword": "Delete File",
            "resources": ["hunt_1.resource"],
            "keywordArgs": [
                {"param": "session",  "position": 1, "sessionVariable": "CURRENT_SESSION"},
                {"param": "filePath", "position": 2, "variableRef": False},
            ],
            "pythonCall": "Issue Shell Cmd",
            "documentation": "Delete file to cover tracks",
            "tags": ["defense-evasion", "cleanup"],
        }
    },

    "cs-timestomp": {
        "_key": "cs-timestomp",
        "name": "Timestomp File",
        "description": "Modify file timestamps to match a reference file to defeat forensic timeline analysis",
        "executionType": "cobalt_strike",
        "estimatedDuration": 5,
        "inputs": [
            {"id": "session", "label": "Beacon Session", "type": "session", "required": True}
        ],
        "outputs": [
            {"id": "session", "label": "Beacon Session", "type": "session", "description": "Session after timestomp"}
        ],
        "parameters": [
            {"id": "session",      "label": "Session",         "type": "string", "required": True, "placeholder": "${CURRENT_SESSION}",            "default": "${CURRENT_SESSION}"},
            {"id": "targetFile",   "label": "Target File",     "type": "string", "required": True, "placeholder": "C:\\Users\\Public\\update.exe",  "default": "C:\\Users\\Public\\update.exe"},
            {"id": "referenceFile","label": "Reference File",  "type": "string", "required": True, "placeholder": "C:\\Windows\\System32\\cmd.exe", "default": "C:\\Windows\\System32\\cmd.exe"},
        ],
        "requirements": {"c2Server": True, "listeners": [], "payloads": [], "libraries": ["hunt_1.resource"]},
        "robotFramework": {
            "keyword": "Timestomp File",
            "resources": ["hunt_1.resource"],
            "keywordArgs": [
                {"param": "session",       "position": 1, "sessionVariable": "CURRENT_SESSION"},
                {"param": "targetFile",    "position": 2, "variableRef": False},
                {"param": "referenceFile", "position": 3, "variableRef": False},
            ],
            "pythonCall": "Run Btimestomp",
            "documentation": "Modify file timestamps",
            "tags": ["defense-evasion", "timestomp"],
        }
    },

    "cs-copy-beacon": {
        "_key": "cs-copy-beacon",
        "name": "Copy Beacon",
        "description": "Copy beacon executable to a new location on target to stage for persistence or lateral movement",
        "executionType": "cobalt_strike",
        "estimatedDuration": 5,
        "inputs": [
            {"id": "session", "label": "Beacon Session", "type": "session", "required": True}
        ],
        "outputs": [
            {"id": "session", "label": "Beacon Session", "type": "session", "description": "Session after copy"}
        ],
        "parameters": [
            {"id": "session",    "label": "Session",         "type": "string", "required": True, "placeholder": "${CURRENT_SESSION}",            "default": "${CURRENT_SESSION}"},
            {"id": "sourcePath", "label": "Source Path",     "type": "string", "required": True, "placeholder": "C:\\Windows\\Temp\\update.exe",  "default": "C:\\Windows\\Temp\\update.exe"},
            {"id": "destPath",   "label": "Destination Path","type": "string", "required": True, "placeholder": "C:\\Users\\Public\\update.exe",  "default": "C:\\Users\\Public\\update.exe"},
        ],
        "requirements": {"c2Server": True, "listeners": [], "payloads": [], "libraries": ["hunt_1.resource"]},
        "robotFramework": {
            "keyword": "Copy Beacon",
            "resources": ["hunt_1.resource"],
            "keywordArgs": [
                {"param": "session",    "position": 1, "sessionVariable": "CURRENT_SESSION"},
                {"param": "sourcePath", "position": 2, "variableRef": False},
                {"param": "destPath",   "position": 3, "variableRef": False},
            ],
            "pythonCall": "Issue Shell Cmd",
            "documentation": "Copy beacon to new location",
            "tags": ["defense-evasion", "copy"],
        }
    },

    # ── COLLECTION ────────────────────────────────────────────────────────────

    "cs-stage-data": {
        "_key": "cs-stage-data",
        "name": "Stage Data",
        "description": "Archive target files using PowerShell Compress-Archive to stage data for exfiltration",
        "executionType": "cobalt_strike",
        "estimatedDuration": 30,
        "inputs": [
            {"id": "session", "label": "Beacon Session", "type": "session", "required": True}
        ],
        "outputs": [
            {"id": "archive_ready", "label": "Archive Ready", "type": "string", "description": "Path to staged archive"}
        ],
        "parameters": [
            {"id": "session",      "label": "Session",       "type": "string", "required": True,  "placeholder": "${CURRENT_SESSION}",             "default": "${CURRENT_SESSION}"},
            {"id": "sourcePath",   "label": "Source Path",   "type": "string", "required": True,  "placeholder": "C:\\Users\\*\\Documents",         "default": "C:\\Users\\*\\Documents"},
            {"id": "archivePath",  "label": "Archive Path",  "type": "string", "required": True,  "placeholder": "C:\\Windows\\Temp\\staged.zip",   "default": "C:\\Windows\\Temp\\staged.zip"},
        ],
        "requirements": {"c2Server": True, "listeners": [], "payloads": [], "libraries": ["hunt_1.resource"]},
        "robotFramework": {
            "keyword": "Stage Data",
            "resources": ["hunt_1.resource"],
            "keywordArgs": [
                {"param": "session",     "position": 1, "sessionVariable": "CURRENT_SESSION"},
                {"param": "sourcePath",  "position": 2, "variableRef": False},
                {"param": "archivePath", "position": 3, "variableRef": False},
            ],
            "pythonCall": "Issue Powershell Cmd",
            "preKeywordLog": "=== Staging Data from ${sourcePath} ===",
            "documentation": "Archive data for exfiltration",
            "tags": ["collection", "stage"],
        }
    },

    "screenshot": {
        "_key": "screenshot",
        "name": "Screenshot",
        "description": "Capture a screenshot of the current desktop on the target host via beacon",
        "executionType": "cobalt_strike",
        "estimatedDuration": 5,
        "inputs": [
            {"id": "session", "label": "Beacon Session", "type": "session", "required": True}
        ],
        "outputs": [
            {"id": "screenshot_file", "label": "Screenshot File", "type": "string", "description": "Screenshot saved to artifact directory"}
        ],
        "parameters": [
            {"id": "session", "label": "Session", "type": "string", "required": True, "placeholder": "${CURRENT_SESSION}", "default": "${CURRENT_SESSION}"},
        ],
        "requirements": {"c2Server": True, "listeners": [], "payloads": [], "libraries": ["hunt_1.resource"]},
        "robotFramework": {
            "keyword": "Screenshot",
            "resources": ["hunt_1.resource"],
            "keywordArgs": [
                {"param": "session", "position": 1, "sessionVariable": "CURRENT_SESSION"},
            ],
            "pythonCall": "Issue Shell Cmd",
            "documentation": "Capture desktop screenshot",
            "tags": ["collection", "screenshot"],
        }
    },

    "cs-download-file": {
        "_key": "cs-download-file",
        "name": "Download File",
        "description": "Download a file from target to operator machine via Cobalt Strike beacon channel",
        "executionType": "cobalt_strike",
        "estimatedDuration": 30,
        "inputs": [
            {"id": "session", "label": "Beacon Session", "type": "session", "required": True}
        ],
        "outputs": [
            {"id": "file_downloaded", "label": "File Downloaded", "type": "boolean", "description": "File retrieved to operator machine"}
        ],
        "parameters": [
            {"id": "session",    "label": "Session",      "type": "string", "required": True, "placeholder": "${CURRENT_SESSION}",          "default": "${CURRENT_SESSION}"},
            {"id": "remotePath", "label": "Remote Path",  "type": "string", "required": True, "placeholder": "C:\\Windows\\Temp\\staged.zip","default": "C:\\Windows\\Temp\\staged.zip"},
        ],
        "requirements": {"c2Server": True, "listeners": [], "payloads": [], "libraries": ["hunt_1.resource"]},
        "robotFramework": {
            "keyword": "Download File",
            "resources": ["hunt_1.resource"],
            "keywordArgs": [
                {"param": "session",    "position": 1, "sessionVariable": "CURRENT_SESSION"},
                {"param": "remotePath", "position": 2, "variableRef": False},
            ],
            "pythonCall": "cobaltstrike.Download File",
            "documentation": "Download file from target",
            "tags": ["exfiltration", "download"],
        }
    },

    # ── IMPACT ────────────────────────────────────────────────────────────────

    "cs-stop-service": {
        "_key": "cs-stop-service",
        "name": "Stop Service",
        "description": "Stop a named Windows service via net stop command through beacon",
        "executionType": "cobalt_strike",
        "estimatedDuration": 10,
        "inputs": [
            {"id": "session", "label": "Beacon Session", "type": "session", "required": True}
        ],
        "outputs": [
            {"id": "service_stopped", "label": "Service Stopped", "type": "boolean", "description": "Service has been stopped"}
        ],
        "parameters": [
            {"id": "session",     "label": "Session",      "type": "string", "required": True, "placeholder": "${CURRENT_SESSION}", "default": "${CURRENT_SESSION}"},
            {"id": "serviceName", "label": "Service Name", "type": "string", "required": True, "placeholder": "WinDefend",          "default": "WinDefend"},
        ],
        "requirements": {"c2Server": True, "listeners": [], "payloads": [], "elevated": True, "libraries": ["hunt_1.resource"]},
        "robotFramework": {
            "keyword": "Stop Service",
            "resources": ["hunt_1.resource"],
            "keywordArgs": [
                {"param": "session",     "position": 1, "sessionVariable": "CURRENT_SESSION"},
                {"param": "serviceName", "position": 2, "variableRef": False},
            ],
            "pythonCall": "Issue Shell Cmd",
            "documentation": "Stop Windows service",
            "tags": ["impact", "service"],
        }
    },

    # ── BRUTE SIM ─────────────────────────────────────────────────────────────

    "brute-sim": {
        "_key": "brute-sim",
        "name": "Brute Sim",
        "description": "Simulate credential brute force activity against a domain with configurable attempt count and delay",
        "executionType": "cobalt_strike",
        "estimatedDuration": 60,
        "inputs": [
            {"id": "session", "label": "Beacon Session", "type": "session", "required": True}
        ],
        "outputs": [
            {"id": "brute_complete", "label": "Brute Sim Complete", "type": "boolean", "description": "Simulation completed"}
        ],
        "parameters": [
            {"id": "session",      "label": "Session",         "type": "string", "required": True,  "placeholder": "${CURRENT_SESSION}", "default": "${CURRENT_SESSION}"},
            {"id": "targetDomain", "label": "Target Domain",   "type": "string", "required": True,  "placeholder": "${DOMAIN1}",         "default": "${DOMAIN1}"},
            {"id": "userList",     "label": "User List",       "type": "string", "required": True,  "placeholder": "${BRUTESIM_INFO.userfile}", "default": "${BRUTESIM_INFO.userfile}"},
            {"id": "passFile",     "label": "Password File",   "type": "string", "required": True,  "placeholder": "${BRUTESIM_INFO.passfile}", "default": "${BRUTESIM_INFO.passfile}"},
            {"id": "attempts",     "label": "Max Attempts",    "type": "number", "required": False, "placeholder": "10",                 "default": 10},
            {"id": "delay",        "label": "Delay (seconds)", "type": "number", "required": False, "placeholder": "2",                  "default": 2},
        ],
        "requirements": {"c2Server": True, "listeners": [], "payloads": [], "libraries": ["hunt_1.resource"]},
        "robotFramework": {
            "keyword": "Brute Sim",
            "resources": ["hunt_1.resource"],
            "keywordArgs": [
                {"param": "session",      "position": 1, "sessionVariable": "CURRENT_SESSION"},
                {"param": "targetDomain", "position": 2, "variableRef": False},
                {"param": "userList",     "position": 3, "variableRef": False},
                {"param": "passFile",     "position": 4, "variableRef": False},
                {"param": "attempts",     "position": 5, "variableRef": False},
                {"param": "delay",        "position": 6, "variableRef": False},
            ],
            "pythonCall": "Issue Shell Cmd",
            "documentation": "Simulate credential brute force",
            "tags": ["credential-access", "brute-force"],
        }
    },

}


def write_payloads():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    written = []
    for key, payload in MODULES.items():
        path = os.path.join(OUTPUT_DIR, f"{key}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        written.append(key)
        print(f"  ✓ {key}.json")

    print(f"\n✅ Wrote {len(written)} payload files to {OUTPUT_DIR}/")

    # Verify keys match what GraphDB expects
    print("\nVerifying against GraphDB module list...")
    expected_keys = [
        "brute-sim", "cs-copy-beacon", "cs-create-listener", "cs-delete-file",
        "cs-download-file", "cs-dump-credentials", "cs-elevate-spawnas",
        "cs-generate-payload", "cs-get-arp", "cs-get-processes",
        "cs-get-session-by-ip", "cs-get-pwd", "cs-getuid",
        "cs-initial-access", "cs-inject-process", "cs-kill-session",
        "cs-lateral-psexec", "cs-lateral-winrm", "cs-list-directory",
        "cs-move-beacon", "cs-network-enumerate", "cs-persistence-registry",
        "cs-persistence-schtasks", "cs-query-registry", "screenshot",
        "cs-session-sleep", "cs-stage-data", "cs-start-c2", "cs-stop-c2",
        "cs-stop-service", "cs-timestomp", "cs-upload-file",
    ]
    missing = [k for k in expected_keys if k not in MODULES]
    extra = [k for k in MODULES if k not in expected_keys]

    if missing:
        print(f"  ⚠ Missing payloads for: {missing}")
    if extra:
        print(f"  ℹ Extra payloads (not in GraphDB): {extra}")
    if not missing and not extra:
        print("  ✓ All 33 keys match GraphDB exactly")


if __name__ == "__main__":
    write_payloads()