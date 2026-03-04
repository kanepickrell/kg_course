#!/usr/bin/env python3
"""
ADAPTIVE MAKER - Meta-Cognitive Document Classification
TWO-MODEL ARCHITECTURE: Large model for meta-reasoning, small model for verification
FULLY DOMAIN-AGNOSTIC: No hardcoded domain logic

Architecture:
- Phase 0: Meta-LLM (LARGE MODEL) generates document-specific probes
- Phase B: Execute adaptive probes (SMALL MODEL) with 3x voting
- Phase C: Meta-LLM (LARGE MODEL) interprets its own probe results
- Phase D: Final synthesis

Test with:
    python maker_model.py document.txt
    python maker_model.py document.pdf
"""

from dataclasses import dataclass, asdict, field
from typing import List, Dict, Any, Optional
import re
import hashlib
import asyncio
import json
import sys
import os

# Single Ollama client
from ollama import Client
ollama_client = Client(host="http://10.10.80.99:4001")

# Two-model configuration: Large for meta-reasoning, small for verification
META_MODEL = "gpt-oss:120b"
PROBE_MODEL = "gemma3:27b-it-qat"


# =====================================================================
# 0. DATA STRUCTURES
# =====================================================================

@dataclass
class NormalizedInput:
    raw_text: str
    container_type: str
    filename: Optional[str] = None
    url: Optional[str] = None
    metadata_block: Dict[str, Any] = None
    headings: List[str] = None
    paragraphs: List[str] = None
    tables: List[str] = None
    code_blocks: List[str] = None
    lists: List[str] = None
    embedded_urls: List[str] = None
    embedded_dates: List[str] = None
    author_like: List[str] = None
    title_like: List[str] = None
    corrupt_flags: List[str] = None
    stats: Dict[str, Any] = None
    semantic_chunks: List[str] = None


@dataclass
class ProbeResult:
    """Single probe result after voting"""
    probe_name: str
    value: Any  # bool or float
    votes: List[Any]
    agreement: float


@dataclass
class DeterministicSignals:
    """Computed signals from meta-aggregation"""
    artifact_type: str
    artifact_confidence: float
    themes: List[str]
    safety_flags: List[str]
    reasoning: str
    generated_probes: List[str]


@dataclass
class StandardizedArtifact:
    title: str
    description: str
    artifact_type: str
    canonical_theme: str
    themes: List[str]
    purpose: str
    categories: List[str]
    tags: List[str]
    safety_flags: List[str]
    source_url: Optional[str]
    source_filename: Optional[str]
    container_type: str
    author: Optional[str]
    created_at: Optional[str]
    confidence: float
    normalization_notes: List[str]
    probe_results: Dict[str, ProbeResult] = field(default_factory=dict)
    deterministic_signals: Optional[DeterministicSignals] = None


# =====================================================================
# 1. PHASE A - DETERMINISTIC NORMALIZATION (NO LLM)
# =====================================================================

def _extract_pdf_text(raw_bytes: bytes) -> str:
    """
    Extract text from PDF bytes using pdfminer.six.

    - Expects exact PDF bytes (no prior re-encoding).
    - Falls back to UTF-8 decode if extraction fails or returns empty.
    """
    from io import BytesIO
    from pdfminer.high_level import extract_text

    try:
        bio = BytesIO(raw_bytes)
        text = extract_text(bio)

        if text and text.strip():
            return text

        print("pdfminer returned empty text; falling back to UTF-8 decode.")
        return raw_bytes.decode("utf-8", errors="replace")

    except Exception as e:
        print(f"pdfminer extraction error: {e}")
        return raw_bytes.decode("utf-8", errors="replace")


def _chunk_text(text: str, max_tokens: int = 512) -> List[str]:
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks = []
    current = []
    length = 0

    for p in paras:
        p_len = len(p.split())
        if length + p_len > max_tokens and current:
            chunks.append(" ".join(current))
            current = [p]
            length = p_len
        else:
            current.append(p)
            length += p_len

    if current:
        chunks.append(" ".join(current))

    return chunks


