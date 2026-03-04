// components/NeuralExperimentPanel.tsx
// UPDATED to support v3 Hybrid Cluster Router with ClusterCards
import React, { useState, useCallback, useEffect } from "react";
import {
    Play,
    Pause,
    SkipBack,
    SkipForward,
    ChevronRight,
    ChevronLeft,
    Zap,
    Search,
    Target,
    Activity,
    Loader2,
    X,
    RefreshCw,
    Settings,
    Shield,
    Users,
    GitBranch,
    Layers,
    CheckCircle,
} from "lucide-react";

// ========================
// TYPES - v3 API Response
// ========================

interface ClusterCard {
    cluster_id: string;
    node_count: number;
    node_ids: string[];
    type_distribution: Record<string, number>;
    primary_type: string;
    team_distribution: Record<string, number>;
    primary_team: string;
    mitre_techniques: string[];
    tools: string[];
    internal_edges: number;
    external_edges: number;
    edge_types: Record<string, number>;
    core_nodes: string[];
    keywords: string[];
    coherence_score: number;
    connectivity_score: number;
    summary: string;
}

interface PropagationStep {
    from_agent: string;
    to_agent: string;
    signal: number;
    hop: number;
}

interface EntryScore {
    semantic: number;
    mitre: number;
    tools: number;
    keywords: number;
    combined: number;
}

interface V3SearchResult {
    query: string;
    entry_agents: string[];
    entry_scores: Record<string, EntryScore>;
    activated_agents: string[];
    contributing_agents: string[];
    propagation_path: PropagationStep[];
    contexts: Record<string, string>;
    cluster_cards: Record<string, ClusterCard>;
    nodes_traversed: number;
    time_ms: number;
}

// For graph overlay compatibility
export interface NeuralOverlay {
    nodeStates: Map<string, NeuralNodeState>;
    nodeSignals: Map<string, number>;
    propagationEdges: Map<string, { source: string; target: string; signal: number }>;
    activationOrder: string[];
    currentStep: number;
}

export type NeuralNodeState = "dormant" | "entry" | "activated" | "contributing";

interface NeuralExperimentPanelProps {
    onOverlayChange: (overlay: NeuralOverlay | null) => void;
    onNodeFocus: (nodeId: string) => void;
}

// ========================
// CONSTANTS
// ========================

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

const EXAMPLE_QUERIES = [
    "credential dumping mimikatz",
    "lateral movement psexec",
    "cobalt strike beacon",
    "persistence registry",
    "defense evasion",
];

const TEAM_COLORS: Record<string, string> = {
    opfor: "bg-red-500/20 text-red-300 border-red-500",
    automation: "bg-blue-500/20 text-blue-300 border-blue-500",
    content_dev: "bg-purple-500/20 text-purple-300 border-purple-500",
    range: "bg-green-500/20 text-green-300 border-green-500",
    unknown: "bg-gray-500/20 text-gray-300 border-gray-500",
};

// ========================
// COMPONENT
// ========================

