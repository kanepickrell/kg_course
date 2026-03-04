import ollama
from datetime import datetime
import time
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import re
from collections import Counter

# Configuration
OLLAMA_HOST = "http://10.10.80.99:4001"
LARGE_MODEL = "gpt-oss:120b"
SMALL_MODEL = "gpt-oss:120b"  # Can switch to smaller model later for speed

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def normalize_text(s: str) -> str:
    """Normalize Unicode punctuation to ASCII"""
    if not s:
        return s
    return (s.replace(""", '"').replace(""", '"')
             .replace("'", "'").replace("'", "'")
             .replace("\u00a0", " "))  # non-breaking space

def extract_all_ips(text: str) -> List[str]:
    """Extract all valid IPv4 addresses from text"""
    ip_pattern = r'\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b'
    potential_ips = re.findall(ip_pattern, text)
    
    valid_ips = []
    for ip in potential_ips:
        try:
            octets = [int(x) for x in ip.split('.')]
            if all(0 <= o <= 255 for o in octets):
                valid_ips.append(ip)
        except:
            continue
    
    return sorted(list(set(valid_ips)))

def extract_all_credentials(text: str) -> List[Dict[str, str]]:
    """Extract all potential credentials from text"""
    credentials = []
    seen = set()
    
    # Pattern 1: WMIC style /user:"username" /password:"password" (handle curly quotes)
    wmic_pattern = r'/user:\s*["\u201c\u201d\']([^"\u201c\u201d\']+)["\u201c\u201d\'].*?/password:\s*["\u201c\u201d\']([^"\u201c\u201d\']+)["\u201c\u201d\']'
    for match in re.finditer(wmic_pattern, text, re.IGNORECASE | re.DOTALL):
        username = match.group(1).strip()
        password = match.group(2).strip()
        key = f"{username}:{password}"
        if key not in seen and username and password:
            credentials.append({
                "username": username,
                "password": password,
                "type": "wmic",
                "source": "regex"
            })
            seen.add(key)
    
    # Pattern 2: SSH style username@host
    ssh_pattern = r'ssh\s+(?:-p\s+\d+\s+)?([a-zA-Z0-9._-]+)@'
    for match in re.finditer(ssh_pattern, text, re.IGNORECASE):
        username = match.group(1).strip()
        key = f"{username}:ssh"
        if key not in seen and username:
            credentials.append({
                "username": username,
                "password": None,
                "type": "ssh",
                "source": "regex"
            })
            seen.add(key)
    
    # Pattern 3: PowerShell -SamAccountName (AD user creation)
    ps_user_pattern = r'-SamAccountName\s+["\u201c\u201d\']([^"\u201c\u201d\']+)["\u201c\u201d\']'
    ps_pass_pattern = r'ConvertTo-SecureString\s+["\u201c\u201d\']([^"\u201c\u201d\']+)["\u201c\u201d\']'
    
    ps_users = re.findall(ps_user_pattern, text, re.IGNORECASE)
    ps_passes = re.findall(ps_pass_pattern, text, re.IGNORECASE)
    
    # Match them up (simple positional matching)
    for i, username in enumerate(ps_users):
        username = username.strip()
        password = ps_passes[i].strip() if i < len(ps_passes) else None
        key = f"{username}:{password}"
        if key not in seen and username:
            credentials.append({
                "username": username,
                "password": password,
                "type": "powershell",
                "source": "regex"
            })
            seen.add(key)
    
    # Pattern 4: Email addresses
    email_pattern = r'\b([a-zA-Z0-9._%+-]+@[a-zA-Z][a-zA-Z0-9.-]*\.[a-zA-Z]{2,})\b'
    for match in re.finditer(email_pattern, text, re.IGNORECASE):
        email = match.group(1)
        key = f"email:{email}"
        if key not in seen:
            credentials.append({
                "username": email,
                "password": None,
                "type": "email",
                "source": "regex"
            })
            seen.add(key)
    
    return credentials

# ============================================================================
# AGENT 1: META-NARRATIVE AGENT
# ============================================================================