def _compute_stats(text: str) -> Dict[str, Any]:
    tokens = text.split()
    length = len(tokens)
    unique = len(set(tokens))
    return {
        "token_count": length,
        "unique_token_count": unique,
        "type_token_ratio": unique / length if length > 0 else 0.0,
        "char_count": len(text),
        "line_count": len(text.splitlines()),
        "hash": hashlib.sha256(text.encode("utf-8")).hexdigest()
    }


def normalize_input(
    raw_bytes: bytes,
    filename: Optional[str] = None,
) -> NormalizedInput:
    """
    Phase A: deterministic normalization with PDF support.

    IMPORTANT:
    - raw_bytes must be the true bytes of the source file (no intermediate encoding).
    - PDF detection is based on filename extension and file signature.
    """
    container_type: str
    text: str

    # Detect PDF by filename or magic header
    is_pdf = False
    if filename and filename.lower().endswith(".pdf"):
        is_pdf = True
    elif raw_bytes.startswith(b"%PDF"):
        is_pdf = True

    if is_pdf:
        container_type = "pdf"
        text = _extract_pdf_text(raw_bytes)
    else:
        container_type = "txt"
        # For non-PDF content, we assume UTF-8 or replace invalid bytes
        text = raw_bytes.decode("utf-8", errors="replace")

    # Normalize newline conventions
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    stats = _compute_stats(text)
    semantic_chunks = _chunk_text(text, max_tokens=512)

    # Very light structure detection; can be expanded later
    title_like = [text.strip().splitlines()[0][:100]] if text.strip() else []

    return NormalizedInput(
        raw_text=text,
        container_type=container_type,
        filename=filename,
        url=None,
        metadata_block={},
        headings=[],
        paragraphs=[],
        tables=[],
        code_blocks=[],
        lists=[],
        embedded_urls=[],
        embedded_dates=[],
        author_like=[],
        title_like=title_like,
        corrupt_flags=[],
        stats=stats,
        semantic_chunks=semantic_chunks,
    )


# =====================================================================
# 2. PHASE 0 - META-PROBE GENERATION (LARGE MODEL)
# =====================================================================

async def generate_adaptive_probes(
    normalized: NormalizedInput,
    max_probes: int = 25
) -> List[tuple]:
    """
    Meta-LLM call: analyze document and propose relevant probes.
    Uses LARGE MODEL for deep reasoning.
    DOMAIN-AGNOSTIC: Works for any document type.
    """

    text_sample = "\n\n".join(normalized.semantic_chunks[:3])

    prompt = f"""You are a document analysis expert. Analyze this document excerpt and generate a list of atomic binary questions (probes) that would help classify it.

Document excerpt (first ~1500 tokens):
\"\"\"{text_sample[:6000]}\"\"\"


Document statistics:
- Token count: {normalized.stats['token_count']}
- Title candidate: {normalized.title_like[0] if normalized.title_like else 'Unknown'}
- Container type: {normalized.container_type}

TASK: Generate {max_probes} atomic yes/no questions to determine:
1. Document TYPE (policy, runbook, playbook, report, manual, training, scenario, protocol, contract, form, etc.)
2. Document DOMAIN (cybersecurity, medical, legal, technical, military, business, administrative, etc.)
3. Document PURPOSE (instruct, document, analyze, inform, train, regulate, etc.)

Requirements for each probe:
- ATOMIC: Tests ONE specific feature
- BINARY: Answerable with yes/no only
- OBJECTIVE: No subjective judgment (avoid "good", "important", "appropriate")
- SPECIFIC: Targets this document's unique characteristics
- DISCRIMINATIVE: Helps distinguish between document types

Focus on:
- Specific terminology, acronyms, and jargon used
- Document structure (tables, walkthroughs, sections, timelines)
- Domain indicators (tools, frameworks, concepts specific to a field)
- Purpose signals (commands, analysis, instructions, regulations)
- Audience clues (who would use this?)

OUTPUT FORMAT (JSON array):
[
  {{"probe": "Contains step-by-step numbered instructions", "category": "structure"}},
  {{"probe": "References specific military doctrine or regulations", "category": "domain"}},
  {{"probe": "Includes form fields or fillable sections", "category": "type"}}
]

Generate {max_probes} probes now. Return ONLY valid JSON."""

    try:
        response = ollama_client.chat(
            model=META_MODEL,
            messages=[{"role": "user", "content": prompt}]
        )

        content = response['message']['content']

        # Extract JSON
        match = re.search(r'\[.*\]', content, re.DOTALL)
        if match:
            probes_data = json.loads(match.group(0))
        else:
            probes_data = json.loads(content)

        probes = []
        for item in probes_data[:max_probes]:
            probe_text = item.get('probe', '')
            category = item.get('category', 'general')
            if probe_text:
                # Convert to snake_case identifier
                probe_id = re.sub(r'[^\w\s]', '', probe_text.lower())
                probe_id = '_'.join(probe_id.split())[:50]
                probes.append((probe_id, probe_text, category))

        return probes

    except Exception as e:
        print(f"⚠️ Probe generation failed: {e}")
        # Fallback to generic probes
        return [
            ("has_structured_sections", "Contains clearly defined sections or headings", "structure"),
            ("has_technical_terminology", "Uses domain-specific technical terminology", "domain"),
            ("has_procedural_steps", "Contains procedural or instructional steps", "purpose")
        ]