export const NeuralExperimentPanel: React.FC<NeuralExperimentPanelProps> = ({
    onOverlayChange,
    onNodeFocus,
}) => {
    // State
    const [query, setQuery] = useState("");
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [result, setResult] = useState<V3SearchResult | null>(null);

    // View state
    const [activeTab, setActiveTab] = useState<"overview" | "cards" | "propagation">("overview");
    const [selectedAgent, setSelectedAgent] = useState<string | null>(null);

    // Settings
    const [topK, setTopK] = useState(5);
    const [showSettings, setShowSettings] = useState(false);
    const [apiVersion, setApiVersion] = useState<"v3" | "v2">("v3");

    // ========================
    // API CALLS
    // ========================

    const runExperiment = useCallback(async () => {
        if (!query.trim()) return;

        setIsLoading(true);
        setError(null);
        setResult(null);
        setSelectedAgent(null);
        onOverlayChange(null);

        try {
            const params = new URLSearchParams({
                q: query,
                top_k: String(topK),
            });

            const endpoint = apiVersion === "v3" 
                ? `${API_BASE}/api/neural-v3/search?${params}`
                : `${API_BASE}/api/neural/experiment/run?${params}`;

            const response = await fetch(endpoint);

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.detail || `HTTP ${response.status}`);
            }

            const data: V3SearchResult = await response.json();
            console.log("🧠 Neural v3 search result:", data);
            setResult(data);

            // Apply overlay for graph visualization
            applyOverlay(data);

        } catch (err) {
            console.error("Neural search failed:", err);
            setError(err instanceof Error ? err.message : "Search failed");
        } finally {
            setIsLoading(false);
        }
    }, [query, topK, apiVersion, onOverlayChange]);

    // ========================
    // OVERLAY GENERATION
    // ========================

    const applyOverlay = useCallback(
        (data: V3SearchResult) => {
            if (!data) return;

            const nodeStates = new Map<string, NeuralNodeState>();
            const nodeSignals = new Map<string, number>();
            const propagationEdges = new Map<string, { source: string; target: string; signal: number }>();
            const activationOrder: string[] = [];

            // Process each cluster's nodes
            Object.entries(data.cluster_cards).forEach(([agentId, card]) => {
                const isEntry = data.entry_agents.includes(agentId);
                const isContributing = data.contributing_agents.includes(agentId);
                const isActivated = data.activated_agents.includes(agentId);

                let state: NeuralNodeState = "dormant";
                if (isEntry) state = "entry";
                else if (isContributing) state = "contributing";
                else if (isActivated) state = "activated";

                const signal = data.entry_scores[agentId]?.combined || 0;

                // Apply state to all nodes in this cluster
                card.node_ids.forEach((nodeId) => {
                    nodeStates.set(nodeId, state);
                    nodeSignals.set(nodeId, signal);
                    if (state !== "dormant") {
                        activationOrder.push(nodeId);
                    }
                });
            });

            // Add propagation edges
            data.propagation_path.forEach((step) => {
                const fromCard = data.cluster_cards[step.from_agent];
                const toCard = data.cluster_cards[step.to_agent];

                if (fromCard?.node_ids?.[0] && toCard?.node_ids?.[0]) {
                    const edgeKey = `${fromCard.node_ids[0]}-${toCard.node_ids[0]}`;
                    propagationEdges.set(edgeKey, {
                        source: fromCard.node_ids[0],
                        target: toCard.node_ids[0],
                        signal: step.signal,
                    });
                }
            });

            const overlay: NeuralOverlay = {
                nodeStates,
                nodeSignals,
                propagationEdges,
                activationOrder,
                currentStep: data.propagation_path.length,
            };

            onOverlayChange(overlay);
        },
        [onOverlayChange]
    );

    const handleReset = () => {
        setResult(null);
        setSelectedAgent(null);
        setError(null);
        onOverlayChange(null);
    };

    const handleAgentClick = (agentId: string) => {
        setSelectedAgent(agentId === selectedAgent ? null : agentId);
        
        // Focus on first node of this cluster
        const card = result?.cluster_cards[agentId];
        if (card?.node_ids?.[0]) {
            onNodeFocus(card.node_ids[0]);
        }
    };

    // ========================
    // RENDER
    // ========================

    return (
        <div className="bg-gray-800/95 backdrop-blur border border-gray-600 rounded-lg shadow-xl overflow-hidden max-h-[calc(100vh-200px)] flex flex-col">
            {/* Header */}
            <div className="bg-gray-900 px-4 py-3 border-b border-gray-700 flex items-center justify-between flex-shrink-0">
                <div className="flex items-center gap-2">
                    <Zap className="w-5 h-5 text-yellow-500" />
                    <span className="font-semibold text-white">Neural Routing v3</span>
                    <span className="text-xs px-2 py-0.5 bg-emerald-600 rounded text-white">Hybrid</span>
                </div>
                <div className="flex items-center gap-2">
                    <button
                        onClick={() => setShowSettings(!showSettings)}
                        className={`p-1.5 rounded hover:bg-gray-700 ${
                            showSettings ? "bg-gray-700 text-yellow-400" : "text-gray-400"
                        }`}
                        title="Settings"
                    >
                        <Settings className="w-4 h-4" />
                    </button>
                    {result && (
                        <button
                            onClick={handleReset}
                            className="p-1.5 rounded hover:bg-gray-700 text-gray-400 hover:text-white"
                            title="Reset"
                        >
                            <RefreshCw className="w-4 h-4" />
                        </button>
                    )}
                </div>
            </div>

            {/* Settings Panel */}
            {showSettings && (
                <div className="px-4 py-3 bg-gray-900/50 border-b border-gray-700 space-y-3 flex-shrink-0">
                    <div>
                        <label className="text-xs text-gray-400 block mb-1">
                            Top-K Entry Agents: {topK}
                        </label>
                        <input
                            type="range"
                            min={1}
                            max={10}
                            value={topK}
                            onChange={(e) => setTopK(Number(e.target.value))}
                            className="w-full accent-yellow-500"
                        />
                    </div>
                    <div>
                        <label className="text-xs text-gray-400 block mb-1">API Version</label>
                        <div className="flex gap-2">
                            <button
                                onClick={() => setApiVersion("v3")}
                                className={`px-3 py-1 rounded text-xs ${
                                    apiVersion === "v3"
                                        ? "bg-emerald-600 text-white"
                                        : "bg-gray-700 text-gray-300"
                                }`}
                            >
                                v3 Hybrid
                            </button>
                            <button
                                onClick={() => setApiVersion("v2")}
                                className={`px-3 py-1 rounded text-xs ${
                                    apiVersion === "v2"
                                        ? "bg-blue-600 text-white"
                                        : "bg-gray-700 text-gray-300"
                                }`}
                            >
                                v2 Enhanced
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Query Input */}
            <div className="p-4 border-b border-gray-700 flex-shrink-0">
                <div className="relative">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                    <input
                        type="text"
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        onKeyDown={(e) => e.key === "Enter" && runExperiment()}
                        placeholder="Search with neural routing..."
                        className="w-full pl-10 pr-20 py-2 bg-gray-700 border border-gray-600 rounded text-sm text-white placeholder-gray-400 focus:outline-none focus:border-yellow-500"
                        disabled={isLoading}
                    />
                    <button
                        onClick={runExperiment}
                        disabled={isLoading || !query.trim()}
                        className="absolute right-2 top-1/2 -translate-y-1/2 px-3 py-1 bg-yellow-600 hover:bg-yellow-500 disabled:bg-gray-600 disabled:cursor-not-allowed rounded text-xs font-medium text-white"
                    >
                        {isLoading ? (
                            <Loader2 className="w-4 h-4 animate-spin" />
                        ) : (
                            "Search"
                        )}
                    </button>
                </div>

                {/* Example queries */}
                <div className="mt-2 flex flex-wrap gap-1">
                    {EXAMPLE_QUERIES.slice(0, 3).map((eq) => (
                        <button
                            key={eq}
                            onClick={() => setQuery(eq)}
                            className="text-xs px-2 py-0.5 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded"
                        >
                            {eq.length > 20 ? eq.slice(0, 20) + "..." : eq}
                        </button>
                    ))}
                </div>
            </div>

            {/* Error Display */}
            {error && (
                <div className="px-4 py-3 bg-red-900/30 border-b border-red-800 text-red-300 text-sm flex items-center gap-2 flex-shrink-0">
                    <X className="w-4 h-4" />
                    {error}
                </div>
            )}

            {/* Results */}
            {result && (
                <div className="flex-1 overflow-hidden flex flex-col">
                    {/* Metrics Summary */}
                    <div className="px-4 py-3 bg-gray-900/30 border-b border-gray-700 grid grid-cols-4 gap-2 text-center flex-shrink-0">
                        <div>
                            <div className="text-lg font-bold text-yellow-400">
                                {result.entry_agents.length}
                            </div>
                            <div className="text-xs text-gray-400">Entry</div>
                        </div>
                        <div>
                            <div className="text-lg font-bold text-blue-400">
                                {result.activated_agents.length}
                            </div>
                            <div className="text-xs text-gray-400">Activated</div>
                        </div>
                        <div>
                            <div className="text-lg font-bold text-emerald-400">
                                {result.contributing_agents.length}
                            </div>
                            <div className="text-xs text-gray-400">Contributing</div>
                        </div>
                        <div>
                            <div className="text-lg font-bold text-purple-400">
                                {result.propagation_path.length}
                            </div>
                            <div className="text-xs text-gray-400">Hops</div>
                        </div>
                    </div>

                    {/* Tabs */}
                    <div className="flex border-b border-gray-700 flex-shrink-0">
                        <button
                            onClick={() => setActiveTab("overview")}
                            className={`flex-1 px-4 py-2 text-sm ${
                                activeTab === "overview"
                                    ? "bg-gray-700 text-white border-b-2 border-yellow-500"
                                    : "text-gray-400 hover:text-white"
                            }`}
                        >
                            Overview
                        </button>
                        <button
                            onClick={() => setActiveTab("cards")}
                            className={`flex-1 px-4 py-2 text-sm ${
                                activeTab === "cards"
                                    ? "bg-gray-700 text-white border-b-2 border-yellow-500"
                                    : "text-gray-400 hover:text-white"
                            }`}
                        >
                            Clusters
                        </button>
                        <button
                            onClick={() => setActiveTab("propagation")}
                            className={`flex-1 px-4 py-2 text-sm ${
                                activeTab === "propagation"
                                    ? "bg-gray-700 text-white border-b-2 border-yellow-500"
                                    : "text-gray-400 hover:text-white"
                            }`}
                        >
                            Propagation
                        </button>
                    </div>

                    {/* Tab Content */}
                    <div className="flex-1 overflow-y-auto">
                        {activeTab === "overview" && (
                            <OverviewTab result={result} onAgentClick={handleAgentClick} />
                        )}
                        {activeTab === "cards" && (
                            <ClusterCardsTab
                                result={result}
                                selectedAgent={selectedAgent}
                                onAgentClick={handleAgentClick}
                            />
                        )}
                        {activeTab === "propagation" && (
                            <PropagationTab result={result} />
                        )}
                    </div>

                    {/* Footer */}
                    <div className="px-4 py-2 bg-gray-900/50 border-t border-gray-700 text-xs text-gray-500 flex justify-between flex-shrink-0">
                        <span>{result.nodes_traversed} nodes traversed</span>
                        <span>{result.time_ms.toFixed(0)}ms</span>
                    </div>
                </div>
            )}

            {/* Empty state */}
            {!result && !isLoading && !error && (
                <div className="px-4 py-8 text-center flex-1">
                    <Activity className="w-12 h-12 text-gray-600 mx-auto mb-3" />
                    <p className="text-gray-400 text-sm">
                        Enter a query to search with hybrid semantic-structural clustering
                    </p>
                    <p className="text-gray-500 text-xs mt-2">
                        Clusters are formed by KNN + edge affinity, producing coherent expertise neighborhoods
                    </p>
                </div>
            )}
        </div>
    );
};

