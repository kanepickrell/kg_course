// components/GraphExplorer.tsx - D3 Version with Neural Experiment Support
// FIXED: Added onNodeInspect prop and other missing props from Index.tsx
import React, {
    useEffect,
    useState,
    useCallback,
    useRef,
    forwardRef,
    useImperativeHandle,
} from "react";
import { D3GraphCanvas, D3GraphCanvasRef, NeuralOverlay } from "./D3GraphCanvas";
import { NeuralExperimentPanel } from "./NeuralExperimentPanel";
import { GraphData, GraphNode, GraphEdge } from "@/lib/graph/GraphRenderer";
import {
    Filter,
    Expand,
    Shrink,
    Target,
    Trash2,
    RefreshCw,
    Keyboard,
    Zap,
    Pickaxe,
    Plus,
    Link2,
    X,
} from "lucide-react";

// ========================
// TYPE DEFINITIONS
// ========================

interface ClusterInfo {
    [clusterId: string]: {
        name: string;
        color: string;
        nodeCount?: number;
    };
}

interface SchemaFilter {
    nodeTypes: Set<string>;
    edgeTypes: Set<string>;
}

interface GraphExplorerProps {
    initialData?: GraphData;
    selectedNodes?: string[];  // External selection state from parent
    onNodeSelect?: (nodeIds: string[]) => void;
    onNodeInspect?: (node: GraphNode) => void;  // ADDED: For populating Gems sidebar
    onEdgeSelect?: (edgeId: string | null, edgeData?: GraphEdge) => void;
    onSelectionChange?: (nodes: string[], edges: string[]) => void;
    onNodeDeleted?: () => void;  // ADDED: Callback after node deletion
    mode?: "mining" | "discovery";  // ADDED: Explorer mode
    onModeChange?: (mode: "mining" | "discovery") => void;  // ADDED: Mode change callback
    className?: string;
}

export interface GraphExplorerRef {
    refresh: () => Promise<void>;
    refreshData: () => Promise<void>;  // Alias for refresh
    focusNode: (nodeId: string, duration?: number) => void;
    getSelectedNodes: () => string[];
    clearSelection: () => void;
}

// ========================
// CONSTANTS
// ========================

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

// ========================
// UTILITY FUNCTIONS
// ========================

function getNodeTypeFromId(nodeId: string): string {
    const parts = nodeId.split("/");
    return parts.length > 1 ? parts[0] : "unknown";
}

function getEdgeTypeFromId(edgeId: string): string {
    const parts = edgeId.split("/");
    return parts.length > 1 ? parts[0] : "unknown";
}

// ========================
// MAIN COMPONENT
// ========================