class MetaNarrativeAgent:
    """
    Agent 1: Meta-Narrative Agent
    - Provides 1-sentence summary of document
    - Lists all IP addresses found (regex)
    - Lists all credentials found (regex)
    """
    
    def __init__(self, host=OLLAMA_HOST, model=LARGE_MODEL):
        self.client = ollama.Client(host=host)
        self.model = model
    
    def analyze_document(self, document_text: str) -> Dict:
        """
        Analyze document and return:
        1. One-sentence summary
        2. All IP addresses (regex)
        3. All credentials (regex)
        """
        
        print("=" * 80)
        print("META-NARRATIVE AGENT: Document Analysis")
        print("=" * 80)
        
        start_time = time.time()
        
        # Normalize text
        normalized_text = normalize_text(document_text)
        
        # Extract IPs and credentials deterministically
        print("\n🔍 Extracting IPs and credentials (regex)...")
        ip_addresses = extract_all_ips(normalized_text)
        credentials = extract_all_credentials(normalized_text)
        
        print(f"   ✓ Found {len(ip_addresses)} IP addresses")
        print(f"   ✓ Found {len(credentials)} credentials")
        
        # Generate meta-narrative summary
        print("\n🧠 Generating meta-narrative summary...")
        summary = self._generate_summary(document_text, len(ip_addresses), len(credentials))
        
        elapsed_time = time.time() - start_time
        
        result = {
            "meta_narrative": summary,
            "ip_addresses": ip_addresses,
            "credentials": credentials,
            "statistics": {
                "total_ips": len(ip_addresses),
                "total_credentials": len(credentials),
                "document_length_chars": len(document_text),
                "document_length_lines": len(document_text.split('\n')),
                "processing_time_seconds": round(elapsed_time, 2)
            }
        }
        
        print(f"\n✅ Analysis complete in {elapsed_time:.2f}s")
        
        return result
    
    def _generate_summary(self, document_text: str, num_ips: int, num_creds: int) -> str:
        """Generate one-sentence summary using large model"""
        
        # Truncate document if too long (keep first and last parts)
        max_chars = 50000
        if len(document_text) > max_chars:
            keep = max_chars // 2
            truncated = document_text[:keep] + "\n\n[... middle content truncated ...]\n\n" + document_text[-keep:]
        else:
            truncated = document_text
        
        prompt = f"""Analyze this cybersecurity document and provide a single, comprehensive sentence that describes what it is about.

The document contains {num_ips} IP addresses and {num_creds} credentials.

Focus on:
- What type of document is this? (execution plan, report, procedure, etc.)
- What is the primary objective or scenario?
- What are the key actions or phases?

Return ONLY one sentence. No preamble, no additional explanation.

Document:
{truncated}"""

        try:
            response = self.client.chat(
                model=self.model,
                messages=[
                    {
                        "role": "system", 
                        "content": "You provide concise, accurate summaries of technical documents in exactly one sentence."
                    },
                    {
                        "role": "user", 
                        "content": prompt
                    }
                ]
            )
            
            summary = response['message']['content'].strip()
            
            # Clean up any extra formatting
            summary = summary.strip('"\'')
            
            # Ensure it's one sentence (take first sentence if multiple)
            if '.' in summary:
                summary = summary.split('.')[0] + '.'
            
            return summary
            
        except Exception as e:
            print(f"      ⚠️  Summary generation failed: {e}")
            return f"A technical document containing {num_ips} IP addresses and {num_creds} credentials."


# ============================================================================
# AGENT 2: SEGMENTS AGENT
# ============================================================================