// ========================
// TAB COMPONENTS
// ========================

const OverviewTab: React.FC<{
    result: V3SearchResult;
    onAgentClick: (id: string) => void;
}> = ({ result, onAgentClick }) => {
    return (
        <div className="p-4 space-y-4">
            {/* Entry Agents */}
            <div>
                <div className="text-xs text-gray-400 mb-2 flex items-center gap-1">
                    <Target className="w-3 h-3" />
                    Entry Agents
                </div>
                <div className="space-y-2">
                    {result.entry_agents.map((agentId) => {
                        const card = result.cluster_cards[agentId];
                        const scores = result.entry_scores[agentId];
                        if (!card) return null;

                        return (
                            <button
                                key={agentId}
                                onClick={() => onAgentClick(agentId)}
                                className="w-full text-left p-3 bg-amber-500/10 border border-amber-500/30 rounded hover:bg-amber-500/20 transition"
                            >
                                <div className="flex items-center justify-between mb-1">
                                    <span className="font-medium text-amber-300">
                                        {card.cluster_id}
                                    </span>
                                    <TeamBadge team={card.primary_team} />
                                </div>
                                <div className="text-xs text-gray-400">
                                    {card.node_count} {card.primary_type}s • coherence: {(card.coherence_score * 100).toFixed(0)}%
                                </div>
                                {scores && (
                                    <div className="mt-2 flex gap-2 text-xs">
                                        <ScoreBadge label="semantic" value={scores.semantic} />
                                        <ScoreBadge label="tools" value={scores.tools} />
                                        <ScoreBadge label="combined" value={scores.combined} color="yellow" />
                                    </div>
                                )}
                            </button>
                        );
                    })}
                </div>
            </div>

            {/* Contexts */}
            {Object.keys(result.contexts).length > 0 && (
                <div>
                    <div className="text-xs text-gray-400 mb-2 flex items-center gap-1">
                        <CheckCircle className="w-3 h-3" />
                        Generated Contexts
                    </div>
                    <div className="space-y-2">
                        {Object.entries(result.contexts).map(([agentId, context]) => {
                            const card = result.cluster_cards[agentId];
                            return (
                                <div
                                    key={agentId}
                                    className="p-2 bg-emerald-900/20 border border-emerald-800 rounded text-xs"
                                >
                                    <div className="text-emerald-400 font-medium mb-1">
                                        {card?.cluster_id || agentId}
                                    </div>
                                    <div className="text-gray-300">{context}</div>
                                </div>
                            );
                        })}
                    </div>
                </div>
            )}
        </div>
    );
};

