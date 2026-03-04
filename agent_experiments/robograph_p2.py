# robograph_p2.py

import ollama
from datetime import datetime
import time
import json
from pathlib import Path
from typing import Dict, List, Optional, Set
from collections import Counter
import re

# Configuration
OLLAMA_HOST = "http://10.10.80.99:4001"
LARGE_MODEL = "gpt-oss:120b"

# ============================================================================
# PHASE 1 → PHASE 2 ADAPTER
# ============================================================================

class Phase1ToPhase2Adapter:
    """
    Transform Phase 1 output format to Phase 2 input format
    """
    
    @staticmethod
    def transform(phase1_output: Dict) -> Dict:
        """
        Convert Phase 1 extraction format to Phase 2 expected format
        
        Flattens per-segment data into global structures
        """
        
        extractions = phase1_output.get("extractions", {})
        
        # Transform 1: Flatten command sequences
        command_sequences = []
        for segment_cmds in extractions.get("commands", []):
            for cmd in segment_cmds.get("commands", []):
                # Add segment context to each command
                cmd['segment_id'] = segment_cmds.get('segment_id')
                cmd['segment_title'] = segment_cmds.get('segment_title')
                command_sequences.append(cmd)
        
        # Transform 2: Build network topology
        network_topology = Phase1ToPhase2Adapter._build_network_topology(
            extractions.get("network_relationships", []),
            extractions.get("ip_credentials", {})
        )
        
        # Transform 3: Aggregate tools
        tools_used = []
        for segment_tools in extractions.get("tools", []):
            tools_used.extend(segment_tools.get("tools", []))
        
        # Transform 4: Aggregate file paths
        all_file_paths = {
            "windows": [],
            "linux": []
        }
        for segment_paths in extractions.get("file_paths", []):
            paths = segment_paths.get("paths", {})
            all_file_paths["windows"].extend(paths.get("windows", []))
            all_file_paths["linux"].extend(paths.get("linux", []))
        
        return {
            "command_sequences": command_sequences,
            "network_topology": network_topology,
            "tools_used": tools_used,
            "file_paths": all_file_paths,
            "ip_credentials": extractions.get("ip_credentials", {}),
            "meta_narrative": phase1_output.get("meta_narrative", {}),
            "segments": phase1_output.get("segments", {})
        }
    
    @staticmethod
    def _build_network_topology(network_relationships: List[Dict], ip_credentials: Dict) -> Dict:
        """
        Aggregate network relationships into a unified topology
        """
        
        # Aggregate IP roles across all segments
        ip_role_map = {}
        all_connections = []
        
        for segment_rel in network_relationships:
            segment_id = segment_rel.get("segment_id")
            relationships = segment_rel.get("relationships", {})
            
            # Aggregate IP roles
            for ip_role in relationships.get("ip_roles", []):
                ip = ip_role.get("ip")
                role = ip_role.get("role")
                
                if ip not in ip_role_map:
                    ip_role_map[ip] = {
                        "ip_address": ip,
                        "role": role,
                        "segment_ids": []
                    }
                
                ip_role_map[ip]["segment_ids"].append(segment_id)
            
            # Aggregate connections
            all_connections.extend(relationships.get("connections", []))
        
        # Generate logical names from IP addresses or roles
        hosts = []
        for ip, data in ip_role_map.items():
            role = data.get("role", "unknown")
            logical_name = Phase1ToPhase2Adapter._generate_logical_name(ip, role)
            
            hosts.append({
                "ip_address": ip,
                "logical_name": logical_name,
                "role": role,
                "segment_ids": data["segment_ids"]
            })
        
        return {
            "hosts": hosts,
            "connections": all_connections
        }
    
    @staticmethod
    def _generate_logical_name(ip: str, role: str) -> str:
        """
        Generate logical hostname from IP and role
        """
        
        # Extract last octet
        last_octet = ip.split(".")[-1]
        
        # Map role to prefix
        role_prefix_map = {
            "target_victim": "TARGET",
            "pivot_host": "PIVOT",
            "c2_server": "C2",
            "attacker_source": "ATTACKER",
        }
        
        prefix = role_prefix_map.get(role, "HOST")
        
        return f"DI-{prefix}-{last_octet}"