class SegmentsAgent:
    """
    Agent 2: Segments Agent
    - Uses meta-narrative context to intelligently identify segment boundaries
    - Returns segments with exact raw text extracted from original document
    """
    
    def __init__(self, host=OLLAMA_HOST, model=LARGE_MODEL):
        self.client = ollama.Client(host=host)
        self.model = model
    
    def segment_document(self, document_text: str, meta_narrative: str) -> Dict:
        """
        Identify logical segment boundaries and extract raw text
        Returns: Dict with segments array containing {id, title, start_line, end_line, content, rationale}
        """
        
        print("\n" + "=" * 80)
        print("SEGMENTS AGENT: Intelligent Document Segmentation")
        print("=" * 80)
        
        start_time = time.time()
        
        print(f"\n📋 Context: {meta_narrative}")
        print("\n🔪 Identifying segment boundaries...")
        
        segments = self._generate_segments(document_text, meta_narrative)
        
        elapsed_time = time.time() - start_time
        
        result = {
            "segments": segments,
            "statistics": {
                "total_segments": len(segments),
                "processing_time_seconds": round(elapsed_time, 2)
            }
        }
        
        print(f"\n✅ Segmentation complete in {elapsed_time:.2f}s")
        print(f"   Created {len(segments)} segments")
        
        return result
    
    def _generate_segments(self, document_text: str, meta_narrative: str) -> List[Dict]:
        """Use LLM to identify segment boundaries, then extract exact raw text"""
        
        # Split document into lines for line-based extraction
        lines = document_text.split('\n')
        
        # Create line-numbered version for LLM
        numbered_lines = '\n'.join(f"{i+1:4d}: {line}" for i, line in enumerate(lines))
        
        prompt = f"""You are analyzing a document to identify logical segment boundaries.

CONTEXT (Meta-Narrative):
{meta_narrative}

The document has {len(lines)} lines total.

Analyze the document structure and identify where each logical segment begins and ends using LINE NUMBERS.

Consider:
- Does the document have clear phases or stages?
- Are there distinct activities or operations?
- Are there logical boundaries between sections?
- What groupings would make sense for analyzing this type of document?

Return ONLY valid JSON with this exact structure (no markdown, no code blocks):
{{
  "segmentation_strategy": "brief explanation of how you chose to segment",
  "segments": [
    {{
      "id": 1,
      "title": "brief descriptive title",
      "start_line": 1,
      "end_line": 15,
      "rationale": "why this is a logical segment"
    }}
  ]
}}

LINE-NUMBERED DOCUMENT:
{numbered_lines}"""

        try:
            response = self.client.chat(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You identify document segment boundaries by analyzing structure and providing line numbers. You always return valid JSON."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )
            
            result_text = response['message']['content'].strip()
            
            # Clean up markdown code blocks if present
            if result_text.startswith('```'):
                result_text = '\n'.join(result_text.split('\n')[1:])
            if result_text.endswith('```'):
                result_text = '\n'.join(result_text.split('\n')[:-1])
            result_text = result_text.strip()
            
            # Parse JSON
            parsed = json.loads(result_text)
            
            # Extract strategy
            strategy = parsed.get('segmentation_strategy', 'No strategy provided')
            
            # Now extract ACTUAL raw content using line numbers
            segments = []
            for seg in parsed.get('segments', []):
                seg_id = seg.get('id', 0)
                title = seg.get('title', 'Untitled')
                start_line = seg.get('start_line', 1)
                end_line = seg.get('end_line', len(lines))
                rationale = seg.get('rationale', 'No rationale provided')
                
                # Convert to 0-indexed and extract raw text
                start_idx = max(0, start_line - 1)
                end_idx = min(len(lines), end_line)
                
                # Extract EXACT raw text from original document
                raw_content = '\n'.join(lines[start_idx:end_idx])
                
                segment_data = {
                    "id": seg_id,
                    "title": title,
                    "start_line": start_line,
                    "end_line": end_line,
                    "content": raw_content,
                    "rationale": rationale
                }
                
                # Add strategy to first segment only
                if seg_id == 1:
                    segment_data['segmentation_strategy'] = strategy
                
                segments.append(segment_data)
            
            return segments
            
        except json.JSONDecodeError as e:
            print(f"      ⚠️  JSON parsing failed: {e}")
            print(f"      Raw response preview: {result_text[:500]}...")
            return [{
                "id": 1,
                "title": "Complete Document",
                "start_line": 1,
                "end_line": len(lines),
                "content": document_text,
                "rationale": "Segmentation failed, using entire document",
                "segmentation_strategy": "Fallback strategy due to parsing error"
            }]
        except Exception as e:
            print(f"      ⚠️  Segmentation failed: {e}")
            import traceback
            traceback.print_exc()
            return [{
                "id": 1,
                "title": "Complete Document",
                "start_line": 1,
                "end_line": len(lines),
                "content": document_text,
                "rationale": "Segmentation failed, using entire document",
                "segmentation_strategy": "Fallback strategy due to error"
            }]


# ============================================================================
# AGENT 3: VALIDATION AGENT (IPs and Credentials)
# ============================================================================

class ValidationAgent:
    """
    Agent 3: Validation Agent
    - Independently extracts IPs/credentials from each segment (no knowledge of regex results)
    - Provides confidence scores for each finding
    """
    
    def __init__(self, host=OLLAMA_HOST, model=SMALL_MODEL):
        self.client = ollama.Client(host=host)
        self.model = model
    
    def validate_segment(self, segment: Dict) -> Dict:
        """
        Independently extract IPs and credentials from a segment
        No knowledge of regex results - true blind validation
        """
        
        segment_id = segment['id']
        segment_title = segment['title']
        segment_content = segment['content']
        
        print(f"\n   🔍 Validating Segment #{segment_id}: {segment_title}")
        
        start_time = time.time()
        
        # LLM extraction (blind - no knowledge of regex results)
        extracted = self._extract_from_segment(segment_content, segment_id)
        
        elapsed_time = time.time() - start_time
        
        print(f"      ✓ Found {len(extracted['ip_addresses'])} IPs, {len(extracted['credentials'])} credentials ({elapsed_time:.2f}s)")
        
        return {
            "segment_id": segment_id,
            "segment_title": segment_title,
            "ip_addresses": extracted['ip_addresses'],
            "credentials": extracted['credentials'],
            "processing_time_seconds": round(elapsed_time, 2)
        }
    
    def _extract_from_segment(self, content: str, segment_id: int) -> Dict:
        """Use LLM to extract IPs and credentials independently"""
        
        prompt = f"""Extract ALL IP addresses and credentials from this text segment.

For IP addresses:
- IPv4 addresses (e.g., 192.168.1.1)
- Include ALL IPs you find

For credentials, look for ANY format:
- User/password pairs in any format (wmic, ssh, powershell, etc.)
- SSH usernames (with or without passwords)
- API keys or tokens
- Database credentials
- Natural language mentions (e.g., "login with admin/temp123")
- Email addresses used for authentication
- ANY other authentication information

For each credential, assess confidence:
- "high": Clear username/password pair with explicit context
- "medium": Username with implied password or partial information
- "low": Ambiguous or uncertain extraction

Return ONLY valid JSON (no markdown, no code blocks):
{{
  "ip_addresses": ["1.2.3.4", ...],
  "credentials": [
    {{
      "username": "...",
      "password": "..." or null,
      "type": "description of format/context",
      "confidence": "high|medium|low",
      "context": "brief explanation of where/how found"
    }}
  ]
}}

TEXT SEGMENT:
{content}"""

        try:
            response = self.client.chat(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert at extracting IP addresses and credentials from text. You always return valid JSON."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )
            
            result_text = response['message']['content'].strip()
            
            # Clean markdown if present
            if result_text.startswith('```'):
                result_text = '\n'.join(result_text.split('\n')[1:])
            if result_text.endswith('```'):
                result_text = '\n'.join(result_text.split('\n')[:-1])
            result_text = result_text.strip()
            
            # Parse JSON
            parsed = json.loads(result_text)
            
            # Add source tracking
            ips = parsed.get('ip_addresses', [])
            creds = parsed.get('credentials', [])
            
            # Mark all as LLM-sourced
            for cred in creds:
                cred['source'] = 'llm'
                cred['segment_id'] = segment_id
            
            return {
                "ip_addresses": ips,
                "credentials": creds
            }
            
        except json.JSONDecodeError as e:
            print(f"         ⚠️  JSON parsing failed: {e}")
            return {"ip_addresses": [], "credentials": []}
        except Exception as e:
            print(f"         ⚠️  Extraction failed: {e}")
            return {"ip_addresses": [], "credentials": []}


# ============================================================================
# AGENT 4: COMMAND EXTRACTION AGENT
# ============================================================================

class CommandExtractionAgent:
    """
    Agent 4: Command Extraction Agent
    - Extracts command sequences with tool context
    - Preserves exact syntax (no paraphrasing)
    """
    
    def __init__(self, host=OLLAMA_HOST, model=SMALL_MODEL):
        self.client = ollama.Client(host=host)
        self.model = model
    
    def extract_commands(self, segment: Dict) -> Dict:
        """Extract commands from segment"""
        
        segment_id = segment['id']
        segment_title = segment['title']
        segment_content = segment['content']
        
        print(f"\n   📜 Extracting commands from Segment #{segment_id}: {segment_title}")
        
        start_time = time.time()
        
        commands = self._extract_commands_from_segment(segment_content, segment_id)
        
        elapsed_time = time.time() - start_time
        
        print(f"      ✓ Found {len(commands)} commands ({elapsed_time:.2f}s)")
        
        return {
            "segment_id": segment_id,
            "segment_title": segment_title,
            "commands": commands,
            "processing_time_seconds": round(elapsed_time, 2)
        }
    
    def _extract_commands_from_segment(self, content: str, segment_id: int) -> List[Dict]:
        """Use LLM to extract commands"""
        
        prompt = f"""Extract ALL commands from this text segment.

For each command, identify:
- The exact command text (preserve syntax exactly)
- The tool/context (metasploit, cobalt strike, sliver, powershell, bash, ssh, etc.)
- Any targets (IPs, hostnames, users)
- Any parameters or flags

Return ONLY valid JSON (no markdown, no code blocks):
{{
  "commands": [
    {{
      "command": "exact command text",
      "tool_context": "which tool/shell is this command for",
      "target": "IP or hostname if applicable",
      "parameters": {{"key": "value"}},
      "line_number": "approximate line in segment if known"
    }}
  ]
}}

TEXT SEGMENT:
{content}"""

        try:
            response = self.client.chat(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You extract commands from technical documents with exact syntax preservation. You always return valid JSON."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )
            
            result_text = response['message']['content'].strip()
            
            # Clean markdown if present
            if result_text.startswith('```'):
                result_text = '\n'.join(result_text.split('\n')[1:])
            if result_text.endswith('```'):
                result_text = '\n'.join(result_text.split('\n')[:-1])
            result_text = result_text.strip()
            
            # Parse JSON
            parsed = json.loads(result_text)
            
            commands = parsed.get('commands', [])
            
            # Add segment context
            for cmd in commands:
                cmd['segment_id'] = segment_id
                cmd['source'] = 'llm'
            
            return commands
            
        except json.JSONDecodeError as e:
            print(f"         ⚠️  JSON parsing failed: {e}")
            return []
        except Exception as e:
            print(f"         ⚠️  Extraction failed: {e}")
            return []


# ============================================================================
# AGENT 5: TOOL DETECTION AGENT
# ============================================================================

class ToolDetectionAgent:
    """
    Agent 5: Tool Detection Agent
    - Identifies which C2/tools are used in each segment
    - Maps to library references for Robot Framework
    """
    
    def __init__(self, host=OLLAMA_HOST, model=SMALL_MODEL):
        self.client = ollama.Client(host=host)
        self.model = model
    
    def detect_tools(self, segment: Dict) -> Dict:
        """Detect tools used in segment"""
        
        segment_id = segment['id']
        segment_title = segment['title']
        segment_content = segment['content']
        
        print(f"\n   🔧 Detecting tools in Segment #{segment_id}: {segment_title}")
        
        start_time = time.time()
        
        tools = self._detect_tools_in_segment(segment_content, segment_id)
        
        elapsed_time = time.time() - start_time
        
        print(f"      ✓ Found {len(tools)} tools ({elapsed_time:.2f}s)")
        
        return {
            "segment_id": segment_id,
            "segment_title": segment_title,
            "tools": tools,
            "processing_time_seconds": round(elapsed_time, 2)
        }
    
    def _detect_tools_in_segment(self, content: str, segment_id: int) -> List[Dict]:
        """Use LLM to detect tools"""
        
        prompt = f"""Identify ALL offensive security tools, frameworks, and C2 platforms used in this text.

Look for:
- C2 Frameworks: Metasploit, Cobalt Strike, Sliver, Empire, etc.
- Offensive Tools: nmap, Responder, Mimikatz, etc.
- Scripts: PowerShell scripts, Python scripts, etc.
- Network Tools: proxychains, ssh, etc.

For each tool, identify:
- Tool name
- Category (c2_framework, recon_tool, credential_tool, network_tool, script, etc.)
- How it's being used (brief description)

Return ONLY valid JSON (no markdown, no code blocks):
{{
  "tools": [
    {{
      "name": "tool name",
      "category": "tool category",
      "usage": "brief description of how it's used",
      "confidence": "high|medium|low"
    }}
  ]
}}

TEXT SEGMENT:
{content}"""

        try:
            response = self.client.chat(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You identify offensive security tools and frameworks from technical documents. You always return valid JSON."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )
            
            result_text = response['message']['content'].strip()
            
            # Clean markdown if present
            if result_text.startswith('```'):
                result_text = '\n'.join(result_text.split('\n')[1:])
            if result_text.endswith('```'):
                result_text = '\n'.join(result_text.split('\n')[:-1])
            result_text = result_text.strip()
            
            # Parse JSON
            parsed = json.loads(result_text)
            
            tools = parsed.get('tools', [])
            
            # Add segment context
            for tool in tools:
                tool['segment_id'] = segment_id
                tool['source'] = 'llm'
            
            return tools
            
        except json.JSONDecodeError as e:
            print(f"         ⚠️  JSON parsing failed: {e}")
            return []
        except Exception as e:
            print(f"         ⚠️  Extraction failed: {e}")
            return []


# ============================================================================
# AGENT 6: FILE PATH EXTRACTION AGENT
# ============================================================================

class FilePathExtractionAgent:
    """
    Agent 6: File Path Extraction Agent
    - Extracts file paths from commands
    - Distinguishes Windows vs Linux paths
    - Identifies source vs destination paths
    """
    
    def __init__(self, host=OLLAMA_HOST, model=SMALL_MODEL):
        self.client = ollama.Client(host=host)
        self.model = model
    
    def extract_paths(self, segment: Dict) -> Dict:
        """Extract file paths from segment"""
        
        segment_id = segment['id']
        segment_title = segment['title']
        segment_content = segment['content']
        
        print(f"\n   📁 Extracting file paths from Segment #{segment_id}: {segment_title}")
        
        start_time = time.time()
        
        paths = self._extract_paths_from_segment(segment_content, segment_id)
        
        elapsed_time = time.time() - start_time
        
        total_paths = len(paths.get('windows', [])) + len(paths.get('linux', []))
        print(f"      ✓ Found {total_paths} file paths ({elapsed_time:.2f}s)")
        
        return {
            "segment_id": segment_id,
            "segment_title": segment_title,
            "paths": paths,
            "processing_time_seconds": round(elapsed_time, 2)
        }
    
    def _extract_paths_from_segment(self, content: str, segment_id: int) -> Dict:
        """Use LLM to extract file paths"""
        
        prompt = f"""Extract ALL file paths from this text segment.

For each path, identify:
- The exact path (preserve syntax including backslashes, spaces, etc.)
- Path type (windows or linux)
- Role (source, destination, executable, config, etc.)
- Associated command if known

Return ONLY valid JSON (no markdown, no code blocks):
{{
  "windows": [
    {{
      "path": "exact Windows path",
      "role": "source|destination|executable|config|etc",
      "context": "brief description"
    }}
  ],
  "linux": [
    {{
      "path": "exact Linux path",
      "role": "source|destination|executable|config|etc",
      "context": "brief description"
    }}
  ]
}}

TEXT SEGMENT:
{content}"""

        try:
            response = self.client.chat(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You extract file paths from technical documents with exact syntax preservation. You always return valid JSON."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )
            
            result_text = response['message']['content'].strip()
            
            # Clean markdown if present
            if result_text.startswith('```'):
                result_text = '\n'.join(result_text.split('\n')[1:])
            if result_text.endswith('```'):
                result_text = '\n'.join(result_text.split('\n')[:-1])
            result_text = result_text.strip()
            
            # Parse JSON
            parsed = json.loads(result_text)
            
            # Add segment context
            for path in parsed.get('windows', []):
                path['segment_id'] = segment_id
                path['source'] = 'llm'
            
            for path in parsed.get('linux', []):
                path['segment_id'] = segment_id
                path['source'] = 'llm'
            
            return {
                "windows": parsed.get('windows', []),
                "linux": parsed.get('linux', [])
            }
            
        except json.JSONDecodeError as e:
            print(f"         ⚠️  JSON parsing failed: {e}")
            return {"windows": [], "linux": []}
        except Exception as e:
            print(f"         ⚠️  Extraction failed: {e}")
            return {"windows": [], "linux": []}


# ============================================================================
# AGENT 7: NETWORK RELATIONSHIP AGENT
# ============================================================================

class NetworkRelationshipAgent:
    """
    Agent 7: Network Relationship Agent
    - Maps relationships between IPs (source -> target)
    - Identifies roles (attacker, victim, C2, pivot)
    """
    
    def __init__(self, host=OLLAMA_HOST, model=SMALL_MODEL):
        self.client = ollama.Client(host=host)
        self.model = model
    
    def extract_relationships(self, segment: Dict, known_ips: List[str]) -> Dict:
        """Extract network relationships from segment"""
        
        segment_id = segment['id']
        segment_title = segment['title']
        segment_content = segment['content']
        
        print(f"\n   🌐 Extracting network relationships from Segment #{segment_id}: {segment_title}")
        
        start_time = time.time()
        
        relationships = self._extract_relationships_from_segment(
            segment_content, 
            segment_id,
            known_ips
        )
        
        elapsed_time = time.time() - start_time
        
        print(f"      ✓ Found {len(relationships)} relationships ({elapsed_time:.2f}s)")
        
        return {
            "segment_id": segment_id,
            "segment_title": segment_title,
            "relationships": relationships,
            "processing_time_seconds": round(elapsed_time, 2)
        }
    
    def _extract_relationships_from_segment(self, content: str, segment_id: int, known_ips: List[str]) -> List[Dict]:
        """Use LLM to extract network relationships"""
        
        prompt = f"""Analyze network relationships in this text segment.

Known IP addresses in the document: {', '.join(known_ips)}

For each IP address that appears in this segment, determine:
- Role: attacker_source, target_victim, c2_server, pivot_host, etc.
- Relationships: which IPs communicate with which (source -> target)
- Protocol/method: how they communicate (ssh, wmic, http, etc.)

Return ONLY valid JSON (no markdown, no code blocks):
{{
  "ip_roles": [
    {{
      "ip": "IP address",
      "role": "attacker_source|target_victim|c2_server|pivot_host|etc",
      "confidence": "high|medium|low"
    }}
  ],
  "connections": [
    {{
      "source_ip": "IP",
      "target_ip": "IP",
      "protocol": "ssh|wmic|http|etc",
      "description": "brief description of connection"
    }}
  ]
}}

TEXT SEGMENT:
{content}"""

        try:
            response = self.client.chat(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You analyze network relationships in cybersecurity documents. You always return valid JSON."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )
            
            result_text = response['message']['content'].strip()
            
            # Clean markdown if present
            if result_text.startswith('```'):
                result_text = '\n'.join(result_text.split('\n')[1:])
            if result_text.endswith('```'):
                result_text = '\n'.join(result_text.split('\n')[:-1])
            result_text = result_text.strip()
            
            # Parse JSON
            parsed = json.loads(result_text)
            
            # Add segment context
            for role in parsed.get('ip_roles', []):
                role['segment_id'] = segment_id
                role['source'] = 'llm'
            
            for conn in parsed.get('connections', []):
                conn['segment_id'] = segment_id
                conn['source'] = 'llm'
            
            return parsed
            
        except json.JSONDecodeError as e:
            print(f"         ⚠️  JSON parsing failed: {e}")
            return {"ip_roles": [], "connections": []}
        except Exception as e:
            print(f"         ⚠️  Extraction failed: {e}")
            return {"ip_roles": [], "connections": []}


# ============================================================================
# RECONCILIATION AGENT
# ============================================================================

class ReconciliationAgent:
    """
    Reconciliation Agent
    - Merges regex (global) and LLM (per-segment) results
    - Identifies agreements, unique findings, and conflicts
    - Produces final consolidated list with provenance
    """
    
    def __init__(self):
        pass
    
    def reconcile(self, regex_results: Dict, llm_results: List[Dict]) -> Dict:
        """
        Merge regex and LLM results with provenance tracking
        
        Args:
            regex_results: Global regex extraction from meta-narrative agent
            llm_results: List of per-segment LLM extractions from validation agent
            
        Returns:
            Consolidated results with provenance
        """
        
        print("\n" + "=" * 80)
        print("RECONCILIATION AGENT: Merging Results")
        print("=" * 80)
        
        start_time = time.time()
        
        # Merge IPs
        print("\n🔗 Reconciling IP addresses...")
        ip_reconciliation = self._reconcile_ips(
            regex_results['ip_addresses'],
            llm_results
        )
        
        # Merge credentials
        print("🔗 Reconciling credentials...")
        cred_reconciliation = self._reconcile_credentials(
            regex_results['credentials'],
            llm_results
        )
        
        elapsed_time = time.time() - start_time
        
        result = {
            "ip_addresses": ip_reconciliation,
            "credentials": cred_reconciliation,
            "statistics": {
                "total_ips": len(ip_reconciliation['all_ips']),
                "total_credentials": len(cred_reconciliation['all_credentials']),
                "processing_time_seconds": round(elapsed_time, 2)
            }
        }
        
        print(f"\n✅ Reconciliation complete in {elapsed_time:.2f}s")
        
        return result
    
    def _reconcile_ips(self, regex_ips: List[str], llm_results: List[Dict]) -> Dict:
        """Reconcile IP addresses from regex and LLM"""
        
        # Collect all LLM IPs
        llm_ips = set()
        for result in llm_results:
            llm_ips.update(result['ip_addresses'])
        
        regex_set = set(regex_ips)
        llm_set = set(llm_ips)
        
        both = sorted(list(regex_set & llm_set))
        regex_only = sorted(list(regex_set - llm_set))
        llm_only = sorted(list(llm_set - regex_set))
        
        all_ips = sorted(list(regex_set | llm_set))
        
        print(f"   ✓ Total unique IPs: {len(all_ips)}")
        print(f"      • Both found (high confidence): {len(both)}")
        print(f"      • Regex only: {len(regex_only)}")
        print(f"      • LLM only: {len(llm_only)}")
        
        return {
            "all_ips": all_ips,
            "provenance": {
                "both": both,
                "regex_only": regex_only,
                "llm_only": llm_only
            }
        }
    
    def _reconcile_credentials(self, regex_creds: List[Dict], llm_results: List[Dict]) -> Dict:
        """Reconcile credentials from regex and LLM"""
        
        # Collect all LLM credentials
        llm_creds = []
        for result in llm_results:
            llm_creds.extend(result['credentials'])
        
        # Create normalized keys for comparison
        def make_key(cred):
            username = cred.get('username', '').lower().strip()
            password = cred.get('password', '')
            if password:
                password = password.strip()
            return f"{username}:{password if password else 'NOPASS'}"
        
        regex_keys = {make_key(c): c for c in regex_creds}
        llm_keys = {make_key(c): c for c in llm_creds}
        
        both_keys = set(regex_keys.keys()) & set(llm_keys.keys())
        regex_only_keys = set(regex_keys.keys()) - set(llm_keys.keys())
        llm_only_keys = set(llm_keys.keys()) - set(regex_keys.keys())
        
        # Build consolidated list
        both = [regex_keys[k] for k in sorted(both_keys)]
        regex_only = [regex_keys[k] for k in sorted(regex_only_keys)]
        llm_only = [llm_keys[k] for k in sorted(llm_only_keys)]
        
        # Mark confidence
        for c in both:
            c['confidence'] = 'high'
            c['found_by'] = 'both'
        
        for c in regex_only:
            c['confidence'] = 'high'  # Regex is deterministic
            c['found_by'] = 'regex_only'
        
        for c in llm_only:
            # Keep LLM's confidence assessment
            if 'confidence' not in c:
                c['confidence'] = 'medium'
            c['found_by'] = 'llm_only'
        
        all_credentials = both + regex_only + llm_only
        
        print(f"   ✓ Total unique credentials: {len(all_credentials)}")
        print(f"      • Both found (high confidence): {len(both)}")
        print(f"      • Regex only: {len(regex_only)}")
        print(f"      • LLM only: {len(llm_only)}")
        
        return {
            "all_credentials": all_credentials,
            "provenance": {
                "both": both,
                "regex_only": regex_only,
                "llm_only": llm_only
            }
        }


# ============================================================================
# MAIN ORCHESTRATOR
# ============================================================================

class RoboGraphDemo:
    """
    Full extraction pipeline with all agents
    """
    
    def __init__(self, host=OLLAMA_HOST):
        # Meta-reasoning agents (large model)
        self.meta_agent = MetaNarrativeAgent(host, LARGE_MODEL)
        self.segments_agent = SegmentsAgent(host, LARGE_MODEL)
        
        # Extraction agents (small model)
        self.validation_agent = ValidationAgent(host, SMALL_MODEL)
        self.command_agent = CommandExtractionAgent(host, SMALL_MODEL)
        self.tool_agent = ToolDetectionAgent(host, SMALL_MODEL)
        self.path_agent = FilePathExtractionAgent(host, SMALL_MODEL)
        self.network_agent = NetworkRelationshipAgent(host, SMALL_MODEL)
        
        # Reconciliation
        self.reconciliation_agent = ReconciliationAgent()
    
    def analyze(self, document_text: str) -> Dict:
        """Run full analysis pipeline"""
        
        # Stage 1: Meta-narrative analysis (includes regex extraction)
        meta_result = self.meta_agent.analyze_document(document_text)
        
        # Stage 2: Segment the document
        segments_result = self.segments_agent.segment_document(
            document_text, 
            meta_result['meta_narrative']
        )
        
        # Stage 3: Per-segment extraction (all agents)
        print("\n" + "=" * 80)
        print("EXTRACTION AGENTS: Per-Segment Analysis")
        print("=" * 80)
        
        validation_results = []
        command_results = []
        tool_results = []
        path_results = []
        network_results = []
        
        for segment in segments_result['segments']:
            # IP/Credential validation
            validation_results.append(
                self.validation_agent.validate_segment(segment)
            )
            
            # Command extraction
            command_results.append(
                self.command_agent.extract_commands(segment)
            )
            
            # Tool detection
            tool_results.append(
                self.tool_agent.detect_tools(segment)
            )
            
            # File path extraction
            path_results.append(
                self.path_agent.extract_paths(segment)
            )
            
            # Network relationships
            network_results.append(
                self.network_agent.extract_relationships(
                    segment,
                    meta_result['ip_addresses']
                )
            )
        
        # Stage 4: Reconciliation (IPs and credentials only for now)
        reconciliation_result = self.reconciliation_agent.reconcile(
            {
                'ip_addresses': meta_result['ip_addresses'],
                'credentials': meta_result['credentials']
            },
            validation_results
        )
        
        # Combine all results
        return {
            "meta_narrative": meta_result,
            "segments": segments_result,
            "extractions": {
                "ip_credentials": reconciliation_result,
                "commands": command_results,
                "tools": tool_results,
                "file_paths": path_results,
                "network_relationships": network_results
            }
        }


# ============================================================================
# TEST FUNCTION
# ============================================================================

def test_agents():
    """Test the full pipeline"""
    
    exec_plan_file = Path("baqt_unprocessed.txt")
    
    if not exec_plan_file.exists():
        print(f"\n❌ Error: {exec_plan_file} not found")
        return False
    
    raw_plan = exec_plan_file.read_text(encoding='utf-8')
    
    print(f"\n📄 Loaded document from: {exec_plan_file}")
    print(f"   Length: {len(raw_plan)} characters")
    print(f"   Lines: {len(raw_plan.split(chr(10)))}")
    
    try:
        parser = RoboGraphDemo()
        result = parser.analyze(raw_plan)
        
        # Print summary statistics
        print("\n" + "=" * 80)
        print("FINAL EXTRACTION SUMMARY")
        print("=" * 80)
        
        extractions = result['extractions']
        
        # IPs and Credentials
        ip_cred = extractions['ip_credentials']
        print(f"\n📡 IP ADDRESSES: {ip_cred['statistics']['total_ips']}")
        print(f"🔑 CREDENTIALS: {ip_cred['statistics']['total_credentials']}")
        
        # Commands
        total_commands = sum(len(r['commands']) for r in extractions['commands'])
        print(f"📜 COMMANDS: {total_commands}")
        
        # Tools
        total_tools = sum(len(r['tools']) for r in extractions['tools'])
        print(f"🔧 TOOLS: {total_tools}")
        
        # File Paths
        total_paths = sum(
            len(r['paths']['windows']) + len(r['paths']['linux'])
            for r in extractions['file_paths']
        )
        print(f"📁 FILE PATHS: {total_paths}")
        
        # Network Relationships
        total_relationships = sum(
            len(r['relationships'].get('connections', []))
            for r in extractions['network_relationships']
        )
        print(f"🌐 NETWORK CONNECTIONS: {total_relationships}")
        
        # Show sample commands
        print(f"\n📜 SAMPLE COMMANDS:")
        for cmd_result in extractions['commands'][:3]:  # First 3 segments
            if cmd_result['commands']:
                print(f"\n   Segment #{cmd_result['segment_id']}: {cmd_result['segment_title']}")
                for cmd in cmd_result['commands'][:2]:  # First 2 commands per segment
                    print(f"      • [{cmd.get('tool_context', 'unknown'):15}] {cmd['command'][:80]}...")
        
        # Show sample tools
        print(f"\n🔧 TOOLS DETECTED:")
        all_tools = []
        for tool_result in extractions['tools']:
            all_tools.extend(tool_result['tools'])
        
        # Deduplicate by name
        unique_tools = {tool['name']: tool for tool in all_tools}.values()
        for tool in list(unique_tools)[:10]:  # Show first 10 unique tools
            print(f"   • {tool['name']:20} [{tool['category']:15}]")
        
        # Save output
        output_file = Path("agent_output_full.json")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        print(f"\n💾 Full output saved to: {output_file}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_agents()
    exit(0 if success else 1)