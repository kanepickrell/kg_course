# phase3_testcase_generator.py

import ollama
from datetime import datetime
import time
import json
from pathlib import Path
from typing import Dict, List
import re

# Configuration
OLLAMA_HOST = "http://10.10.80.99:4001"
OLLAMA_MODEL = "gpt-oss:120b"

class TacticTestCaseGenerator:
    """
    Phase 3: Generate Robot Framework test cases for each tactic independently
    """
    
    def __init__(self, host=OLLAMA_HOST, model=OLLAMA_MODEL):
        self.client = ollama.Client(host=host)
        self.model = model
    
    def generate_all_test_cases(self, 
                                 tactical_breakdown: dict,
                                 library_mapping: dict,
                                 variables_dict: dict) -> dict:
        """
        Generate test cases for all tactics
        Returns dict with test_cases and keywords sections
        """
        
        print(f"🔨 Generating test cases for all tactics...")
        print(f"   Model: {self.model}")
        print(f"   Tactics to process: {len(tactical_breakdown['tactics'])}")
        print("-" * 70)
        
        all_test_cases = []
        all_keywords = []
        
        for tactic in tactical_breakdown['tactics']:
            tactic_name = tactic['tactic_name']
            
            print(f"\n🎯 Generating test case: {tactic_name}")
            
            # Get library suggestions for this tactic
            tactic_libs = library_mapping['tactic_library_map'].get(tactic_name, {})
            
            # Generate test case
            result = self.generate_test_case_for_tactic(
                tactic=tactic,
                library_suggestions=tactic_libs,
                variables=variables_dict
            )
            
            all_test_cases.append(result['test_case'])
            if result.get('keywords'):
                all_keywords.append(result['keywords'])
            
            print(f"   ✓ Test case generated")
            print(f"   ✓ Keywords: {len(result.get('keywords', '').split('\\n')) if result.get('keywords') else 0}")
        
        print(f"\n✅ All Test Cases Generated")
        print(f"   Total test cases: {len(all_test_cases)}")
        
        return {
            "test_cases": all_test_cases,
            "keywords": all_keywords
        }
    
    def generate_test_case_for_tactic(self,
                                       tactic: dict,
                                       library_suggestions: dict,
                                       variables: dict) -> dict:
        """
        Generate a single test case for one tactic
        Returns dict with 'test_case' and 'keywords' sections
        """
        
        # Build focused context for this tactic
        context = self._build_tactic_context(tactic, library_suggestions, variables)
        
        prompt = f"""{context}

GENERATION TASK:
Generate a Robot Framework test case for the tactic described above.

OUTPUT REQUIREMENTS:
Return ONLY valid Robot Framework code with these sections:

1. TEST CASE section (required)
2. KEYWORDS section (if helper keywords are needed)

FORMAT RULES:
- Use proper Robot Framework syntax with 4 spaces for indentation
- Mark test case with [Documentation] and [Tags] for MITRE techniques
- Use variables from AVAILABLE VARIABLES (format: ${{VAR_NAME}})
- Use ONLY keywords listed in AVAILABLE KEYWORDS
- If exact keyword doesn't exist, use "# DEV: Review - [explanation]" comment
- Add "Log It" calls after significant actions with MITRE technique IDs
- Target 70-80% completion - mark uncertain areas with comments
- Use "Log To Console" for progress updates

STRUCTURE:
*** Test Cases ***
{tactic['tactic_name'].replace(' ', '_').replace('-', '_')}
    [Documentation]    {tactic['objective']}
    [Tags]    {tactic.get('mitre_id', 'CUSTOM')}
    
    Log To Console    \\n[{tactic['tactic_name'].upper()}] Starting...
    
    # Your implementation here
    # Call keywords (either built-in or custom keywords defined below)
    
    Log It    ${{LOG_FILENAME}}    {tactic['tactic_name']} completed    machine=${{RHOSTS}}    tid={tactic.get('mitre_id', 'CUSTOM')}    ioc=${{EMPTY}}

*** Keywords ***
# Define custom keywords here if needed
# Each keyword should be a reusable helper function

GENERATION GUIDELINES:
1. For metasploit exploits: Create resource script, run msfconsole with -r flag
2. For file operations: Use appropriate library (OperatingSystem or cobaltstrike.C2Keywords)
3. For cobalt strike: Use C2Keywords library functions
4. For system commands: Use Run Process or Execute Command
5. Always log with MITRE ATT&CK technique IDs where applicable
6. Add "# DEV:" comments for:
   - Timeout values that may need adjustment
   - Missing beacon callback handling
   - Unclear tool transitions
   - Parameters that need validation

Return ONLY the Robot Framework code, no markdown formatting, no explanations.
"""
        
        try:
            start_time = time.time()
            
            messages = [
                {
                    "role": "system",
                    "content": "You are a Robot Framework expert. Generate valid Robot Framework test code only. No markdown, no explanations."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ]
            
            response = self.client.chat(
                model=self.model,
                messages=messages
            )
            
            elapsed_time = time.time() - start_time
            reply = response['message']['content']
            
            # Performance metrics
            eval_count = response.get('eval_count', 0)
            eval_duration = response.get('eval_duration', 0) / 1e9
            
            if eval_count > 0 and eval_duration > 0:
                tokens_per_sec = eval_count / eval_duration
                print(f"   Generation time: {elapsed_time:.2f}s ({tokens_per_sec:.1f} tok/s)")
            
            # Clean and split response
            result = self._parse_robot_code(reply)
            
            return result
            
        except Exception as e:
            print(f"   ⚠️  Generation failed: {e}")
            return self._fallback_test_case(tactic)
    
    def _build_tactic_context(self, tactic: dict, library_suggestions: dict, variables: dict) -> str:
        """Build focused context with only relevant information for this tactic"""
        
        context = f"""You are generating a Robot Framework test case for a single cyber operation tactic.

TACTIC DETAILS:
Name: {tactic['tactic_name']}
Objective: {tactic['objective']}
MITRE ATT&CK: {tactic.get('mitre_id', 'CUSTOM')}
Sequence: #{tactic['sequence_number']}
Tools: {', '.join(tactic.get('tools_mentioned', []))}

ACTIONS TO IMPLEMENT:
"""
        
        for idx, action in enumerate(tactic['actions'], 1):
            context += f"\n{idx}. {action['action_type'].upper()} ({action['tool']})\n"
            context += f"   Command: {action['command_or_description']}\n"
            context += f"   Target: {action.get('target', 'N/A')}\n"
            if action.get('critical_parameters'):
                context += f"   Parameters: {json.dumps(action['critical_parameters'], indent=6)}\n"
        
        context += f"\n\nAVAILABLE KEYWORDS (from suggested libraries):\n"
        
        # Add suggested keywords
        if library_suggestions.get('suggested_keywords'):
            for kw in library_suggestions['suggested_keywords']:
                context += f"\n- {kw['keyword']} ({kw['library']})\n"
                context += f"  Use: {kw['use_case']}\n"
                if kw.get('example_usage'):
                    context += f"  Example: {kw['example_usage']}\n"
        
        # Add tool-specific patterns
        tools = tactic.get('tools_mentioned', [])
        
        if 'metasploit' in tools:
            context += self._get_metasploit_pattern()
        
        if 'cobaltstrike' in tools:
            context += self._get_cobaltstrike_pattern()
        
        if 'system' in tools:
            context += self._get_system_command_pattern()
        
        context += f"\n\nAVAILABLE VARIABLES:\n"
        for var_name, var_value in sorted(variables.items()):
            context += f"- ${{{var_name}}} = {var_value}\n"
        
        return context
    
    def _get_metasploit_pattern(self) -> str:
        return """

METASPLOIT AUTOMATION PATTERN:
================================
Common approach: Create resource script (.rc file), then run msfconsole

Example Pattern:
```robot
Create MSF Resource Script
    [Documentation]    Generate Metasploit resource script
    ${{rc_content}}=    Catenate    SEPARATOR=\\n
    ...    use exploit/MODULE_NAME
    ...    set RHOSTS ${{RHOSTS}}
    ...    set PAYLOAD ${{PAYLOAD}}
    ...    run
    ...    sleep 10
    Create File    ${{RESOURCE_FILE}}    ${{rc_content}}
    Log To Console    Resource script created

Execute Metasploit Exploit
    [Documentation]    Run msfconsole with resource script
    ${{result}}=    Run Process    msfconsole    -q    -r    ${{RESOURCE_FILE}}
    ...    stdout=${{MSF_OUTPUT_FILE}}    timeout=300s
    Should Be Equal As Integers    ${{result.rc}}    0
    
    ${{output}}=    Get File    ${{MSF_OUTPUT_FILE}}
    # DEV: Add validation for Meterpreter session establishment
    Should Contain    ${{output}}    session
```
"""
    
    def _get_cobaltstrike_pattern(self) -> str:
        return """

COBALT STRIKE BEACON PATTERN:
================================
Typical workflow: Wait for callback -> Set active -> Interact -> Cleanup

Example Pattern:
```robot
Deploy Beacon
    [Documentation]    Wait for beacon and configure
    ${{beacon}}=    Wait For Beacon Checkin With Specific Ip    ${{RHOSTS}}    timeout=5m
    Set Global Variable    ${{active_beacon}}    ${{beacon}}
    Set Active Beacon    ${{active_beacon}}
    
    ${{beacon_info}}=    Get Beacon Info    ${{active_beacon}}
    ${{beacon_host}}=    Get From Dictionary    ${{beacon_info}}    host
    Log To Console    Beacon active on ${{beacon_host}}

Interact With Beacon
    [Documentation]    Execute commands via beacon
    Set Active Beacon    ${{active_beacon}}
    
    Change Directory    C:\\\\Path\\\\To\\\\Dir
    Upload File    /local/file.exe    C:\\\\Remote\\\\file.exe
    
    # Execute via PowerShell
    Run PsCommand    Start-Process -FilePath "C:\\\\Remote\\\\file.exe"
```
"""
    
    def _get_system_command_pattern(self) -> str:
        return """

SYSTEM COMMAND PATTERN:
================================
For network configuration or system-level operations

Example Pattern:
```robot
Configure System
    [Documentation]    Execute system configuration command
    
    # DEV: Verify the exact command syntax for your environment
    ${{result}}=    Run Process    bash    -c    echo "config command here"
    ...    timeout=30s
    
    Log    ${{result.stdout}}
    Should Be Equal As Integers    ${{result.rc}}    0
    
    Log It    ${{LOG_FILENAME}}    System configured    machine=${{HOST}}    tid=CUSTOM    ioc=${{EMPTY}}
```
"""
    
    def _parse_robot_code(self, response_text: str) -> dict:
        """Parse Robot Framework code into test case and keywords sections"""
        
        # Clean up markdown if present
        cleaned = response_text.strip()
        if cleaned.startswith("```robot"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
        
        # Split into test cases and keywords
        if "*** Keywords ***" in cleaned:
            parts = cleaned.split("*** Keywords ***")
            test_case_raw = parts[0].strip()
            keywords_raw = "*** Keywords ***\n" + parts[1].strip()
        else:
            test_case_raw = cleaned
            keywords_raw = ""
        
        # Remove ALL Robot Framework section headers using regex
        # Pattern matches: *** Settings ***, *** Variables ***, *** Test Cases ***
        section_header_pattern = r'\*\*\*\s+(Settings|Variables|Test Cases)\s+\*\*\*\s*\n?'
        
        test_case = re.sub(section_header_pattern, '', test_case_raw, flags=re.IGNORECASE).strip()
        
        # Clean keywords section (remove unwanted headers but keep *** Keywords ***)
        if keywords_raw:
            keywords = re.sub(section_header_pattern, '', keywords_raw, flags=re.IGNORECASE).strip()
            # Ensure Keywords header is present
            if not keywords.startswith("*** Keywords ***"):
                keywords = "*** Keywords ***\n" + keywords
        else:
            keywords = ""
        
        return {
            "test_case": test_case,
            "keywords": keywords
        }
    
    def _fallback_test_case(self, tactic: dict) -> dict:
        """Generate a minimal fallback test case"""
        
        tactic_name = tactic['tactic_name'].replace(' ', '_').replace('-', '_')
        
        test_case = f"""{tactic_name}
    [Documentation]    {tactic['objective']}
    [Tags]    {tactic.get('mitre_id', 'CUSTOM')}
    
    Log To Console    \\n[{tactic['tactic_name'].upper()}] Starting...
    
    # DEV: Implementation needed for this tactic
    # Actions required:
"""
        
        for idx, action in enumerate(tactic['actions'], 1):
            test_case += f"    # {idx}. {action['action_type']} - {action['command_or_description'][:60]}...\n"
        
        test_case += f"""    
    Log To Console    ⚠️  Tactic not fully implemented - requires manual completion
    Log It    ${{LOG_FILENAME}}    {tactic['tactic_name']} placeholder    machine=${{EMPTY}}    tid={tactic.get('mitre_id', 'CUSTOM')}    ioc=${{EMPTY}}
"""
        
        return {
            "test_case": test_case,
            "keywords": ""
        }


def test_phase3_testcase_generator():
    """Test Phase 3: Test Case Generation"""
    
    print("=" * 70)
    print("PHASE 3: TEST CASE GENERATION")
    print("=" * 70)
    
    # Read Phase 1 output (tactical breakdown)
    phase1_file = Path("robograph_p1_output.json")
    if not phase1_file.exists():
        print(f"\n❌ Error: {phase1_file} not found")
        return False
    
    # Read Phase 2 output (library analysis)
    phase2_file = Path("robograph_p2_output.json")
    if not phase2_file.exists():
        print(f"\n❌ Error: {phase2_file} not found")
        return False
    
    tactical_breakdown = json.loads(phase1_file.read_text(encoding='utf-8'))
    phase2_data = json.loads(phase2_file.read_text(encoding='utf-8'))
    
    library_mapping = phase2_data['library_mapping']
    variables_dict = phase2_data['variables_dict']
    settings_section = phase2_data['settings_section']
    variables_section = phase2_data['variables_section']
    
    print(f"\n📄 Loaded tactical breakdown: {len(tactical_breakdown['tactics'])} tactics")
    print(f"📄 Loaded library mapping: {len(library_mapping['required_libraries'])} libraries")
    print(f"📄 Loaded variables: {len(variables_dict)} variables")
    
    try:
        # Initialize generator
        generator = TacticTestCaseGenerator()
        
        # Generate all test cases
        result = generator.generate_all_test_cases(
            tactical_breakdown=tactical_breakdown,
            library_mapping=library_mapping,
            variables_dict=variables_dict
        )
        
        # ============================================================
        # CORRECTED ASSEMBLY ORDER
        # ============================================================
        print(f"\n📝 Assembling complete Robot Framework script...")
        
        # 1. Settings
        final_script = settings_section + "\n"
        
        # 2. Variables
        final_script += variables_section + "\n"
        
        # 3. Keywords (BEFORE Test Cases!)
        all_keywords = [kw for kw in result['keywords'] if kw]
        if all_keywords:
            final_script += "*** Keywords ***\n"
            for keywords_section in all_keywords:
                # Remove duplicate *** Keywords *** headers
                kw_clean = keywords_section.replace("*** Keywords ***", "").strip()
                if kw_clean:  # Only add if there's actual content
                    final_script += kw_clean + "\n\n"
        
        # 4. Test Cases (AFTER Keywords!)
        final_script += "*** Test Cases ***\n"
        for test_case in result['test_cases']:
            final_script += test_case + "\n\n"
        
        # Print preview
        print(f"\n--- Generated Robot Framework Script Preview ---")
        lines = final_script.split('\n')
        print('\n'.join(lines[:50]))
        if len(lines) > 50:
            print(f"\n... ({len(lines) - 50} more lines) ...")
        print("---")
        
        # Save final script
        output_file = Path("generated_exploit.robot")
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(final_script)
        
        print(f"\n💾 Complete Robot Framework script saved to: {output_file}")
        
        # Save phase 3 data
        phase3_data = {
            "test_cases": result['test_cases'],
            "keywords": result['keywords'],
            "complete_script": final_script
        }
        
        phase3_file = Path("phase3_output.json")
        with open(phase3_file, 'w', encoding='utf-8') as f:
            json.dump(phase3_data, f, indent=2, ensure_ascii=False)
        
        print(f"💾 Phase 3 data saved to: {phase3_file}")
        
        # Generate statistics
        print(f"\n📊 Generation Statistics:")
        print(f"   Test cases: {len(result['test_cases'])}")
        print(f"   Keywords sections: {len([k for k in result['keywords'] if k])}")
        print(f"   Total lines: {len(final_script.split(chr(10)))}")
        print(f"   Script size: {len(final_script)} characters")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_phase3_testcase_generator()
    exit(0 if success else 1)