# =====================================================================
# 3. PHASE B - EXECUTE PROBES (SMALL MODEL, 3X VOTING)
# =====================================================================

async def execute_probe(
    probe_id: str,
    probe_text: str,
    normalized: NormalizedInput,
    num_votes: int = 3
) -> ProbeResult:
    """Execute a single probe with voting."""

    text_sample = "\n\n".join(normalized.semantic_chunks[:3])

    prompt = f"""Answer this YES/NO question about the document:

QUESTION: {probe_text}

DOCUMENT EXCERPT:
\"\"\"{text_sample[:3000]}\"\"\"


Answer ONLY with "yes" or "no". No explanation needed."""

    votes = []
    for _ in range(num_votes):
        try:
            response = ollama_client.chat(
                model=PROBE_MODEL,
                messages=[{"role": "user", "content": prompt}]
            )

            answer = response['message']['content'].strip().lower()
            vote = 'yes' in answer or 'true' in answer
            votes.append(vote)

        except Exception as e:
            print(f"⚠️ Vote failed for probe '{probe_id}': {e}")
            votes.append(False)

    # Calculate agreement
    true_votes = sum(votes)
    agreement = true_votes / len(votes) if votes else 0.0
    final_value = true_votes >= (len(votes) / 2)

    return ProbeResult(
        probe_name=probe_id,
        value=final_value,
        votes=votes,
        agreement=agreement
    )


async def execute_all_probes(
    probes: List[tuple],
    normalized: NormalizedInput
) -> Dict[str, ProbeResult]:
    """Execute all probes in parallel with voting."""

    print(f"  🔍 Executing {len(probes)} probes with 3x voting...")

    tasks = [
        execute_probe(probe_id, probe_text, normalized)
        for probe_id, probe_text, _ in probes
    ]

    results = await asyncio.gather(*tasks)

    return {result.probe_name: result for result in results}


# =====================================================================
# 4. PHASE C - META-AGGREGATION (LARGE MODEL)
# =====================================================================