const ClusterCardsTab: React.FC<{
    result: V3SearchResult;
    selectedAgent: string | null;
    onAgentClick: (id: string) => void;
}> = ({ result, selectedAgent, onAgentClick }) => {
    const selectedCard = selectedAgent ? result.cluster_cards[selectedAgent] : null;

    return (
        <div className="p-4">
            {/* Cluster List */}
            <div className="grid grid-cols-2 gap-2 mb-4">
                {Object.entries(result.cluster_cards).map(([agentId, card]) => {
                    const isEntry = result.entry_agents.includes(agentId);
                    const isSelected = agentId === selectedAgent;

                    return (
                        <button
                            key={agentId}
                            onClick={() => onAgentClick(agentId)}
                            className={`p-2 rounded border text-left transition ${
                                isSelected
                                    ? "bg-yellow-500/20 border-yellow-500"
                                    : isEntry
                                    ? "bg-amber-500/10 border-amber-500/30 hover:bg-amber-500/20"
                                    : "bg-gray-700/50 border-gray-600 hover:bg-gray-700"
                            }`}
                        >
                            <div className="flex items-center justify-between">
                                <span className="text-xs font-medium text-white truncate">
                                    {card.cluster_id}
                                </span>
                                <TeamBadge team={card.primary_team} size="sm" />
                            </div>
                            <div className="text-xs text-gray-400 mt-1">
                                {card.node_count} nodes
                            </div>
                            <CoherenceMeter value={card.coherence_score} />
                        </button>
                    );
                })}
            </div>

            {/* Selected Card Detail */}
            {selectedCard && (
                <ClusterCardDetail card={selectedCard} />
            )}
        </div>
    );
};