# ============================================================================
# SETTINGS SECTION GENERATOR
# ============================================================================

class SettingsSectionGenerator:
    """
    Generate *** Settings *** section based on detected tools
    """
    
    def __init__(self):
        pass
    
    def generate(self, phase1_data: Dict) -> Dict:
        """Generate Settings section from Phase 1 data"""
        
        print(f"\n🔧 Generating Settings Section...")
        
        # Extract tool contexts from commands
        tool_contexts = set()
        for cmd in phase1_data.get("command_sequences", []):
            tool = cmd.get("tool_context")
            if tool:
                tool_contexts.add(tool.lower())
        
        # Determine required libraries
        libraries = self._determine_libraries(tool_contexts)
        resources = self._determine_resources(libraries)
        
        print(f"   ✓ Detected tools: {sorted(tool_contexts)}")
        print(f"   ✓ Required libraries: {len(libraries)}")
        
        return {
            "libraries": libraries,
            "resources": resources,
            "documentation": phase1_data.get("meta_narrative", {}).get("meta_narrative", "Automated workflow")
        }
    
    def _determine_libraries(self, tool_contexts: Set[str]) -> List[str]:
        """Map tool contexts to Robot Framework libraries"""
        
        libraries = [
            "BuiltIn",
            "LogLibrary.py",
            "DateTime",
            "Collections"
        ]
        
        # Map tools to libraries
        if any(t in tool_contexts for t in ["metasploit", "meterpreter", "bash", "powershell", "nmap"]):
            libraries.append("Process")
        
        if "ssh" in tool_contexts or any("ssh" in t for t in tool_contexts):
            libraries.append("SSHLibrary")
        
        if any("cobalt" in t for t in tool_contexts):
            libraries.append("cobaltstrike.C2Keywords")
        
        if "sliver" in tool_contexts:
            libraries.append("sliverc2.SliverRobotLibrary")
        
        if any(t in tool_contexts for t in ["metasploit", "meterpreter"]):
            libraries.append("OperatingSystem")
        
        return sorted(set(libraries))
    
    def _determine_resources(self, libraries: List[str]) -> List[str]:
        """Determine resource files based on libraries"""
        
        resources = []
        
        if "cobaltstrike.C2Keywords" in libraries:
            resources.append("../cobaltstrike/cobaltstrike.resource")
        
        if "sliverc2.SliverRobotLibrary" in libraries:
            resources.append("../sliverc2/sliverc2.resource")
        
        return resources
    
    def render(self, variables_data: Dict) -> str:
        """Render Variables section to Robot Framework syntax"""
        
        lines = ["*** Variables ***"]
        
        # Group variables
        variables = variables_data.get("variables", {})
        grouped = {}
        
        for var_name, var_data in variables.items():
            group = var_data.get("group", "Other")
            if group not in grouped:
                grouped[group] = []
            grouped[group].append((var_name, var_data))
        
        # Render in order
        group_order = [
            "Network Topology",
            "Credentials",
            "C2 Infrastructure (TODO)",
            "Configuration",
            "File Paths",
            "Other"
        ]
        
        for group_name in group_order:
            if group_name not in grouped:
                continue
            
            lines.append(f"\n# {group_name}")
            
            # Calculate max variable name length in this group
            group_vars = grouped[group_name]
            max_var_len = max(len(f"${{{var_name}}}") for var_name, _ in group_vars)
            
            # Add padding to align values nicely
            # Use next multiple of 4 for tab-like alignment
            value_column = ((max_var_len // 4) + 1) * 4
            
            for var_name, var_data in sorted(group_vars):
                value = var_data.get("value", "")
                comment = var_data.get("comment", "")
                
                var_line = f"${{{var_name}}}"
                padding = " " * (value_column - len(var_line))
                
                if comment:
                    lines.append(f"{var_line}{padding}{value}    # {comment}")
                else:
                    lines.append(f"{var_line}{padding}{value}")
        
        return "\n".join(lines)


# ============================================================================
# VARIABLES SECTION GENERATOR
# ============================================================================

class VariablesSectionGenerator:
    """
    Generate *** Variables *** section from Phase 1 extractions
    """
    
    def __init__(self):
        pass
    
    def generate(self, phase1_data: Dict) -> Dict:
        """Generate Variables section from Phase 1 data"""
        
        print(f"\n🔧 Generating Variables Section...")
        
        # Extract data
        network_hosts = phase1_data.get("network_topology", {}).get("hosts", [])
        credentials = phase1_data.get("ip_credentials", {}).get("credentials", {}).get("all_credentials", [])
        file_paths = phase1_data.get("file_paths", {})
        
        # Generate variable groups
        variables = {}
        
        # Network topology variables
        self._add_network_variables(variables, network_hosts)
        
        # Credential variables
        self._add_credential_variables(variables, credentials)
        
        # File path variables
        self._add_file_path_variables(variables, file_paths)
        
        # Standard configuration variables (with TODOs)
        self._add_standard_variables(variables)
        
        print(f"   ✓ Generated {len(variables)} variables")
        
        return {"variables": variables}
    
    def _add_network_variables(self, variables: Dict, hosts: List[Dict]):
        """Add network topology variables"""
        
        # Sort hosts by role priority
        role_priority = {"target_victim": 1, "c2_server": 2, "pivot_host": 3, "attacker_source": 4}
        sorted_hosts = sorted(hosts, key=lambda h: role_priority.get(h.get("role"), 99))
        
        for host in sorted_hosts:
            ip = host.get("ip_address")
            name = host.get("logical_name", "").replace("-", "_").upper()
            role = host.get("role", "unknown")
            
            if ip and name:
                var_name = f"TARGET_{name}_IP"
                variables[var_name] = {
                    "value": ip,
                    "comment": f"{host.get('logical_name')} ({role})",
                    "group": "Network Topology"
                }
    
    def _add_credential_variables(self, variables: Dict, credentials: List[Dict]):
        """Add credential variables"""
        
        # Group credentials by type
        seen_users = set()
        
        for cred in credentials:
            username = cred.get("username")
            password = cred.get("password")
            cred_type = cred.get("type", "unknown")
            
            if not username:
                continue
            
            # Create base variable name
            if "\\" in username:
                # Domain credentials: DI\Administrator -> ADMIN
                user_part = username.split("\\")[-1]
                base_name = user_part.upper().replace(".", "_")
            else:
                base_name = username.upper().replace(".", "_").replace("@", "_AT_")
            
            # Avoid duplicates
            if base_name in seen_users:
                continue
            seen_users.add(base_name)
            
            # Add username variable
            variables[f"{base_name}_USER"] = {
                "value": username,
                "comment": cred_type,
                "group": "Credentials"
            }
            
            # Add password variable if present
            if password:
                variables[f"{base_name}_PASS"] = {
                    "value": password,
                    "comment": "",
                    "group": "Credentials"
                }
    
    def _add_file_path_variables(self, variables: Dict, file_paths: Dict):
        """Add file path variables"""
        
        # Extract unique payload paths
        windows_paths = file_paths.get("windows", [])
        linux_paths = file_paths.get("linux", [])
        
        # Look for artifact/payload directories
        for path_obj in linux_paths:
            path = path_obj.get("path", "")
            role = path_obj.get("role", "")
            
            if "artifact" in path.lower() or role == "source":
                if "ARTIFACT_DIR" not in variables:
                    # Extract directory from path
                    if "/" in path:
                        dir_path = "/".join(path.split("/")[:-1])
                        variables["ARTIFACT_DIR"] = {
                            "value": dir_path or "./artifacts",
                            "comment": "Payload directory",
                            "group": "File Paths"
                        }
    
    def _add_standard_variables(self, variables: Dict):
        """Add standard configuration variables with TODOs"""
        
        # Logging
        variables["LOG_FILENAME"] = {
            "value": "execution_log.csv",
            "comment": "",
            "group": "Configuration"
        }
        
        # Artifact directory (if not already added)
        if "ARTIFACT_DIR" not in variables:
            variables["ARTIFACT_DIR"] = {
                "value": "./artifacts",
                "comment": "",
                "group": "Configuration"
            }
        
        # Beacon timeout
        variables["BEACON_TIMEOUT"] = {
            "value": "2m",
            "comment": "C2 beacon check-in timeout",
            "group": "Configuration"
        }
        
        # TODO placeholders for missing config
        variables["CS_IP"] = {
            "value": "# TODO: C2_SERVER_IP",
            "comment": "Cobalt Strike server IP",
            "group": "C2 Infrastructure (TODO)"
        }
        
        variables["CS_USER"] = {
            "value": "# TODO: C2_USERNAME",
            "comment": "Cobalt Strike username",
            "group": "C2 Infrastructure (TODO)"
        }
        
        variables["CS_PASS"] = {
            "value": "# TODO: C2_PASSWORD",
            "comment": "Cobalt Strike password",
            "group": "C2 Infrastructure (TODO)"
        }
        
        variables["CS_DIR"] = {
            "value": "/opt/cobaltstrike",
            "comment": "Cobalt Strike directory",
            "group": "C2 Infrastructure (TODO)"
        }
        
        variables["CS_PORT"] = {
            "value": "50050",
            "comment": "Cobalt Strike port",
            "group": "C2 Infrastructure (TODO)"
        }
    
    def render(self, variables_data: Dict) -> str:
        """Render Variables section to Robot Framework syntax"""
        
        lines = ["*** Variables ***"]
        
        # Group variables
        variables = variables_data.get("variables", {})
        grouped = {}
        
        for var_name, var_data in variables.items():
            group = var_data.get("group", "Other")
            if group not in grouped:
                grouped[group] = []
            grouped[group].append((var_name, var_data))
        
        # Render in order
        group_order = [
            "Network Topology",
            "Credentials",
            "C2 Infrastructure (TODO)",
            "Configuration",
            "File Paths",
            "Other"
        ]
        
        for group_name in group_order:
            if group_name not in grouped:
                continue
            
            lines.append(f"\n# {group_name}")
            
            for var_name, var_data in sorted(grouped[group_name]):
                value = var_data.get("value", "")
                comment = var_data.get("comment", "")
                
                var_line = f"${{{var_name}}}"
                padding = " " * max(1, 25 - len(var_line))
                
                if comment:
                    lines.append(f"{var_line}{padding}{value}    # {comment}")
                else:
                    lines.append(f"{var_line}{padding}{value}")
        
        return "\n".join(lines)


# ============================================================================
# KEYWORDS SECTION GENERATOR
# ============================================================================

class KeywordsSectionGenerator:
    """
    Generate *** Keywords *** section with commented command examples
    """
    
    def __init__(self):
        pass
    
    def generate(self, phase1_data: Dict) -> Dict:
        """Generate Keywords section with commented examples"""
        
        print(f"\n🔧 Generating Keywords Section...")
        
        # Detect common patterns
        ssh_count = 0
        timing_count = 0
        
        for cmd in phase1_data.get("command_sequences", []):
            command = cmd.get("command", "").lower()
            
            if "ssh" in command or "open connection" in command:
                ssh_count += 1
            
            if any(word in command for word in ["sleep", "pause", "wait"]):
                timing_count += 1
        
        # Generate standard keywords
        keywords = []
        
        if timing_count >= 3:
            keywords.append({
                "name": "Command Pause",
                "args": [],
                "documentation": "Random pause between commands (45-120s)",
                "body": [
                    "${pause}=    Evaluate    random.randint(45, 120)",
                    "Log To Console    Pausing for ${pause} seconds",
                    "Sleep    ${pause}"
                ]
            })
        
        if ssh_count >= 3:
            keywords.append({
                "name": "Get Local Terminal",
                "args": ["host", "username", "password", "alias"],
                "documentation": "Establish SSH connection to local host",
                "body": [
                    "Open Connection    ${host}    alias=${alias}    timeout=300s",
                    "Login    ${username}    ${password}"
                ]
            })
        
        # Add commented command examples
        example_commands = self._get_example_commands(phase1_data)
        
        print(f"   ✓ Generated {len(keywords)} keywords")
        print(f"   ✓ Extracted {len(example_commands)} example commands")
        
        return {
            "keywords": keywords,
            "example_commands": example_commands
        }
    
    def _get_example_commands(self, phase1_data: Dict) -> List[Dict]:
        """Extract example commands for reference"""
        
        examples = []
        segments = phase1_data.get("segments", {}).get("segments", [])
        
        for segment in segments:
            segment_title = segment.get("title", "Unknown")
            segment_id = segment.get("id")
            
            # Get commands for this segment
            segment_commands = [
                cmd for cmd in phase1_data.get("command_sequences", [])
                if cmd.get("segment_id") == segment_id
            ]
            
            if segment_commands:
                examples.append({
                    "segment_title": segment_title,
                    "segment_id": segment_id,
                    "commands": segment_commands[:5]  # First 5 commands
                })
        
        return examples
    
    def render(self, keywords_data: Dict) -> str:
        """Render Keywords section to Robot Framework syntax"""
        
        lines = ["*** Keywords ***"]
        
        # Render actual keywords
        for kw in keywords_data.get("keywords", []):
            lines.append(f"\n{kw['name']}")
            
            if kw.get("args"):
                args_str = "    ".join([f"${{{arg}}}" for arg in kw["args"]])
                lines.append(f"    [Arguments]    {args_str}")
            
            if kw.get("documentation"):
                lines.append(f"    [Documentation]    {kw['documentation']}")
            
            for body_line in kw.get("body", []):
                lines.append(f"    {body_line}")
        
        # Add commented example commands
        lines.append("\n")
        lines.append("# ============================================================================")
        lines.append("# EXTRACTED COMMANDS (For Reference)")
        lines.append("# ============================================================================")
        lines.append("# Below are the commands extracted from Phase 1.")
        lines.append("# Use these as templates for building test cases.")
        lines.append("")
        
        for example in keywords_data.get("example_commands", []):
            segment_title = example.get("segment_title")
            lines.append(f"\n# Segment: {segment_title}")
            lines.append("# " + "-" * 70)
            
            for cmd in example.get("commands", []):
                command = cmd.get("command", "")
                tool = cmd.get("tool_context", "unknown")
                target = cmd.get("target", "")
                
                lines.append(f"# [{tool}] {command[:100]}")
                if target:
                    lines.append(f"#          Target: {target}")
        
        return "\n".join(lines)


# ============================================================================
# TEST CASES SECTION GENERATOR
# ============================================================================

class TestCasesSectionGenerator:
    """
    Generate *** Test Cases *** section with commented structure
    """
    
    def __init__(self):
        pass
    
    def generate(self, phase1_data: Dict) -> Dict:
        """Generate commented test case structure"""
        
        print(f"\n🔧 Generating Test Cases Section...")
        
        segments = phase1_data.get("segments", {}).get("segments", [])
        
        test_cases = []
        
        for segment in segments:
            segment_title = segment.get("title", "Unknown")
            segment_id = segment.get("id")
            rationale = segment.get("rationale", "")
            
            # Get commands for this segment
            segment_commands = [
                cmd for cmd in phase1_data.get("command_sequences", [])
                if cmd.get("segment_id") == segment_id
            ]
            
            test_cases.append({
                "name": segment_title,
                "segment_id": segment_id,
                "rationale": rationale,
                "command_count": len(segment_commands),
                "commands": segment_commands
            })
        
        print(f"   ✓ Structured {len(test_cases)} test cases")
        
        return {"test_cases": test_cases}
    
    def render(self, test_cases_data: Dict) -> str:
        """Render Test Cases section with commented structure"""
        
        lines = ["*** Test Cases ***"]
        lines.append("")
        lines.append("# ============================================================================")
        lines.append("# AUTOMATED TEST CASES")
        lines.append("# ============================================================================")
        lines.append("# Each test case corresponds to a segment from Phase 1.")
        lines.append("# Commands are listed as comments for reference.")
        lines.append("# TODO: Uncomment and parameterize commands as needed.")
        lines.append("")
        
        for test_case in test_cases_data.get("test_cases", []):
            name = test_case.get("name")
            rationale = test_case.get("rationale", "")
            commands = test_case.get("commands", [])
            
            lines.append(f"\n{name}")
            lines.append(f"    [Documentation]    {rationale}")
            lines.append(f"    [Tags]    segment-{test_case.get('segment_id')}")
            lines.append("")
            lines.append(f"    # TODO: Implement {len(commands)} commands")
            lines.append("    Log To Console    TODO: Execute segment commands")
            
            # Add commented command list
            for i, cmd in enumerate(commands[:10], 1):  # First 10 commands
                command = cmd.get("command", "")[:80]
                tool = cmd.get("tool_context", "unknown")
                lines.append(f"    # {i}. [{tool}] {command}")
                if i < len(commands) and i == 10:
                    lines.append(f"    # ... and {len(commands) - 10} more commands")
        
        return "\n".join(lines)


# ============================================================================
# PHASE 2 ORCHESTRATOR
# ============================================================================

class Phase2RobotGenerator:
    """
    Phase 2 Orchestrator: Generate complete Robot Framework script
    """
    
    def __init__(self):
        self.settings_gen = SettingsSectionGenerator()
        self.variables_gen = VariablesSectionGenerator()
        self.keywords_gen = KeywordsSectionGenerator()
        self.testcases_gen = TestCasesSectionGenerator()
    
    def generate(self, phase1_output: Dict) -> Dict:
        """Generate complete Robot Framework script from Phase 1 output"""
        
        print("=" * 70)
        print("PHASE 2: ROBOT FRAMEWORK GENERATION")
        print("=" * 70)
        
        start_time = time.time()
        
        # Transform Phase 1 data
        print("\n🔄 Transforming Phase 1 data...")
        adapter = Phase1ToPhase2Adapter()
        phase1_data = adapter.transform(phase1_output)
        
        # Generate each section
        settings_data = self.settings_gen.generate(phase1_data)
        variables_data = self.variables_gen.generate(phase1_data)
        keywords_data = self.keywords_gen.generate(phase1_data)
        testcases_data = self.testcases_gen.generate(phase1_data)
        
        # Render sections
        settings_section = self.settings_gen.render(settings_data)
        variables_section = self.variables_gen.render(variables_data)
        keywords_section = self.keywords_gen.render(keywords_data)
        testcases_section = self.testcases_gen.render(testcases_data)
        
        elapsed_time = time.time() - start_time
        
        print(f"\n✅ Phase 2 Complete in {elapsed_time:.1f}s")
        
        return {
            "settings_section": settings_section,
            "variables_section": variables_section,
            "keywords_section": keywords_section,
            "testcases_section": testcases_section,
            "metadata": {
                "generation_time": elapsed_time,
                "total_variables": len(variables_data.get("variables", {})),
                "total_keywords": len(keywords_data.get("keywords", [])),
                "total_test_cases": len(testcases_data.get("test_cases", []))
            }
        }


# ============================================================================
# TEST FUNCTION
# ============================================================================

def test_robograph_p2():
    """Test Phase 2: Robot Framework Generation"""
    
    phase1_file = Path("agent_output_full.json")
    
    if not phase1_file.exists():
        print(f"\n❌ Error: {phase1_file} not found")
        print(f"   Please run Phase 1 extraction first")
        return False
    
    phase1_output = json.loads(phase1_file.read_text(encoding="utf-8"))
    
    print(f"\n📄 Loaded Phase 1 output from: {phase1_file}")
    
    try:
        generator = Phase2RobotGenerator()
        result = generator.generate(phase1_output)
        
        # Print results
        print("\n" + "=" * 70)
        print("GENERATED ROBOT FRAMEWORK SCRIPT")
        print("=" * 70)
        
        print("\n" + result["settings_section"])
        print("\n" + result["variables_section"])
        print("\n" + result["keywords_section"])
        print("\n" + result["testcases_section"])
        
        # Save complete Robot script
        robot_file = Path("generated_robot_script.robot")
        with open(robot_file, "w", encoding="utf-8") as f:
            f.write(result["settings_section"])
            f.write("\n\n")
            f.write(result["variables_section"])
            f.write("\n\n")
            f.write(result["keywords_section"])
            f.write("\n\n")
            f.write(result["testcases_section"])
        
        # Save metadata
        output_file = Path("robograph_p2_output.json")
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        print(f"\n💾 Complete Robot script saved to: {robot_file}")
        print(f"💾 Phase 2 metadata saved to: {output_file}")
        
        print(f"\n📊 Generation Summary:")
        print(f"   Variables: {result['metadata']['total_variables']}")
        print(f"   Keywords: {result['metadata']['total_keywords']}")
        print(f"   Test Cases: {result['metadata']['total_test_cases']}")
        print(f"   Time: {result['metadata']['generation_time']:.1f}s")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_robograph_p2()
    exit(0 if success else 1)