export const GraphExplorer = forwardRef<GraphExplorerRef, GraphExplorerProps>(
    (
        {
            initialData,
            selectedNodes: externalSelectedNodes,  // Renamed to distinguish from internal state
            onNodeSelect,
            onNodeInspect,  // ADDED
            onEdgeSelect,
            onSelectionChange,
            onNodeDeleted,  // ADDED
            mode,  // ADDED
            onModeChange,  // ADDED
            className = "",
        },
        ref
    ) => {
        // ========================
        // STATE
        // ========================

        // Graph data
        const [graphData, setGraphData] = useState<GraphData>({
            nodes: [],
            edges: [],
        });
        const [clusterInfo, setClusterInfo] = useState<ClusterInfo>({});

        // Selection state - use external if provided, otherwise internal
        const [internalSelectedNodes, setInternalSelectedNodes] = useState<string[]>([]);
        const selectedNodes = externalSelectedNodes ?? internalSelectedNodes;
        const setSelectedNodes = useCallback((nodes: string[] | ((prev: string[]) => string[])) => {
            if (typeof nodes === 'function') {
                setInternalSelectedNodes(nodes);
                // Also notify parent if callback provided
                setInternalSelectedNodes(prev => {
                    const newNodes = nodes(prev);
                    onNodeSelect?.(newNodes);
                    return newNodes;
                });
            } else {
                setInternalSelectedNodes(nodes);
                onNodeSelect?.(nodes);
            }
        }, [onNodeSelect]);

        const [selectedEdge, setSelectedEdge] = useState<string | null>(null);

        // UI state
        const [isLoading, setIsLoading] = useState(false);
        const [error, setError] = useState<string | null>(null);
        const [activeCluster, setActiveCluster] = useState<string | null>(null);
        const [isFullscreen, setIsFullscreen] = useState(false);
        const [showFilters, setShowFilters] = useState(false);
        const [showKeyboardShortcuts, setShowKeyboardShortcuts] = useState(false);

        // Schema filtering
        const [availableNodeTypes, setAvailableNodeTypes] = useState<string[]>([]);
        const [availableEdgeTypes, setAvailableEdgeTypes] = useState<string[]>([]);
        const [schemaFilter, setSchemaFilter] = useState<SchemaFilter>({
            nodeTypes: new Set<string>(),
            edgeTypes: new Set<string>(),
        });

        // NEURAL EXPERIMENT STATE
        const [showNeuralExperiment, setShowNeuralExperiment] = useState(false);
        const [neuralOverlay, setNeuralOverlay] = useState<NeuralOverlay | null>(null);

        // EDIT TOOLS FAB STATE
        const [showEditTools, setShowEditTools] = useState(false);
        const [showNodeForm, setShowNodeForm] = useState(false);
        const [showEdgeForm, setShowEdgeForm] = useState(false);
        const [newNodeData, setNewNodeData] = useState({
            label: "",
            type: "artifact",
            cluster: "default",
            description: "",
            tags: "",
        });
        const [newEdgeData, setNewEdgeData] = useState({
            relationshipType: "RELATES_TO",
            weight: 1.0,
            bidirectional: false,
        });

        // Refs
        const graphCanvasRef = useRef<D3GraphCanvasRef>(null);
        const containerRef = useRef<HTMLDivElement>(null);

        // ========================
        // COMPUTED VALUES
        // ========================

        const canDelete = selectedNodes.length === 1 || selectedEdge !== null;
        const canAddEdge = selectedNodes.length === 2;

        // ========================
        // EXPOSE METHODS TO PARENT
        // ========================

        useImperativeHandle(ref, () => ({
            refresh: fetchGraphData,
            refreshData: fetchGraphData,  // Alias
            focusNode: (nodeId: string, duration?: number) => {
                graphCanvasRef.current?.focusNode(nodeId, duration ?? 800);
            },
            getSelectedNodes: () => selectedNodes,
            clearSelection: () => {
                setInternalSelectedNodes([]);
                setSelectedEdge(null);
            },
        }));

        // ========================
        // DATA FETCHING
        // ========================

        const fetchGraphData = useCallback(async () => {
            setIsLoading(true);
            setError(null);

            try {
                const response = await fetch(`${API_BASE}/graph`);
                if (!response.ok) {
                    throw new Error(`Failed to fetch graph: ${response.statusText}`);
                }

                const data = await response.json();
                console.log(
                    `📊 Loaded graph: ${data.nodes?.length || 0} nodes, ${data.edges?.length || 0} edges`
                );

                // Extract node types
                const nodeTypes = new Set<string>();
                data.nodes?.forEach((n: GraphNode) => {
                    const type = getNodeTypeFromId(n.id);
                    nodeTypes.add(type);
                });

                // Extract edge types
                const edgeTypes = new Set<string>();
                data.edges?.forEach((e: GraphEdge) => {
                    const type = getEdgeTypeFromId(e.id);
                    edgeTypes.add(type);
                });

                setAvailableNodeTypes(Array.from(nodeTypes).sort());
                setAvailableEdgeTypes(Array.from(edgeTypes).sort());

                // Build cluster info
                const clusters: ClusterInfo = {};
                data.nodes?.forEach((n: GraphNode) => {
                    const cluster = n.cluster || "default";
                    if (!clusters[cluster]) {
                        clusters[cluster] = {
                            name: cluster,
                            color: getClusterColor(cluster),
                            nodeCount: 0,
                        };
                    }
                    clusters[cluster].nodeCount =
                        (clusters[cluster].nodeCount || 0) + 1;
                });

                setClusterInfo(clusters);
                setGraphData({
                    nodes: data.nodes || [],
                    edges: data.edges || [],
                });
            } catch (err) {
                console.error("Failed to fetch graph:", err);
                setError(err instanceof Error ? err.message : "Failed to load graph");
            } finally {
                setIsLoading(false);
            }
        }, []);

        // Initial load
        useEffect(() => {
            if (initialData) {
                setGraphData(initialData);
            } else {
                fetchGraphData();
            }
        }, [initialData, fetchGraphData]);

        // ========================
        // FILTERING LOGIC
        // ========================

        const displayGraphData = React.useMemo(() => {
            let filteredNodes = graphData.nodes;
            let filteredEdges = graphData.edges;

            // Filter by cluster
            if (activeCluster) {
                filteredNodes = filteredNodes.filter(
                    (n) => n.cluster === activeCluster
                );
                const nodeIds = new Set(filteredNodes.map((n) => n.id));
                filteredEdges = filteredEdges.filter(
                    (e) => nodeIds.has(e.source) && nodeIds.has(e.target)
                );
            }

            // Filter by schema (node types)
            if (schemaFilter.nodeTypes.size > 0) {
                filteredNodes = filteredNodes.filter((n) => {
                    const type = getNodeTypeFromId(n.id);
                    return schemaFilter.nodeTypes.has(type);
                });
                const nodeIds = new Set(filteredNodes.map((n) => n.id));
                filteredEdges = filteredEdges.filter(
                    (e) => nodeIds.has(e.source) && nodeIds.has(e.target)
                );
            }

            // Filter by schema (edge types)
            if (schemaFilter.edgeTypes.size > 0) {
                filteredEdges = filteredEdges.filter((e) => {
                    const type = getEdgeTypeFromId(e.id);
                    return schemaFilter.edgeTypes.has(type);
                });
            }

            return { nodes: filteredNodes, edges: filteredEdges };
        }, [graphData, activeCluster, schemaFilter]);

        // ========================
        // SELECTION HANDLERS
        // ========================

        const handleNodeClick = useCallback(
            (event: MouseEvent, nodeId: string, nodeData: GraphNode) => {
                console.log('🎯 Node clicked:', nodeId, nodeData);  // Debug log
                
                const isMultiSelect = event.ctrlKey || event.metaKey || event.shiftKey;

                if (isMultiSelect) {
                    setInternalSelectedNodes((prev) => {
                        const newSelection = prev.includes(nodeId)
                            ? prev.filter((id) => id !== nodeId)
                            : [...prev, nodeId];
                        onNodeSelect?.(newSelection);
                        return newSelection;
                    });
                } else {
                    setInternalSelectedNodes([nodeId]);
                    setSelectedEdge(null);
                    onNodeSelect?.([nodeId]);
                }

                // FIXED: Call onNodeInspect with full node data for the Gems sidebar
                if (onNodeInspect) {
                    console.log('📤 Calling onNodeInspect with:', nodeData);  // Debug log
                    onNodeInspect(nodeData);
                }
            },
            [onNodeSelect, onNodeInspect]
        );

        const handleNodeDoubleClick = useCallback(
            (event: MouseEvent, nodeId: string, nodeData: GraphNode) => {
                graphCanvasRef.current?.focusNode(nodeId, 600);
            },
            []
        );

        const handleEdgeClick = useCallback(
            (event: MouseEvent, edgeId: string, edgeData: GraphEdge) => {
                setSelectedEdge(edgeId);
                setInternalSelectedNodes([]);
                onEdgeSelect?.(edgeId, edgeData);
            },
            [onEdgeSelect]
        );

        // ========================
        // KEYBOARD SHORTCUTS
        // ========================

        useEffect(() => {
            const handleKeyDown = (e: KeyboardEvent) => {
                // Escape - clear selection
                if (e.key === "Escape") {
                    setInternalSelectedNodes([]);
                    setSelectedEdge(null);
                    setShowEditTools(false);
                    setShowNodeForm(false);
                    setShowEdgeForm(false);
                }

                // F - fit view
                if (e.key === "f" && !e.ctrlKey && !e.metaKey) {
                    const activeElement = document.activeElement;
                    if (
                        activeElement?.tagName !== "INPUT" &&
                        activeElement?.tagName !== "TEXTAREA"
                    ) {
                        graphCanvasRef.current?.fitView(600);
                    }
                }

                // Delete - delete selected nodes
                if ((e.key === "Delete" || e.key === "Backspace") && canDelete) {
                    const activeElement = document.activeElement;
                    if (
                        activeElement?.tagName !== "INPUT" &&
                        activeElement?.tagName !== "TEXTAREA"
                    ) {
                        handleDeleteClick();
                    }
                }

                // N - toggle neural experiment
                if (e.key === "n" && !e.ctrlKey && !e.metaKey) {
                    const activeElement = document.activeElement;
                    if (
                        activeElement?.tagName !== "INPUT" &&
                        activeElement?.tagName !== "TEXTAREA"
                    ) {
                        setShowNeuralExperiment((prev) => !prev);
                    }
                }
            };

            window.addEventListener("keydown", handleKeyDown);
            return () => window.removeEventListener("keydown", handleKeyDown);
        }, [selectedNodes, canDelete]);

        // ========================
        // FAB ACTION HANDLERS
        // ========================

        const handleDeleteClick = useCallback(() => {
            if (selectedEdge) {
                // Delete edge
                const confirmDelete = window.confirm("Delete selected edge?");
                if (!confirmDelete) return;

                fetch(`${API_BASE}/prospector/edge/${encodeURIComponent(selectedEdge)}`, {
                    method: "DELETE",
                })
                    .then((res) => {
                        if (res.ok) {
                            setGraphData((prev) => ({
                                ...prev,
                                edges: prev.edges.filter((e) => e.id !== selectedEdge),
                            }));
                            setSelectedEdge(null);
                            onNodeDeleted?.();
                        }
                    })
                    .catch((err) => console.error("Failed to delete edge:", err));
            } else if (selectedNodes.length === 1) {
                // Delete node
                const nodeId = selectedNodes[0];
                const confirmDelete = window.confirm(`Delete node "${nodeId}"?`);
                if (!confirmDelete) return;

                fetch(`${API_BASE}/prospector/node/${encodeURIComponent(nodeId)}`, {
                    method: "DELETE",
                })
                    .then((res) => {
                        if (res.ok) {
                            setGraphData((prev) => ({
                                nodes: prev.nodes.filter((n) => n.id !== nodeId),
                                edges: prev.edges.filter(
                                    (e) => e.source !== nodeId && e.target !== nodeId
                                ),
                            }));
                            setInternalSelectedNodes([]);
                            onNodeDeleted?.();
                        }
                    })
                    .catch((err) => console.error("Failed to delete node:", err));
            }
            setShowEditTools(false);
        }, [selectedEdge, selectedNodes, onNodeDeleted]);

        const handleCreateNode = useCallback(async () => {
            if (!newNodeData.label.trim()) {
                alert("Please enter a label for the node");
                return;
            }

            try {
                const response = await fetch(`${API_BASE}/prospector/node`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        label: newNodeData.label,
                        type: newNodeData.type,
                        cluster: newNodeData.cluster,
                        description: newNodeData.description,
                        tags: newNodeData.tags.split(",").map((t) => t.trim()).filter(Boolean),
                    }),
                });

                if (response.ok) {
                    const newNode = await response.json();
                    console.log("✅ Created node:", newNode);
                    
                    // Refresh graph to get the new node
                    await fetchGraphData();
                    
                    // Reset form
                    setNewNodeData({
                        label: "",
                        type: "artifact",
                        cluster: "default",
                        description: "",
                        tags: "",
                    });
                    setShowNodeForm(false);
                    setShowEditTools(false);
                } else {
                    const err = await response.text();
                    alert(`Failed to create node: ${err}`);
                }
            } catch (err) {
                console.error("Failed to create node:", err);
                alert("Failed to create node");
            }
        }, [newNodeData, fetchGraphData]);

        const handleCreateEdge = useCallback(async () => {
            if (selectedNodes.length !== 2) {
                alert("Please select exactly 2 nodes to create an edge");
                return;
            }

            try {
                const response = await fetch(`${API_BASE}/prospector/edge`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        from_node: selectedNodes[0],
                        to_node: selectedNodes[1],
                        relationship_type: newEdgeData.relationshipType,
                        weight: newEdgeData.weight,
                        bidirectional: newEdgeData.bidirectional,
                    }),
                });

                if (response.ok) {
                    const newEdge = await response.json();
                    console.log("✅ Created edge:", newEdge);
                    
                    // Refresh graph to get the new edge
                    await fetchGraphData();
                    
                    // Reset form
                    setNewEdgeData({
                        relationshipType: "RELATES_TO",
                        weight: 1.0,
                        bidirectional: false,
                    });
                    setShowEdgeForm(false);
                    setShowEditTools(false);
                    setInternalSelectedNodes([]);
                } else {
                    const err = await response.text();
                    alert(`Failed to create edge: ${err}`);
                }
            } catch (err) {
                console.error("Failed to create edge:", err);
                alert("Failed to create edge");
            }
        }, [selectedNodes, newEdgeData, fetchGraphData]);

        // ========================
        // NODE DELETION (original)
        // ========================

        const handleDeleteSelected = useCallback(async () => {
            if (selectedNodes.length === 0) return;

            const confirmDelete = window.confirm(
                `Delete ${selectedNodes.length} selected node(s)?`
            );
            if (!confirmDelete) return;

            try {
                for (const nodeId of selectedNodes) {
                    await fetch(`${API_BASE}/api/artifact/${encodeURIComponent(nodeId)}`, {
                        method: "DELETE",
                    });
                }

                // Remove from local state
                setGraphData((prev) => ({
                    nodes: prev.nodes.filter((n) => !selectedNodes.includes(n.id)),
                    edges: prev.edges.filter(
                        (e) =>
                            !selectedNodes.includes(e.source) &&
                            !selectedNodes.includes(e.target)
                    ),
                }));

                setInternalSelectedNodes([]);
                
                // ADDED: Notify parent that node was deleted
                onNodeDeleted?.();
            } catch (err) {
                console.error("Failed to delete nodes:", err);
            }
        }, [selectedNodes, onNodeDeleted]);

        // ========================
        // SCHEMA FILTER HANDLERS
        // ========================

        const toggleNodeTypeFilter = (type: string) => {
            setSchemaFilter((prev) => {
                const newTypes = new Set(prev.nodeTypes);
                if (newTypes.has(type)) {
                    newTypes.delete(type);
                } else {
                    newTypes.add(type);
                }
                return { ...prev, nodeTypes: newTypes };
            });
        };

        const toggleEdgeTypeFilter = (type: string) => {
            setSchemaFilter((prev) => {
                const newTypes = new Set(prev.edgeTypes);
                if (newTypes.has(type)) {
                    newTypes.delete(type);
                } else {
                    newTypes.add(type);
                }
                return { ...prev, edgeTypes: newTypes };
            });
        };

        const clearAllFilters = () => {
            setSchemaFilter({ nodeTypes: new Set(), edgeTypes: new Set() });
            setActiveCluster(null);
        };

        // ========================
        // FULLSCREEN
        // ========================

        const toggleFullscreen = useCallback(() => {
            if (!containerRef.current) return;

            if (!isFullscreen) {
                containerRef.current.requestFullscreen?.();
            } else {
                document.exitFullscreen?.();
            }
            setIsFullscreen(!isFullscreen);
        }, [isFullscreen]);

        // ========================
        // NEURAL EXPERIMENT HANDLERS
        // ========================

        const handleNeuralOverlayChange = useCallback((overlay: NeuralOverlay | null) => {
            setNeuralOverlay(overlay);
        }, []);

        const handleNeuralNodeFocus = useCallback((nodeId: string) => {
            graphCanvasRef.current?.focusNode(nodeId, 800);
            setInternalSelectedNodes([nodeId]);
            onNodeSelect?.([nodeId]);
            
            // Also trigger inspect for the focused node
            const node = graphData.nodes.find(n => n.id === nodeId);
            if (node && onNodeInspect) {
                onNodeInspect(node);
            }
        }, [onNodeSelect, onNodeInspect, graphData.nodes]);

        // ========================
        // RENDER
        // ========================

        return (
            <div
                ref={containerRef}
                className={`relative w-full h-full bg-gray-900 ${className}`}
            >
                {/* TOP CONTROL BAR */}
                <div className="absolute top-0 left-0 right-0 z-30 bg-gray-900/90 backdrop-blur border-b border-gray-700 px-4 py-2">
                    <div className="flex items-center justify-between gap-4">
                        {/* Left side - stats */}
                        <div className="text-xs text-gray-400">
                            {displayGraphData.nodes.length} nodes • {displayGraphData.edges.length} edges
                        </div>

                        {/* Control buttons */}
                        <div className="flex items-center gap-2">
                            {/* Filter toggle */}
                            <button
                                onClick={() => setShowFilters(!showFilters)}
                                className={`neo-button-secondary px-3 py-1.5 text-xs flex items-center gap-2 ${
                                    showFilters ? "ring-2 ring-blue-500" : ""
                                }`}
                            >
                                <Filter className="w-4 h-4" />
                                Filters
                                {(schemaFilter.nodeTypes.size > 0 ||
                                    schemaFilter.edgeTypes.size > 0 ||
                                    activeCluster) && (
                                    <span className="bg-blue-500 text-white px-1.5 py-0.5 rounded-full text-xs">
                                        {schemaFilter.nodeTypes.size +
                                            schemaFilter.edgeTypes.size +
                                            (activeCluster ? 1 : 0)}
                                    </span>
                                )}
                            </button>

                            {/* Neural Experiment toggle */}
                            <button
                                onClick={() => setShowNeuralExperiment(!showNeuralExperiment)}
                                className={`neo-button-secondary px-3 py-1.5 text-xs flex items-center gap-2 ${
                                    showNeuralExperiment
                                        ? "ring-2 ring-yellow-500 bg-yellow-900/30"
                                        : ""
                                }`}
                                title="Neural Routing Experiment (N)"
                            >
                                <Zap className="w-4 h-4" />
                                Neural
                            </button>

                            {/* Keyboard shortcuts */}
                            <button
                                onClick={() => setShowKeyboardShortcuts(!showKeyboardShortcuts)}
                                className="neo-button-secondary px-3 py-1.5 text-xs"
                                title="Keyboard Shortcuts"
                            >
                                <Keyboard className="w-4 h-4" />
                            </button>

                            {/* Fit view */}
                            <button
                                onClick={() => graphCanvasRef.current?.fitView(600)}
                                className="neo-button-secondary px-3 py-1.5 text-xs"
                                title="Fit View (F)"
                            >
                                <Target className="w-4 h-4" />
                            </button>

                            {/* Fullscreen */}
                            <button
                                onClick={toggleFullscreen}
                                className="neo-button-secondary px-3 py-1.5 text-xs"
                                title="Toggle Fullscreen"
                            >
                                {isFullscreen ? (
                                    <Shrink className="w-4 h-4" />
                                ) : (
                                    <Expand className="w-4 h-4" />
                                )}
                            </button>

                            {/* Refresh */}
                            <button
                                onClick={fetchGraphData}
                                disabled={isLoading}
                                className="neo-button-secondary px-3 py-1.5 text-xs"
                                title="Refresh Graph"
                            >
                                <RefreshCw
                                    className={`w-4 h-4 ${isLoading ? "animate-spin" : ""}`}
                                />
                            </button>

                            {/* Delete selected */}
                            {selectedNodes.length > 0 && (
                                <button
                                    onClick={handleDeleteSelected}
                                    className="neo-button-danger px-3 py-1.5 text-xs flex items-center gap-2"
                                    title="Delete Selected (Del)"
                                >
                                    <Trash2 className="w-4 h-4" />
                                    Delete ({selectedNodes.length})
                                </button>
                            )}
                        </div>
                    </div>
                </div>

                {/* FILTER PANEL */}
                {showFilters && (
                    <div className="absolute top-14 left-4 z-40 bg-gray-800 border border-gray-600 rounded-lg shadow-xl p-4 w-72 max-h-[60vh] overflow-y-auto">
                        <div className="flex items-center justify-between mb-4">
                            <h3 className="text-sm font-semibold text-white">Filters</h3>
                            <button
                                onClick={clearAllFilters}
                                className="text-xs text-gray-400 hover:text-white"
                            >
                                Clear All
                            </button>
                        </div>

                        {/* Cluster filter */}
                        <div className="mb-4">
                            <h4 className="text-xs font-medium text-gray-400 mb-2">
                                Clusters
                            </h4>
                            <div className="space-y-1">
                                {Object.entries(clusterInfo).map(([id, info]) => (
                                    <button
                                        key={id}
                                        onClick={() =>
                                            setActiveCluster(activeCluster === id ? null : id)
                                        }
                                        className={`w-full text-left px-2 py-1 rounded text-xs flex items-center gap-2 ${
                                            activeCluster === id
                                                ? "bg-blue-500/30 text-blue-300"
                                                : "hover:bg-gray-700 text-gray-300"
                                        }`}
                                    >
                                        <span
                                            className="w-3 h-3 rounded-full"
                                            style={{ backgroundColor: info.color }}
                                        />
                                        {info.name}
                                        <span className="ml-auto text-gray-500">
                                            {info.nodeCount}
                                        </span>
                                    </button>
                                ))}
                            </div>
                        </div>

                        {/* Node type filter */}
                        <div className="mb-4">
                            <h4 className="text-xs font-medium text-gray-400 mb-2">
                                Node Types
                            </h4>
                            <div className="space-y-1 max-h-40 overflow-y-auto">
                                {availableNodeTypes.map((type) => (
                                    <label
                                        key={type}
                                        className="flex items-center gap-2 text-xs text-gray-300 cursor-pointer hover:text-white"
                                    >
                                        <input
                                            type="checkbox"
                                            checked={schemaFilter.nodeTypes.has(type)}
                                            onChange={() => toggleNodeTypeFilter(type)}
                                            className="rounded border-gray-600"
                                        />
                                        {type}
                                    </label>
                                ))}
                            </div>
                        </div>

                        {/* Edge type filter */}
                        <div>
                            <h4 className="text-xs font-medium text-gray-400 mb-2">
                                Edge Types
                            </h4>
                            <div className="space-y-1 max-h-40 overflow-y-auto">
                                {availableEdgeTypes.map((type) => (
                                    <label
                                        key={type}
                                        className="flex items-center gap-2 text-xs text-gray-300 cursor-pointer hover:text-white"
                                    >
                                        <input
                                            type="checkbox"
                                            checked={schemaFilter.edgeTypes.has(type)}
                                            onChange={() => toggleEdgeTypeFilter(type)}
                                            className="rounded border-gray-600"
                                        />
                                        {type}
                                    </label>
                                ))}
                            </div>
                        </div>
                    </div>
                )}

                {/* KEYBOARD SHORTCUTS PANEL */}
                {showKeyboardShortcuts && (
                    <div className="absolute top-14 right-4 z-40 bg-gray-800 border border-gray-600 rounded-lg shadow-xl p-4 w-64">
                        <h3 className="text-sm font-semibold text-white mb-3">
                            Keyboard Shortcuts
                        </h3>
                        <div className="space-y-2 text-xs">
                            <div className="flex justify-between text-gray-300">
                                <span>Fit View</span>
                                <kbd className="px-2 py-0.5 bg-gray-700 rounded">F</kbd>
                            </div>
                            <div className="flex justify-between text-gray-300">
                                <span>Clear Selection</span>
                                <kbd className="px-2 py-0.5 bg-gray-700 rounded">Esc</kbd>
                            </div>
                            <div className="flex justify-between text-gray-300">
                                <span>Delete Selected</span>
                                <kbd className="px-2 py-0.5 bg-gray-700 rounded">Del</kbd>
                            </div>
                            <div className="flex justify-between text-gray-300">
                                <span>Multi-select</span>
                                <kbd className="px-2 py-0.5 bg-gray-700 rounded">Shift+Click</kbd>
                            </div>
                            <div className="flex justify-between text-gray-300">
                                <span>Neural Panel</span>
                                <kbd className="px-2 py-0.5 bg-gray-700 rounded">N</kbd>
                            </div>
                        </div>
                    </div>
                )}

                {/* GRAPH CANVAS */}
                <div className="absolute inset-0 pt-14">
                    <D3GraphCanvas
                        ref={graphCanvasRef}
                        graphData={displayGraphData}
                        selectedNodes={selectedNodes}
                        selectedEdge={selectedEdge}
                        activeCluster={activeCluster}
                        clusterInfo={clusterInfo}
                        neuralOverlay={neuralOverlay}
                        onNodeClick={handleNodeClick}
                        onNodeDoubleClick={handleNodeDoubleClick}
                        onEdgeClick={handleEdgeClick}
                    />
                </div>

                {/* NEURAL EXPERIMENT PANEL */}
                {showNeuralExperiment && (
                    <div className="absolute top-16 right-4 w-80 max-h-[calc(100vh-120px)] z-40">
                        <NeuralExperimentPanel
                            onOverlayChange={handleNeuralOverlayChange}
                            onNodeFocus={handleNeuralNodeFocus}
                        />
                    </div>
                )}

                {/* ======================== */}
                {/* FLOATING ACTION BUTTON - EDIT TOOLS */}
                {/* ======================== */}
                <div className="absolute bottom-12 left-4 z-40">
                    {/* Expanded Options - Show when FAB is open */}
                    {showEditTools && (
                        <div className="absolute bottom-14 left-0 flex flex-col gap-3 animate-in fade-in slide-in-from-bottom-2 duration-200">
                            {/* Delete */}
                            <button
                                onClick={(e) => {
                                    e.stopPropagation();
                                    if (canDelete) {
                                        handleDeleteClick();
                                    }
                                }}
                                className={`w-10 h-10 rounded-lg border-2 flex items-center justify-center transition-all duration-200 ${
                                    canDelete
                                        ? "bg-red-500/20 border-red-500 text-red-400 hover:bg-red-500/30 hover:scale-110 cursor-pointer"
                                        : "bg-black/40 border-gray-600 text-gray-500 cursor-not-allowed"
                                }`}
                                title={
                                    selectedEdge
                                        ? "Delete selected edge"
                                        : selectedNodes.length === 1
                                        ? "Delete selected node"
                                        : "Select 1 node or edge to delete"
                                }
                            >
                                <Trash2 className="w-4 h-4" />
                            </button>

                            {/* Add Edge */}
                            <button
                                onClick={(e) => {
                                    e.stopPropagation();
                                    if (canAddEdge) {
                                        setShowEdgeForm(true);
                                        setShowEditTools(false);
                                    }
                                }}
                                className={`w-10 h-10 rounded-lg border-2 flex items-center justify-center transition-all duration-200 ${
                                    canAddEdge
                                        ? "bg-blue-500/20 border-blue-500 text-blue-400 hover:bg-blue-500/30 hover:scale-110 cursor-pointer"
                                        : "bg-black/40 border-gray-600 text-gray-500 cursor-not-allowed"
                                }`}
                                title={
                                    canAddEdge
                                        ? "Add edge between selected nodes"
                                        : "Select 2 nodes to add edge"
                                }
                            >
                                <Link2 className="w-4 h-4" />
                            </button>

                            {/* Add Node */}
                            <button
                                onClick={(e) => {
                                    e.stopPropagation();
                                    setShowNodeForm(true);
                                    setShowEditTools(false);
                                }}
                                className="w-10 h-10 rounded-lg border-2 bg-emerald-500/20 border-emerald-500 text-emerald-400 hover:bg-emerald-500/30 flex items-center justify-center transition-all duration-200 hover:scale-110 cursor-pointer"
                                title="Add new node"
                            >
                                <Plus className="w-4 h-4" />
                            </button>
                        </div>
                    )}

                    {/* Main FAB Button - Sleek Square Design */}
                    <button
                        onClick={() => setShowEditTools(!showEditTools)}
                        className={`w-11 h-11 rounded-lg border-2 flex items-center justify-center transition-all duration-300 ${
                            showEditTools
                                ? "bg-emerald-500/20 border-emerald-500 text-emerald-400 rotate-45"
                                : "bg-black/60 border-gray-700 text-gray-400 hover:border-emerald-500/50 hover:text-emerald-400"
                        }`}
                        title="Edit tools"
                    >
                        <Pickaxe className="w-5 h-5 transition-transform" />
                    </button>
                </div>

                {/* ======================== */}
                {/* ADD NODE FORM MODAL */}
                {/* ======================== */}
                {showNodeForm && (
                    <div className="absolute inset-0 bg-black/50 flex items-center justify-center z-50">
                        <div className="bg-gray-800 border border-gray-600 rounded-lg shadow-2xl p-6 w-96 max-w-[90vw]">
                            <div className="flex items-center justify-between mb-4">
                                <h3 className="text-lg font-semibold text-white">Add New Node</h3>
                                <button
                                    onClick={() => setShowNodeForm(false)}
                                    className="text-gray-400 hover:text-white"
                                >
                                    <X className="w-5 h-5" />
                                </button>
                            </div>

                            <div className="space-y-4">
                                <div>
                                    <label className="block text-sm text-gray-400 mb-1">Label *</label>
                                    <input
                                        type="text"
                                        value={newNodeData.label}
                                        onChange={(e) =>
                                            setNewNodeData({ ...newNodeData, label: e.target.value })
                                        }
                                        className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white focus:outline-none focus:ring-2 focus:ring-orange-500"
                                        placeholder="Node label"
                                        autoFocus
                                    />
                                </div>

                                <div>
                                    <label className="block text-sm text-gray-400 mb-1">Type</label>
                                    <select
                                        value={newNodeData.type}
                                        onChange={(e) =>
                                            setNewNodeData({ ...newNodeData, type: e.target.value })
                                        }
                                        className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white focus:outline-none focus:ring-2 focus:ring-orange-500"
                                    >
                                        <option value="artifact">Artifact</option>
                                        <option value="person">Person</option>
                                        <option value="team">Team</option>
                                        <option value="project">Project</option>
                                        <option value="concept">Concept</option>
                                        <option value="tool">Tool</option>
                                    </select>
                                </div>

                                <div>
                                    <label className="block text-sm text-gray-400 mb-1">Cluster</label>
                                    <select
                                        value={newNodeData.cluster}
                                        onChange={(e) =>
                                            setNewNodeData({ ...newNodeData, cluster: e.target.value })
                                        }
                                        className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white focus:outline-none focus:ring-2 focus:ring-orange-500"
                                    >
                                        <option value="default">Default</option>
                                        {Object.keys(clusterInfo).map((cluster) => (
                                            <option key={cluster} value={cluster}>
                                                {cluster}
                                            </option>
                                        ))}
                                    </select>
                                </div>

                                <div>
                                    <label className="block text-sm text-gray-400 mb-1">Description</label>
                                    <textarea
                                        value={newNodeData.description}
                                        onChange={(e) =>
                                            setNewNodeData({ ...newNodeData, description: e.target.value })
                                        }
                                        className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white focus:outline-none focus:ring-2 focus:ring-orange-500 resize-none"
                                        rows={3}
                                        placeholder="Optional description"
                                    />
                                </div>

                                <div>
                                    <label className="block text-sm text-gray-400 mb-1">Tags (comma-separated)</label>
                                    <input
                                        type="text"
                                        value={newNodeData.tags}
                                        onChange={(e) =>
                                            setNewNodeData({ ...newNodeData, tags: e.target.value })
                                        }
                                        className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white focus:outline-none focus:ring-2 focus:ring-orange-500"
                                        placeholder="tag1, tag2, tag3"
                                    />
                                </div>
                            </div>

                            <div className="flex justify-end gap-3 mt-6">
                                <button
                                    onClick={() => setShowNodeForm(false)}
                                    className="px-4 py-2 text-gray-400 hover:text-white transition-colors"
                                >
                                    Cancel
                                </button>
                                <button
                                    onClick={handleCreateNode}
                                    className="px-4 py-2 bg-green-600 hover:bg-green-500 text-white rounded transition-colors"
                                >
                                    Create Node
                                </button>
                            </div>
                        </div>
                    </div>
                )}

                {/* ======================== */}
                {/* ADD EDGE FORM MODAL */}
                {/* ======================== */}
                {showEdgeForm && (
                    <div className="absolute inset-0 bg-black/50 flex items-center justify-center z-50">
                        <div className="bg-gray-800 border border-gray-600 rounded-lg shadow-2xl p-6 w-96 max-w-[90vw]">
                            <div className="flex items-center justify-between mb-4">
                                <h3 className="text-lg font-semibold text-white">Add Edge</h3>
                                <button
                                    onClick={() => setShowEdgeForm(false)}
                                    className="text-gray-400 hover:text-white"
                                >
                                    <X className="w-5 h-5" />
                                </button>
                            </div>

                            <div className="mb-4 p-3 bg-gray-700/50 rounded text-sm">
                                <div className="text-gray-400 mb-1">Connecting:</div>
                                <div className="text-blue-400 font-mono text-xs break-all">
                                    {selectedNodes[0]}
                                </div>
                                <div className="text-gray-500 my-1">→</div>
                                <div className="text-blue-400 font-mono text-xs break-all">
                                    {selectedNodes[1]}
                                </div>
                            </div>

                            <div className="space-y-4">
                                <div>
                                    <label className="block text-sm text-gray-400 mb-1">Relationship Type</label>
                                    <select
                                        value={newEdgeData.relationshipType}
                                        onChange={(e) =>
                                            setNewEdgeData({ ...newEdgeData, relationshipType: e.target.value })
                                        }
                                        className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                                    >
                                        <option value="RELATES_TO">RELATES_TO</option>
                                        <option value="DEPENDS_ON">DEPENDS_ON</option>
                                        <option value="CONTAINS">CONTAINS</option>
                                        <option value="CREATED_BY">CREATED_BY</option>
                                        <option value="OWNED_BY">OWNED_BY</option>
                                        <option value="REFERENCES">REFERENCES</option>
                                        <option value="DERIVED_FROM">DERIVED_FROM</option>
                                    </select>
                                </div>

                                <div>
                                    <label className="block text-sm text-gray-400 mb-1">Weight</label>
                                    <input
                                        type="number"
                                        min="0"
                                        max="1"
                                        step="0.1"
                                        value={newEdgeData.weight}
                                        onChange={(e) =>
                                            setNewEdgeData({ ...newEdgeData, weight: parseFloat(e.target.value) })
                                        }
                                        className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                                    />
                                </div>

                                <div className="flex items-center gap-2">
                                    <input
                                        type="checkbox"
                                        id="bidirectional"
                                        checked={newEdgeData.bidirectional}
                                        onChange={(e) =>
                                            setNewEdgeData({ ...newEdgeData, bidirectional: e.target.checked })
                                        }
                                        className="rounded border-gray-600"
                                    />
                                    <label htmlFor="bidirectional" className="text-sm text-gray-300">
                                        Bidirectional
                                    </label>
                                </div>
                            </div>

                            <div className="flex justify-end gap-3 mt-6">
                                <button
                                    onClick={() => setShowEdgeForm(false)}
                                    className="px-4 py-2 text-gray-400 hover:text-white transition-colors"
                                >
                                    Cancel
                                </button>
                                <button
                                    onClick={handleCreateEdge}
                                    className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded transition-colors"
                                >
                                    Create Edge
                                </button>
                            </div>
                        </div>
                    </div>
                )}

                {/* STATUS BAR */}
                <div className="absolute bottom-0 left-0 right-0 z-30 bg-gray-900/90 backdrop-blur border-t border-gray-700 px-4 py-1.5">
                    <div className="flex items-center justify-between text-xs text-gray-400">
                        <div className="flex items-center gap-4">
                            <span>
                                {displayGraphData.nodes.length} nodes •{" "}
                                {displayGraphData.edges.length} edges
                            </span>
                            {selectedNodes.length > 0 && (
                                <span className="text-blue-400">
                                    {selectedNodes.length} selected
                                </span>
                            )}
                            {selectedEdge && (
                                <span className="text-purple-400">
                                    Edge selected
                                </span>
                            )}
                            {activeCluster && (
                                <span className="text-purple-400">
                                    Cluster: {clusterInfo[activeCluster]?.name}
                                </span>
                            )}
                            {showNeuralExperiment && (
                                <span className="text-yellow-500 font-semibold flex items-center gap-1">
                                    <Zap className="w-3 h-3" /> NEURAL MODE
                                </span>
                            )}
                            {showEditTools && (
                                <span className="text-orange-500 font-semibold flex items-center gap-1">
                                    <Pickaxe className="w-3 h-3" /> PROSPECTING
                                </span>
                            )}
                        </div>
                        <div className="flex items-center gap-2">
                            {error && <span className="text-red-400">{error}</span>}
                            {isLoading && <span className="text-yellow-400">Loading...</span>}
                        </div>
                    </div>
                </div>

                {/* LOADING OVERLAY */}
                {isLoading && (
                    <div className="absolute inset-0 bg-gray-900/50 flex items-center justify-center z-50">
                        <div className="bg-gray-800 px-6 py-4 rounded-lg shadow-xl flex items-center gap-3">
                            <RefreshCw className="w-5 h-5 animate-spin text-blue-400" />
                            <span className="text-white">Loading graph...</span>
                        </div>
                    </div>
                )}
            </div>
        );
    }
);

GraphExplorer.displayName = "GraphExplorer";

// ========================
// HELPER FUNCTIONS
// ========================

function getClusterColor(clusterId: string): string {
    const colors = [
        "#3B82F6", // blue
        "#10B981", // emerald
        "#F59E0B", // amber
        "#EF4444", // red
        "#8B5CF6", // violet
        "#EC4899", // pink
        "#06B6D4", // cyan
        "#84CC16", // lime
    ];

    // Simple hash to get consistent color per cluster
    let hash = 0;
    for (let i = 0; i < clusterId.length; i++) {
        hash = clusterId.charCodeAt(i) + ((hash << 5) - hash);
    }
    return colors[Math.abs(hash) % colors.length];
}

export default GraphExplorer;