const PropagationTab: React.FC<{ result: V3SearchResult }> = ({ result }) => {
    if (result.propagation_path.length === 0) {
        return (
            <div className="p-4 text-center text-gray-400">
                <GitBranch className="w-8 h-8 mx-auto mb-2 opacity-50" />
                <p className="text-sm">No propagation occurred</p>
                <p className="text-xs mt-1">All activated clusters were direct entry matches</p>
            </div>
        );
    }

    return (
        <div className="p-4">
            <div className="space-y-2">
                {result.propagation_path.map((step, idx) => {
                    const fromCard = result.cluster_cards[step.from_agent];
                    const toCard = result.cluster_cards[step.to_agent];

                    return (
                        <div
                            key={idx}
                            className="p-3 bg-gray-700/50 rounded border border-gray-600"
                        >
                            <div className="flex items-center gap-2 text-sm">
                                <div className="flex items-center gap-1">
                                    <TeamBadge team={fromCard?.primary_team || "unknown"} size="sm" />
                                    <span className="text-white">{fromCard?.cluster_id || step.from_agent}</span>
                                </div>
                                <ChevronRight className="w-4 h-4 text-gray-500" />
                                <div className="flex items-center gap-1">
                                    <TeamBadge team={toCard?.primary_team || "unknown"} size="sm" />
                                    <span className="text-white">{toCard?.cluster_id || step.to_agent}</span>
                                </div>
                            </div>
                            <div className="flex gap-4 mt-2 text-xs text-gray-400">
                                <span>Hop: {step.hop}</span>
                                <span>Signal: {(step.signal * 100).toFixed(0)}%</span>
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
};

// ========================
// SUB-COMPONENTS
// ========================

const TeamBadge: React.FC<{ team: string; size?: "sm" | "md" }> = ({ team, size = "md" }) => {
    const colorClass = TEAM_COLORS[team] || TEAM_COLORS.unknown;
    const sizeClass = size === "sm" ? "text-xs px-1.5 py-0.5" : "text-xs px-2 py-0.5";

    return (
        <span className={`rounded border ${colorClass} ${sizeClass}`}>
            {team}
        </span>
    );
};

const ScoreBadge: React.FC<{
    label: string;
    value: number;
    color?: "blue" | "yellow" | "green";
}> = ({ label, value, color = "blue" }) => {
    const colors = {
        blue: "bg-blue-500/20 text-blue-300",
        yellow: "bg-yellow-500/20 text-yellow-300",
        green: "bg-green-500/20 text-green-300",
    };

    return (
        <span className={`px-1.5 py-0.5 rounded ${colors[color]}`}>
            {label}: {(value * 100).toFixed(0)}%
        </span>
    );
};

const CoherenceMeter: React.FC<{ value: number }> = ({ value }) => {
    const percent = value * 100;
    const color = percent >= 80 ? "bg-emerald-500" : percent >= 50 ? "bg-yellow-500" : "bg-red-500";

    return (
        <div className="mt-1 h-1 bg-gray-600 rounded overflow-hidden">
            <div
                className={`h-full ${color} transition-all`}
                style={{ width: `${percent}%` }}
            />
        </div>
    );
};

const ClusterCardDetail: React.FC<{ card: ClusterCard }> = ({ card }) => {
    return (
        <div className="p-3 bg-gray-900/50 rounded border border-gray-600 space-y-3">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <div className="font-medium text-white">{card.cluster_id}</div>
                    <div className="text-xs text-gray-400">
                        {card.node_count} artifacts • {card.primary_type}
                    </div>
                </div>
                <TeamBadge team={card.primary_team} />
            </div>

            {/* Metrics */}
            <div className="grid grid-cols-2 gap-2">
                <div className="text-center p-2 bg-gray-800 rounded">
                    <div className="text-lg font-bold text-emerald-400">
                        {(card.coherence_score * 100).toFixed(0)}%
                    </div>
                    <div className="text-xs text-gray-400">Coherence</div>
                </div>
                <div className="text-center p-2 bg-gray-800 rounded">
                    <div className="text-lg font-bold text-blue-400">
                        {(card.connectivity_score * 100).toFixed(0)}%
                    </div>
                    <div className="text-xs text-gray-400">Connectivity</div>
                </div>
            </div>

            {/* MITRE Techniques */}
            {card.mitre_techniques.length > 0 && (
                <div>
                    <div className="text-xs text-gray-400 mb-1 flex items-center gap-1">
                        <Shield className="w-3 h-3" />
                        MITRE Techniques
                    </div>
                    <div className="flex flex-wrap gap-1">
                        {card.mitre_techniques.slice(0, 6).map((t) => (
                            <span
                                key={t}
                                className="px-1.5 py-0.5 text-xs bg-red-500/20 text-red-300 rounded"
                            >
                                {t}
                            </span>
                        ))}
                        {card.mitre_techniques.length > 6 && (
                            <span className="px-1.5 py-0.5 text-xs text-gray-500">
                                +{card.mitre_techniques.length - 6}
                            </span>
                        )}
                    </div>
                </div>
            )}

            {/* Tools */}
            {card.tools.length > 0 && (
                <div>
                    <div className="text-xs text-gray-400 mb-1 flex items-center gap-1">
                        <Layers className="w-3 h-3" />
                        Tools
                    </div>
                    <div className="flex flex-wrap gap-1">
                        {card.tools.slice(0, 6).map((t) => (
                            <span
                                key={t}
                                className="px-1.5 py-0.5 text-xs bg-purple-500/20 text-purple-300 rounded"
                            >
                                {t}
                            </span>
                        ))}
                    </div>
                </div>
            )}

            {/* Core Nodes */}
            {card.core_nodes.length > 0 && (
                <div>
                    <div className="text-xs text-gray-400 mb-1 flex items-center gap-1">
                        <Target className="w-3 h-3" />
                        Core Artifacts
                    </div>
                    <div className="text-xs text-gray-300">
                        {card.core_nodes.slice(0, 5).join(", ")}
                    </div>
                </div>
            )}

            {/* Edge Stats */}
            <div className="text-xs text-gray-500 pt-2 border-t border-gray-700">
                {card.internal_edges} internal edges • {card.external_edges} external edges
            </div>
        </div>
    );
};

export default NeuralExperimentPanel;