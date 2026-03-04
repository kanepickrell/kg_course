// components/NeuralSearchBar.tsx
// Neural Graph Search UI - Semantic search with cluster activation visualization
import React, { useState, useCallback, useRef, useEffect } from "react";
import {
    Search,
    Loader2,
    X,
    Sparkles,
    Brain,
    ChevronDown,
    ChevronUp,
    Zap,
    Target,
    Clock,
    ExternalLink,
} from "lucide-react";

// =============================================================================
// TYPES
// =============================================================================

interface NeuralSearchResult {
    query: string;
    entry_agents: Record<string, AgentActivation>;
    activated_agents: Record<string, AgentActivation>;
    contributing_agents: Record<string, AgentActivation>;
    propagation_path: PropagationStep[];
    contexts: Record<string, string>;
    time_ms: number;
}

interface AgentActivation {
    agent_id: string;
    cluster_id?: string;
    relevance_score?: number;
    signal_strength?: number;
    node_ids?: string[];
}

interface PropagationStep {
    from_agent: string;
    to_agent: string;
    edge_type: string;
    signal_strength: number;
    depth: number;
}

interface NeuralSearchBarProps {
    onSearchResults: (results: NeuralSearchResult | null) => void;
    onHighlightNodes: (nodeIds: string[]) => void;
    onFocusNode: (nodeId: string) => void;
    disabled?: boolean;
    className?: string;
}

// =============================================================================
// API CONFIGURATION
// =============================================================================

const API_BASE = "http://localhost:8000";

// =============================================================================
// NEURAL SEARCH BAR COMPONENT
// =============================================================================