async def aggregate_probe_results(
    normalized: NormalizedInput,
    probe_results: Dict[str, ProbeResult],
    original_probes: List[tuple]
) -> DeterministicSignals:
    """Meta-LLM interprets its own probe results."""

    # Format probe results for LLM
    results_text = []
    for probe_id, probe_text, category in original_probes:
        result = probe_results.get(probe_id)
        if result and result.value:
            agreement_pct = int(result.agreement * 100)
            results_text.append(f"✓ [{category}] {probe_text} ({agreement_pct}% agreement)")

    results_summary = "\n".join(results_text) if results_text else "No probes returned positive results."

    prompt = f"""Based on the probe results below, determine the document's artifact type and characteristics.

DOCUMENT INFO:
- Filename: {normalized.filename or 'Unknown'}
- Token count: {normalized.stats['token_count']}
- Container: {normalized.container_type}
- Title candidate: {normalized.title_like[0] if normalized.title_like else 'Unknown'}

PROBE RESULTS (positive findings):
{results_summary}

TASK: Analyze these results and return a JSON object with:
{{
  "artifact_type": "specific type name (e.g., 'training_scenario', 'policy_document', 'technical_runbook', 'fillable_form')",
  "confidence": 0.0-1.0 (how confident are you?),
  "themes": ["theme1", "theme2", "theme3"],
  "reasoning": "1-2 sentence explanation of why this type fits",
  "safety_flags": ["flag1 if concerning content detected"]
}}

Return ONLY valid JSON."""

    try:
        response = ollama_client.chat(
            model=META_MODEL,
            messages=[{"role": "user", "content": prompt}]
        )

        content = response['message']['content']

        # Extract JSON
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            data = json.loads(match.group(0))
        else:
            data = json.loads(content)

        return DeterministicSignals(
            artifact_type=data.get('artifact_type', 'unknown_document'),
            artifact_confidence=float(data.get('confidence', 0.5)),
            themes=data.get('themes', [])[:5],
            safety_flags=data.get('safety_flags', []),
            reasoning=data.get('reasoning', 'Unable to determine reasoning'),
            generated_probes=[probe_text for _, probe_text, _ in original_probes]
        )

    except Exception as e:
        print(f"⚠️ Aggregation failed: {e}")
        return DeterministicSignals(
            artifact_type="unknown_document",
            artifact_confidence=0.3,
            themes=["unclassified"],
            safety_flags=[],
            reasoning="Classification failed due to processing error",
            generated_probes=[]
        )


# =====================================================================
# 5. PHASE D - FINAL SYNTHESIS
# =====================================================================

async def synthesize_final_artifact(
    normalized: NormalizedInput,
    probe_results: Dict[str, ProbeResult],
    signals: DeterministicSignals
) -> StandardizedArtifact:
    """Generate final standardized artifact."""

    # Extract title
    title = normalized.title_like[0] if normalized.title_like else normalized.filename or "Untitled Document"

    # Create description
    description = f"This artifact serves as {signals.artifact_type}."

    # Generate tags
    tags = []
    tags.append(signals.artifact_type.replace('_', '-'))
    tags.extend([theme.replace(' ', '-').lower() for theme in signals.themes[:3]])

    # Add probe-based tags
    for probe_id, result in probe_results.items():
        if result.value and result.agreement >= 0.8:
            tag = probe_id.replace('_', '-')[:30]
            if tag not in tags:
                tags.append(tag)

    tags = list(set(tags))[:10]

    return StandardizedArtifact(
        title=title[:200],
        description=description,
        artifact_type=signals.artifact_type,
        canonical_theme=signals.themes[0] if signals.themes else "general",
        themes=signals.themes,
        purpose=f"This artifact serves as {signals.artifact_type}.",
        categories=[signals.themes[0]] if signals.themes else ["uncategorized"],
        tags=tags,
        safety_flags=signals.safety_flags,
        source_url=normalized.url,
        source_filename=normalized.filename,
        container_type=normalized.container_type,
        author=None,
        created_at=None,
        confidence=signals.artifact_confidence,
        normalization_notes=[],
        probe_results=probe_results,
        deterministic_signals=signals
    )


# =====================================================================
# 6. MAIN PIPELINE
# =====================================================================

