"""
Neural Graph Routing - Orchestrator

Synthesizes final answer from activated agent contexts.

CRITICAL RULES:
1. Preserve activation ordering/path info in synthesis
2. Track which agents actually contributed to the answer
3. Don't dump contexts as a bag - maintain structure
4. Deduplicate while preserving unique information
"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from collections import defaultdict

from core.propagation import PropagationResult, ActivationState


@dataclass
class ContextChunk:
    """A context contribution from an agent."""
    agent_id: str
    context: str
    relevance_score: float
    depth: int  # Hop count from entry point
    path: List[str]  # How we reached this agent
    contributed: bool = False  # Set by orchestrator if used in answer


@dataclass
class SynthesisResult:
    """Result of orchestrator synthesis."""
    answer: str
    contributing_agents: List[str]  # Agents whose context made it into the answer
    context_chain: List[ContextChunk]  # Ordered contexts with contribution flags
    synthesis_prompt: str  # The prompt sent to synthesis LLM (for debugging)
    
    # Metrics
    total_contexts: int
    deduplicated_contexts: int
    contexts_used: int


class Orchestrator:
    """
    Synthesizes final answer from activated agent contexts.
    
    Maintains structural awareness - the answer should reflect
    HOW information connects, not just WHAT information was found.
    """
    
    def __init__(
        self,
        use_llm: bool = False,  # Phase 1: deterministic synthesis
        llm_model: str = "gemma2:9b",
    ):
        self.use_llm = use_llm
        self.llm_model = llm_model
    
    def synthesize(
        self,
        query: str,
        propagation_result: PropagationResult,
        agent_contexts: Dict[str, str],  # agent_id -> context emitted
    ) -> SynthesisResult:
        """
        Synthesize answer from activated contexts.
        
        Args:
            query: Original query.
            propagation_result: Full propagation data.
            agent_contexts: Contexts emitted by activated agents.
            
        Returns:
            SynthesisResult with answer and contribution tracking.
        """
        # === STEP 1: Build ordered context chain ===
        context_chain = self._build_context_chain(propagation_result, agent_contexts)
        
        # === STEP 2: Deduplicate while preserving unique info ===
        deduped_chain = self._deduplicate_contexts(context_chain)
        
        # === STEP 3: Build structured prompt ===
        synthesis_prompt = self._build_synthesis_prompt(query, deduped_chain)
        
        # === STEP 4: Generate answer ===
        if self.use_llm:
            answer = self._llm_synthesis(synthesis_prompt)
        else:
            answer = self._deterministic_synthesis(query, deduped_chain)
        
        # === STEP 5: Identify contributing agents ===
        contributing = self._identify_contributors(answer, deduped_chain)
        
        # Mark contributions in chain
        for chunk in context_chain:
            chunk.contributed = chunk.agent_id in contributing
        
        return SynthesisResult(
            answer=answer,
            contributing_agents=contributing,
            context_chain=context_chain,
            synthesis_prompt=synthesis_prompt,
            total_contexts=len(context_chain),
            deduplicated_contexts=len(deduped_chain),
            contexts_used=len(contributing),
        )
    
    def _build_context_chain(
        self,
        result: PropagationResult,
        contexts: Dict[str, str],
    ) -> List[ContextChunk]:
        """
        Build ordered context chain from propagation result.
        Orders by: depth (entry first), then relevance score.
        """
        chain = []
        
        for agent_id in result.activated_agents:
            if agent_id not in contexts or not contexts[agent_id]:
                continue
            
            record = result.activation_records.get(agent_id)
            if not record:
                continue
            
            # Get the shortest path to this agent
            paths = record.incoming_paths
            min_depth = min(len(p) - 1 for p in paths) if paths else 0
            shortest_path = min(paths, key=len) if paths else [agent_id]
            
            chunk = ContextChunk(
                agent_id=agent_id,
                context=contexts[agent_id],
                relevance_score=record.incoming_signal,
                depth=min_depth,
                path=shortest_path,
            )
            chain.append(chunk)
        
        # Sort by depth (ascending), then by relevance (descending)
        chain.sort(key=lambda c: (c.depth, -c.relevance_score))
        
        return chain
    
    def _deduplicate_contexts(
        self,
        chain: List[ContextChunk],
    ) -> List[ContextChunk]:
        """
        Remove near-duplicate contexts while preserving unique information.
        Uses simple token overlap for Phase 1.
        """
        if not chain:
            return []
        
        deduped = [chain[0]]
        
        for chunk in chain[1:]:
            is_duplicate = False
            chunk_tokens = set(chunk.context.lower().split())
            
            for existing in deduped:
                existing_tokens = set(existing.context.lower().split())
                
                # Jaccard similarity
                intersection = len(chunk_tokens & existing_tokens)
                union = len(chunk_tokens | existing_tokens)
                
                if union > 0 and intersection / union > 0.7:
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                deduped.append(chunk)
        
        return deduped
    
    def _build_synthesis_prompt(
        self,
        query: str,
        chain: List[ContextChunk],
    ) -> str:
        """
        Build synthesis prompt that preserves structural information.
        """
        if not chain:
            return f"Query: {query}\n\nNo relevant information found."
        
        # Group by depth to show propagation layers
        depth_groups: Dict[int, List[ContextChunk]] = defaultdict(list)
        for chunk in chain:
            depth_groups[chunk.depth].append(chunk)
        
        prompt_parts = [
            "You are synthesizing knowledge from a distributed graph network.",
            f"\nQuery: {query}",
            "\nActivated knowledge clusters (grouped by proximity to query):",
        ]
        
        for depth in sorted(depth_groups.keys()):
            chunks = depth_groups[depth]
            if depth == 0:
                prompt_parts.append(f"\n=== Entry Points (directly matched) ===")
            else:
                prompt_parts.append(f"\n=== Depth {depth} (propagated from entry points) ===")
            
            for chunk in chunks:
                path_str = " → ".join(chunk.path)
                prompt_parts.append(
                    f"[{chunk.agent_id}] (score: {chunk.relevance_score:.2f}, path: {path_str})"
                )
                prompt_parts.append(f"  Context: {chunk.context}")
        
        prompt_parts.extend([
            "\n" + "=" * 50,
            "\nSynthesize a comprehensive answer that:",
            "1. Addresses the query directly",
            "2. Respects the relationships between clusters (shown in paths)",
            "3. Cites which clusters contributed to each part of your answer",
            "4. Notes any gaps or uncertainties",
        ])
        
        return "\n".join(prompt_parts)
    
    def _deterministic_synthesis(
        self,
        query: str,
        chain: List[ContextChunk],
    ) -> str:
        """
        Phase 1: Deterministic synthesis without LLM.
        Concatenates contexts with structural annotations.
        """
        if not chain:
            return f"No relevant information found for: {query}"
        
        parts = []
        
        # Entry point summary
        entry_chunks = [c for c in chain if c.depth == 0]
        if entry_chunks:
            entry_summary = "; ".join(c.context for c in entry_chunks[:3])
            parts.append(f"Primary sources: {entry_summary}")
        
        # Propagated information
        propagated = [c for c in chain if c.depth > 0]
        if propagated:
            prop_summary = "; ".join(c.context for c in propagated[:3])
            parts.append(f"Related information: {prop_summary}")
        
        # Add provenance
        all_agents = [c.agent_id for c in chain]
        parts.append(f"[Sources: {', '.join(all_agents)}]")
        
        return " ".join(parts)
    
    def _llm_synthesis(self, prompt: str) -> str:
        """
        Phase 2: LLM-based synthesis.
        Placeholder - will integrate with Ollama.
        """
        # TODO: Integrate with Ollama
        # For now, return deterministic placeholder
        return f"[LLM synthesis not yet implemented]\n{prompt[:500]}..."
    
    def _identify_contributors(
        self,
        answer: str,
        chain: List[ContextChunk],
    ) -> List[str]:
        """
        Identify which agents actually contributed to the answer.
        Uses simple heuristic: check if context terms appear in answer.
        """
        contributors = []
        answer_tokens = set(answer.lower().split())
        
        for chunk in chain:
            context_tokens = set(chunk.context.lower().split())
            
            # Check if significant overlap between context and answer
            overlap = context_tokens & answer_tokens
            
            # Filter common words
            stopwords = {"the", "a", "an", "is", "are", "for", "to", "of", "and", "in"}
            meaningful_overlap = overlap - stopwords
            
            # If at least 2 meaningful words from context appear in answer
            if len(meaningful_overlap) >= 2:
                contributors.append(chunk.agent_id)
        
        return contributors


def update_propagation_result_with_contributions(
    result: PropagationResult,
    contributing_agents: List[str],
) -> PropagationResult:
    """
    Update propagation result to mark which agents contributed.
    This is critical for learning routing - we need to distinguish
    'activated' from 'contributed'.
    """
    result.contributing_agents = contributing_agents
    
    for agent_id in contributing_agents:
        if agent_id in result.activation_records:
            result.activation_records[agent_id].state = ActivationState.CONTRIBUTED
    
    return result