export const NeuralSearchBar: React.FC<NeuralSearchBarProps> = ({
    onSearchResults,
    onHighlightNodes,
    onFocusNode,
    disabled = false,
    className = "",
}) => {
    const [query, setQuery] = useState("");
    const [isSearching, setIsSearching] = useState(false);
    const [results, setResults] = useState<NeuralSearchResult | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [showResults, setShowResults] = useState(false);
    const [recentSearches, setRecentSearches] = useState<string[]>([]);
    
    const inputRef = useRef<HTMLInputElement>(null);
    const resultsRef = useRef<HTMLDivElement>(null);

    // Load recent searches from localStorage
    useEffect(() => {
        const saved = localStorage.getItem("protograph-recent-searches");
        if (saved) {
            try {
                setRecentSearches(JSON.parse(saved).slice(0, 5));
            } catch (e) {
                console.error("Failed to load recent searches:", e);
            }
        }
    }, []);

    // Save recent searches
    const saveRecentSearch = useCallback((searchQuery: string) => {
        setRecentSearches(prev => {
            const updated = [searchQuery, ...prev.filter(s => s !== searchQuery)].slice(0, 5);
            localStorage.setItem("protograph-recent-searches", JSON.stringify(updated));
            return updated;
        });
    }, []);

    // Perform neural search
    const performSearch = useCallback(async (searchQuery: string) => {
        if (!searchQuery.trim()) return;

        setIsSearching(true);
        setError(null);
        setShowResults(true);

        try {
            console.log(`🔍 Neural search: "${searchQuery}"`);
            
            const response = await fetch(
                `${API_BASE}/api/neural/search?q=${encodeURIComponent(searchQuery)}`
            );

            if (!response.ok) {
                throw new Error(`Search failed: ${response.statusText}`);
            }

            const data: NeuralSearchResult = await response.json();
            console.log("✅ Search results:", data);

            setResults(data);
            onSearchResults(data);
            saveRecentSearch(searchQuery);

            // Extract all node IDs from contributing agents for highlighting
            const nodeIds: string[] = [];
            if (data.contributing_agents) {
                Object.values(data.contributing_agents).forEach(agent => {
                    if (agent.node_ids) {
                        nodeIds.push(...agent.node_ids);
                    }
                });
            }

            if (nodeIds.length > 0) {
                onHighlightNodes(nodeIds);
            }

        } catch (err) {
            const errorMsg = err instanceof Error ? err.message : "Search failed";
            console.error("❌ Neural search error:", err);
            setError(errorMsg);
            setResults(null);
            onSearchResults(null);
        } finally {
            setIsSearching(false);
        }
    }, [onSearchResults, onHighlightNodes, saveRecentSearch]);

    // Handle form submit
    const handleSubmit = useCallback((e: React.FormEvent) => {
        e.preventDefault();
        performSearch(query);
    }, [query, performSearch]);

    // Handle clear
    const handleClear = useCallback(() => {
        setQuery("");
        setResults(null);
        setError(null);
        setShowResults(false);
        onSearchResults(null);
        onHighlightNodes([]);
        inputRef.current?.focus();
    }, [onSearchResults, onHighlightNodes]);

    // Handle clicking a result node
    const handleNodeClick = useCallback((nodeId: string) => {
        onFocusNode(nodeId);
        onHighlightNodes([nodeId]);
    }, [onFocusNode, onHighlightNodes]);

    // Handle clicking outside to close results
    useEffect(() => {
        const handleClickOutside = (event: MouseEvent) => {
            if (resultsRef.current && !resultsRef.current.contains(event.target as Node)) {
                // Don't close if clicking on the search input
                if (inputRef.current?.contains(event.target as Node)) return;
                setShowResults(false);
            }
        };
        document.addEventListener("mousedown", handleClickOutside);
        return () => document.removeEventListener("mousedown", handleClickOutside);
    }, []);

    // Keyboard shortcut to focus search
    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if ((e.metaKey || e.ctrlKey) && e.key === "k") {
                e.preventDefault();
                inputRef.current?.focus();
                inputRef.current?.select();
            }
        };
        window.addEventListener("keydown", handleKeyDown);
        return () => window.removeEventListener("keydown", handleKeyDown);
    }, []);

    // Count total matched nodes
    const totalMatchedNodes = results ? 
        Object.values(results.contributing_agents || {})
            .reduce((sum, agent) => sum + (agent.node_ids?.length || 0), 0) : 0;

    return (
        <div className={`relative ${className}`}>
            {/* Search Input */}
            <form onSubmit={handleSubmit} className="relative">
                <div className="relative flex items-center">
                    {/* Search Icon / Loading Spinner */}
                    <div className="absolute left-3 text-gray-400">
                        {isSearching ? (
                            <Loader2 className="w-4 h-4 animate-spin text-cactus-green" />
                        ) : (
                            <Brain className="w-4 h-4" />
                        )}
                    </div>

                    {/* Input Field */}
                    <input
                        ref={inputRef}
                        type="text"
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        onFocus={() => setShowResults(true)}
                        placeholder="Neural search... (⌘K)"
                        disabled={disabled || isSearching}
                        className={`
                            w-64 pl-10 pr-20 py-1.5 
                            bg-background border border-border rounded-lg
                            text-sm text-white placeholder-gray-500
                            focus:outline-none focus:ring-2 focus:ring-cactus-green/50 focus:border-cactus-green
                            disabled:opacity-50 disabled:cursor-not-allowed
                            transition-all duration-200
                        `}
                    />

                    {/* Action Buttons */}
                    <div className="absolute right-2 flex items-center gap-1">
                        {query && (
                            <button
                                type="button"
                                onClick={handleClear}
                                className="p-1 text-gray-400 hover:text-white transition-colors"
                                title="Clear search"
                            >
                                <X className="w-3 h-3" />
                            </button>
                        )}
                        <button
                            type="submit"
                            disabled={disabled || isSearching || !query.trim()}
                            className={`
                                p-1 rounded transition-colors
                                ${query.trim() 
                                    ? "text-cactus-green hover:bg-cactus-green/20" 
                                    : "text-gray-600 cursor-not-allowed"
                                }
                            `}
                            title="Search"
                        >
                            <Sparkles className="w-4 h-4" />
                        </button>
                    </div>
                </div>
            </form>

            {/* Results Dropdown */}
            {showResults && (results || error || recentSearches.length > 0) && (
                <div
                    ref={resultsRef}
                    className="absolute top-full left-0 mt-2 w-96 max-h-[70vh] overflow-hidden bg-card border-2 border-border rounded-lg shadow-2xl z-50"
                >
                    {/* Error State */}
                    {error && (
                        <div className="p-4 text-red-400 text-sm">
                            <div className="font-semibold mb-1">Search Error</div>
                            <div className="text-red-300/80">{error}</div>
                        </div>
                    )}

                    {/* Results */}
                    {results && !error && (
                        <div className="flex flex-col">
                            {/* Results Header */}
                            <div className="px-4 py-3 border-b border-border bg-secondary/50">
                                <div className="flex items-center justify-between">
                                    <div className="flex items-center gap-2">
                                        <Zap className="w-4 h-4 text-cactus-green" />
                                        <span className="text-sm font-semibold text-white">
                                            Neural Search Results
                                        </span>
                                    </div>
                                    <div className="flex items-center gap-3 text-xs text-gray-400">
                                        <span className="flex items-center gap-1">
                                            <Target className="w-3 h-3" />
                                            {totalMatchedNodes} nodes
                                        </span>
                                        <span className="flex items-center gap-1">
                                            <Clock className="w-3 h-3" />
                                            {results.time_ms.toFixed(0)}ms
                                        </span>
                                    </div>
                                </div>
                                <div className="mt-1 text-xs text-gray-500">
                                    Query: "{results.query}"
                                </div>
                            </div>

                            {/* Agent Activations */}
                            <div className="overflow-y-auto max-h-[50vh]">
                                {/* Contributing Agents with Context */}
                                {Object.entries(results.contexts || {}).length > 0 ? (
                                    <div className="p-2">
                                        <div className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide px-2 py-1">
                                            Activated Clusters
                                        </div>
                                        {Object.entries(results.contexts).map(([agentId, context]) => {
                                            const agent = results.contributing_agents?.[agentId];
                                            const isRelevant = !context.toLowerCase().includes("not_relevant");
                                            
                                            return (
                                                <AgentContextCard
                                                    key={agentId}
                                                    agentId={agentId}
                                                    context={context}
                                                    nodeIds={agent?.node_ids || []}
                                                    isRelevant={isRelevant}
                                                    onNodeClick={handleNodeClick}
                                                />
                                            );
                                        })}
                                    </div>
                                ) : (
                                    <div className="p-8 text-center text-gray-500">
                                        <Brain className="w-8 h-8 mx-auto mb-2 opacity-50" />
                                        <div className="text-sm">No relevant clusters found</div>
                                        <div className="text-xs mt-1">Try a different search query</div>
                                    </div>
                                )}
                            </div>

                            {/* Stats Footer */}
                            <div className="px-4 py-2 border-t border-border bg-secondary/30 text-[10px] text-gray-500">
                                <div className="flex items-center justify-between">
                                    <span>
                                        Entry: {Object.keys(results.entry_agents || {}).length} agents
                                    </span>
                                    <span>
                                        Propagated: {Object.keys(results.activated_agents || {}).length} agents
                                    </span>
                                    <span>
                                        Contributing: {Object.keys(results.contributing_agents || {}).length} agents
                                    </span>
                                </div>
                            </div>
                        </div>
                    )}

                    {/* Recent Searches (when no results) */}
                    {!results && !error && recentSearches.length > 0 && (
                        <div className="p-2">
                            <div className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide px-2 py-1">
                                Recent Searches
                            </div>
                            {recentSearches.map((search, idx) => (
                                <button
                                    key={idx}
                                    onClick={() => {
                                        setQuery(search);
                                        performSearch(search);
                                    }}
                                    className="w-full px-3 py-2 text-left text-sm text-gray-300 hover:bg-secondary rounded transition-colors flex items-center gap-2"
                                >
                                    <Clock className="w-3 h-3 text-gray-500" />
                                    {search}
                                </button>
                            ))}
                        </div>
                    )}
                </div>
            )}
        </div>
    );
};