async def adaptive_maker_pipeline(
    raw_bytes: bytes,
    filename: Optional[str] = None
) -> dict:
    """
    Complete adaptive maker pipeline.

    Args:
        raw_bytes: Raw file bytes (text or PDF)
        filename: Optional filename for context

    Returns:
        dict with 'status', 'artifact', 'probe_results', 'aggregation_result'
    """

    print(f"\n{'='*60}")
    print(f"📄 Processing: {filename or 'unnamed document'}")
    print(f"{'='*60}")

    # Phase A: Normalize
    print("\n🔧 Phase A: Normalizing input...")
    normalized = normalize_input(raw_bytes, filename)
    print(f"  ✓ Extracted {normalized.stats['token_count']} tokens")
    print(f"  ✓ Container type: {normalized.container_type}")

    # Phase 0: Generate probes
    print("\n🧠 Phase 0: Generating adaptive probes...")
    probes = await generate_adaptive_probes(normalized, max_probes=25)
    print(f"  ✓ Generated {len(probes)} domain-specific probes")

    # Phase B: Execute probes
    print("\n⚡ Phase B: Executing probes...")
    probe_results = await execute_all_probes(probes, normalized)
    positive_count = sum(1 for r in probe_results.values() if r.value)
    print(f"  ✓ Completed {len(probe_results)} probes ({positive_count} positive)")

    # Phase C: Aggregate
    print("\n🎯 Phase C: Aggregating results...")
    aggregation_result = await aggregate_probe_results(normalized, probe_results, probes)
    print(f"  ✓ Type: {aggregation_result.artifact_type}")
    print(f"  ✓ Confidence: {aggregation_result.artifact_confidence:.2%}")

    # Phase D: Synthesize
    print("\n✨ Phase D: Synthesizing final artifact...")
    final_artifact = await synthesize_final_artifact(normalized, probe_results, aggregation_result)

    print(f"\n{'='*60}")
    print(f"✅ CLASSIFICATION COMPLETE")
    print(f"{'='*60}")
    print(f"  📄 Title: {final_artifact.title}")
    print(f"  🏷️  Type: {final_artifact.artifact_type}")
    print(f"  🎯 Confidence: {final_artifact.confidence:.2%}")
    print(f"  🏷️  Themes: {', '.join(final_artifact.themes)}")
    print(f"  ⚠️  Safety: {', '.join(final_artifact.safety_flags) if final_artifact.safety_flags else 'None'}")

    return {
        'status': 'completed',
        'artifact': asdict(final_artifact),
        'probe_results': {name: asdict(result) for name, result in probe_results.items()},
        'aggregation_result': asdict(aggregation_result),
    }


# =====================================================================
# 7. MAIN TEST HARNESS
# =====================================================================

async def main():
    """
    Main test function - provide a file path as command line argument.

    Usage:
        python maker_model.py path/to/document.txt
        python maker_model.py path/to/document.pdf
    """

    print("\n" + "="*60)
    print("ADAPTIVE MAKER - Meta-Cognitive Document Classification")
    print("TWO-MODEL ARCHITECTURE | FULLY DOMAIN-AGNOSTIC")
    print("="*60)

    # Get file path from command line
    if len(sys.argv) < 2:
        print("\n❌ ERROR: No file provided")
        print("Usage: python maker_model.py <file_path>")
        print("Example: python maker_model.py document.txt")
        print("         python maker_model.py document.pdf")
        return

    file_path = sys.argv[1]

    if not os.path.exists(file_path):
        print(f"\n❌ ERROR: File not found: {file_path}")
        return

    # Read file
    with open(file_path, 'rb') as f:
        raw_bytes = f.read()

    filename = os.path.basename(file_path)

    # Test Ollama connection
    try:
        ollama_client.list()
        print(f"✓ Connected to Ollama at http://10.10.80.99:4001")
        print(f"✓ Meta-model (probe generation & aggregation): {META_MODEL}")
        print(f"✓ Probe-model (verification): {PROBE_MODEL}")
    except Exception as e:
        print(f"\n❌ ERROR: Could not connect to Ollama: {e}")
        print("Make sure Ollama is running and accessible")
        return

    # Run pipeline
    try:
        result = await adaptive_maker_pipeline(
            raw_bytes=raw_bytes,
            filename=filename
        )

        # Save results
        output_file = f"{filename}.adaptive_maker_result.json"
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2)

        print(f"\n💾 Full results saved to: {output_file}")

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