// =============================================================================
// AGENT CONTEXT CARD COMPONENT
// =============================================================================

interface AgentContextCardProps {
    agentId: string;
    context: string;
    nodeIds: string[];
    isRelevant: boolean;
    onNodeClick: (nodeId: string) => void;
}

const AgentContextCard: React.FC<AgentContextCardProps> = ({
    agentId,
    context,
    nodeIds,
    isRelevant,
    onNodeClick,
}) => {
    const [expanded, setExpanded] = useState(false);

    // Parse agent ID to get cluster number
    const clusterNum = agentId.replace("agent_cluster_", "");

    return (
        <div 
            className={`
                m-2 rounded-lg border overflow-hidden transition-all duration-200
                ${isRelevant 
                    ? "border-cactus-green/30 bg-cactus-green/5" 
                    : "border-gray-700 bg-gray-800/50 opacity-60"
                }
            `}
        >
            {/* Header */}
            <button
                onClick={() => setExpanded(!expanded)}
                className="w-full px-3 py-2 flex items-center justify-between text-left hover:bg-white/5 transition-colors"
            >
                <div className="flex items-center gap-2">
                    <div 
                        className={`
                            w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold
                            ${isRelevant 
                                ? "bg-cactus-green/20 text-cactus-green" 
                                : "bg-gray-700 text-gray-400"
                            }
                        `}
                    >
                        {clusterNum}
                    </div>
                    <div>
                        <div className="text-xs font-medium text-white">
                            Cluster {clusterNum}
                        </div>
                        <div className="text-[10px] text-gray-500">
                            {nodeIds.length} nodes
                        </div>
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    {isRelevant && (
                        <span className="px-1.5 py-0.5 text-[9px] font-semibold uppercase bg-cactus-green/20 text-cactus-green rounded">
                            Relevant
                        </span>
                    )}
                    {expanded ? (
                        <ChevronUp className="w-4 h-4 text-gray-400" />
                    ) : (
                        <ChevronDown className="w-4 h-4 text-gray-400" />
                    )}
                </div>
            </button>

            {/* Expanded Content */}
            {expanded && (
                <div className="px-3 pb-3 border-t border-white/5">
                    {/* Context */}
                    <div className="mt-2 text-xs text-gray-400 leading-relaxed">
                        {context}
                    </div>

                    {/* Node List */}
                    {nodeIds.length > 0 && (
                        <div className="mt-3">
                            <div className="text-[10px] font-semibold text-gray-500 uppercase mb-1">
                                Matched Nodes
                            </div>
                            <div className="flex flex-wrap gap-1">
                                {nodeIds.slice(0, 8).map(nodeId => {
                                    // Extract label from node ID (format: collection/key)
                                    const label = nodeId.split("/").pop() || nodeId;
                                    return (
                                        <button
                                            key={nodeId}
                                            onClick={(e) => {
                                                e.stopPropagation();
                                                onNodeClick(nodeId);
                                            }}
                                            className="px-2 py-1 text-[10px] bg-secondary hover:bg-cactus-green/20 text-white hover:text-cactus-green rounded transition-colors flex items-center gap-1"
                                            title={nodeId}
                                        >
                                            {label}
                                            <ExternalLink className="w-2.5 h-2.5 opacity-50" />
                                        </button>
                                    );
                                })}
                                {nodeIds.length > 8 && (
                                    <span className="px-2 py-1 text-[10px] text-gray-500">
                                        +{nodeIds.length - 8} more
                                    </span>
                                )}
                            </div>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
};

export default NeuralSearchBar;
