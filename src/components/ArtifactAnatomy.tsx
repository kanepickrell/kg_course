import { PieChart, Pie, Cell, ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar } from "recharts";
import { useMemo, useState } from "react";
import { Layers, Link, Activity, ChevronDown, ChevronRight, Database, GitBranch, ArrowRight, TrendingUp, Users, Target, Trash2 } from "lucide-react";
import { toast } from "sonner";

interface ArtifactAnatomyProps {
    selectedNodes: string[];
    data: any;
    onNodeClick?: (nodeId: string) => void;
    onNodeDeleted?: () => void;
}

const ArtifactAnatomy: React.FC<ArtifactAnatomyProps> = ({ selectedNodes, data, onNodeClick, onNodeDeleted }) => {
    const [expandedNode, setExpandedNode] = useState<string | null>(null);
    const [viewMode, setViewMode] = useState<"cluster" | "node">("cluster");
    const [deleting, setDeleting] = useState<string | null>(null);

    const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

    if (selectedNodes.length === 0) return null;

    // Delete handler
    const handleDelete = async (nodeId: string, nodeLabel: string, event: React.MouseEvent) => {
        event.stopPropagation();
        
        if (!confirm(`Delete "${nodeLabel}"? This cannot be undone.`)) {
            return;
        }

        setDeleting(nodeId);

        try {
            const [collection, key] = nodeId.split('/');
            
            const response = await fetch(`${API_URL}/api/artifact/${collection}/${key}`, {
                method: 'DELETE'
            });

            if (!response.ok) {
                throw new Error('Failed to delete artifact');
            }

            toast.success(`Deleted ${nodeLabel}`);
            
            if (onNodeDeleted) {
                onNodeDeleted();
            }
            
        } catch (error) {
            console.error('Delete failed:', error);
            toast.error('Failed to delete artifact');
        } finally {
            setDeleting(null);
        }
    };

    // Determine if we're analyzing a cluster or individual nodes
    const selectedNodesData = data.nodes.filter((n: any) => selectedNodes.includes(n.id));
    const clusters = [...new Set(selectedNodesData.map((n: any) => n.cluster))];
    const isSingleCluster = clusters.length === 1;

    // Cluster Analytics
    const clusterAnalytics = useMemo(() => {
        if (!isSingleCluster) return null;

        const clusterName = clusters[0];
        const clusterNodes = data.nodes.filter((n: any) => n.cluster === clusterName);

        // Get all edges within this cluster
        const internalEdges = data.edges.filter(
            (e: any) => {
                const source = data.nodes.find((n: any) => n.id === e.source);
                const target = data.nodes.find((n: any) => n.id === e.target);
                return source?.cluster === clusterName && target?.cluster === clusterName;
            }
        );

        // Get cross-cluster edges
        const crossClusterEdges = data.edges.filter(
            (e: any) => {
                const source = data.nodes.find((n: any) => n.id === e.source);
                const target = data.nodes.find((n: any) => n.id === e.target);
                return (source?.cluster === clusterName || target?.cluster === clusterName) &&
                    source?.cluster !== target?.cluster;
            }
        );

        // Type distribution
        const typeDistribution: Record<string, number> = {};
        clusterNodes.forEach((n: any) => {
            typeDistribution[n.type] = (typeDistribution[n.type] || 0) + 1;
        });

        // Importance tiers
        const highImportance = clusterNodes.filter((n: any) => n.importance > 0.8).length;
        const medImportance = clusterNodes.filter((n: any) => n.importance > 0.6 && n.importance <= 0.8).length;
        const lowImportance = clusterNodes.filter((n: any) => n.importance <= 0.6).length;

        // External connections by cluster
        const externalConnections: Record<string, number> = {};
        crossClusterEdges.forEach((e: any) => {
            const source = data.nodes.find((n: any) => n.id === e.source);
            const target = data.nodes.find((n: any) => n.id === e.target);
            const externalCluster = source?.cluster === clusterName ? target?.cluster : source?.cluster;
            if (externalCluster) {
                externalConnections[externalCluster] = (externalConnections[externalCluster] || 0) + 1;
            }
        });

        // Find hub nodes (nodes with most connections)
        const nodeConnections = clusterNodes.map((n: any) => {
            const connections = data.edges.filter(
                (e: any) => e.source === n.id || e.target === n.id
            ).length;
            return { id: n.id, label: n.label, connections, importance: n.importance };
        }).sort((a, b) => b.connections - a.connections);

        // Calculate cluster density (internal connections / possible connections)
        const possibleConnections = (clusterNodes.length * (clusterNodes.length - 1)) / 2;
        const density = possibleConnections > 0 ? (internalEdges.length / possibleConnections) * 100 : 0;

        return {
            name: clusterName,
            totalNodes: clusterNodes.length,
            internalEdges: internalEdges.length,
            externalEdges: crossClusterEdges.length,
            typeDistribution,
            importanceTiers: [
                { tier: "High", count: highImportance, color: "#27AE60" },
                { tier: "Medium", count: medImportance, color: "#FFB84D" },
                { tier: "Low", count: lowImportance, color: "#FF6B6B" }
            ],
            externalConnections,
            hubNodes: nodeConnections.slice(0, 3),
            density: density.toFixed(1),
            avgImportance: (clusterNodes.reduce((sum: number, n: any) => sum + n.importance, 0) / clusterNodes.length).toFixed(2)
        };
    }, [isSingleCluster, clusters, data]);

    // Individual Node Analysis
    const nodeAnalysis = useMemo(() => {
        if (selectedNodes.length !== 1) return null;

        const node = data.nodes.find((n: any) => n.id === selectedNodes[0]);
        if (!node) return null;

        const connections = data.edges.filter(
            (e: any) => e.source === node.id || e.target === node.id
        );

        const incomingEdges = data.edges.filter((e: any) => e.target === node.id);
        const outgoingEdges = data.edges.filter((e: any) => e.source === node.id);

        const connectedNodeIds = connections.map((e: any) =>
            e.source === node.id ? e.target : e.source
        );
        const connectedNodes = data.nodes.filter((n: any) =>
            connectedNodeIds.includes(n.id)
        );

        const typeCounts: Record<string, number> = {};
        connectedNodes.forEach((n: any) => {
            typeCounts[n.type] = (typeCounts[n.type] || 0) + 1;
        });

        const crossClusterConnections = connectedNodes.filter(
            (n: any) => n.cluster !== node.cluster
        ).length;

        return {
            node,
            connections: connections.length,
            incoming: incomingEdges.length,
            outgoing: outgoingEdges.length,
            connectedNodes,
            typeCounts,
            crossCluster: crossClusterConnections,
            clusterConnections: new Set(connectedNodes.map((n: any) => n.cluster)).size
        };
    }, [selectedNodes, data]);

    const colors = ["#FFB84D", "#4DA6FF", "#FF6B6B", "#9B59B6", "#27AE60"];

    // Render node button with delete
    const renderNodeButton = (node: any, isExpanded: boolean) => (
        <div className="flex items-center gap-1">
            <button
                onClick={() => {
                    setExpandedNode(isExpanded ? null : node.id);
                    onNodeClick?.(node.id);
                }}
                className="flex-1 text-left p-2 rounded hover:bg-muted/50 transition-colors text-xs"
            >
                <div className="flex items-center gap-2">
                    {isExpanded ? (
                        <ChevronDown className="w-3 h-3 flex-shrink-0" />
                    ) : (
                        <ChevronRight className="w-3 h-3 flex-shrink-0" />
                    )}
                    <span className="font-semibold truncate">{node.label}</span>
                </div>
                {isExpanded && (
                    <div className="mt-2 pl-5 space-y-1 text-[10px] text-muted-foreground">
                        <div>Type: <span className="font-semibold">{node.type}</span></div>
                        <div>Importance: <span className="font-semibold">{node.importance}</span></div>
                        <div>Size: <span className="font-semibold">{node.size}</span></div>
                        <div>Cluster: <span className="font-semibold">{node.cluster}</span></div>
                    </div>
                )}
            </button>
            
            <button
                onClick={(e) => handleDelete(node.id, node.label, e)}
                disabled={deleting === node.id}
                className="p-2 hover:bg-destructive/20 rounded transition-colors disabled:opacity-50 flex-shrink-0"
                title="Delete node"
            >
                <Trash2 
                    size={14} 
                    className={`text-destructive ${deleting === node.id ? 'animate-pulse' : ''}`} 
                />
            </button>
        </div>
    );

    // Render cluster analytics view
    if (isSingleCluster && clusterAnalytics && viewMode === "cluster") {
        return (
            <div className="space-y-4">
                {/* Header with View Toggle */}
                <div className="flex items-center justify-between">
                    <div>
                        <h3 className="text-xl font-bold mb-1 capitalize">
                            {clusterAnalytics.name.replace(/_/g, ' ')}
                        </h3>
                        <p className="text-xs text-muted-foreground">Cluster Analytics</p>
                    </div>
                    {selectedNodes.length === 1 && (
                        <button
                            onClick={() => setViewMode("node")}
                            className="text-xs neo-button-secondary px-2 py-1"
                        >
                            View Node
                        </button>
                    )}
                </div>

                {/* Key Metrics Grid */}
                <div className="grid grid-cols-2 gap-2">
                    <div className="neo-card p-3">
                        <div className="flex items-center gap-2 mb-1">
                            <Database className="w-4 h-4 text-accent-teal" />
                            <span className="text-xs font-semibold">Total Nodes</span>
                        </div>
                        <div className="text-2xl font-bold">{clusterAnalytics.totalNodes}</div>
                    </div>
                    <div className="neo-card p-3">
                        <div className="flex items-center gap-2 mb-1">
                            <GitBranch className="w-4 h-4 text-accent-pink" />
                            <span className="text-xs font-semibold">Connections</span>
                        </div>
                        <div className="text-2xl font-bold">
                            {clusterAnalytics.internalEdges + clusterAnalytics.externalEdges}
                        </div>
                        <div className="text-[10px] text-muted-foreground">
                            {clusterAnalytics.internalEdges} internal • {clusterAnalytics.externalEdges} external
                        </div>
                    </div>
                    <div className="neo-card p-3">
                        <div className="flex items-center gap-2 mb-1">
                            <Activity className="w-4 h-4 text-accent-gold" />
                            <span className="text-xs font-semibold">Density</span>
                        </div>
                        <div className="text-2xl font-bold">{clusterAnalytics.density}%</div>
                    </div>
                    <div className="neo-card p-3">
                        <div className="flex items-center gap-2 mb-1">
                            <TrendingUp className="w-4 h-4 text-green-500" />
                            <span className="text-xs font-semibold">Avg Importance</span>
                        </div>
                        <div className="text-2xl font-bold">{clusterAnalytics.avgImportance}</div>
                    </div>
                </div>

                {/* Type Distribution Chart */}
                <div className="neo-card p-3">
                    <h4 className="text-xs font-bold mb-2 flex items-center gap-2">
                        <Layers className="w-4 h-4" />
                        Node Type Distribution
                    </h4>
                    <div className="h-[140px]">
                        <ResponsiveContainer>
                            <PieChart>
                                <Pie
                                    data={Object.entries(clusterAnalytics.typeDistribution).map(([type, count]) => ({
                                        name: type,
                                        value: count
                                    }))}
                                    dataKey="value"
                                    nameKey="name"
                                    outerRadius={50}
                                    label={(entry) => `${entry.name} (${entry.value})`}
                                    labelStyle={{ fontSize: 10 }}
                                >
                                    {Object.keys(clusterAnalytics.typeDistribution).map((_, index) => (
                                        <Cell key={index} fill={colors[index % colors.length]} />
                                    ))}
                                </Pie>
                                <Tooltip />
                            </PieChart>
                        </ResponsiveContainer>
                    </div>
                </div>

                {/* Importance Distribution */}
                <div className="neo-card p-3">
                    <h4 className="text-xs font-bold mb-2 flex items-center gap-2">
                        <Target className="w-4 h-4" />
                        Importance Tiers
                    </h4>
                    <div className="space-y-2">
                        {clusterAnalytics.importanceTiers.map((tier) => (
                            <div key={tier.tier} className="flex items-center gap-2">
                                <div
                                    className="w-3 h-3 rounded-full flex-shrink-0"
                                    style={{ backgroundColor: tier.color }}
                                />
                                <div className="flex-1">
                                    <div className="flex items-center justify-between text-xs">
                                        <span className="font-semibold">{tier.tier}</span>
                                        <span className="text-muted-foreground">{tier.count} nodes</span>
                                    </div>
                                    <div className="w-full bg-secondary rounded-full h-1.5 mt-1">
                                        <div
                                            className="h-1.5 rounded-full transition-all"
                                            style={{
                                                width: `${(tier.count / clusterAnalytics.totalNodes) * 100}%`,
                                                backgroundColor: tier.color
                                            }}
                                        />
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>

                {/* Hub Nodes */}
                <div className="neo-card p-3">
                    <h4 className="text-xs font-bold mb-2 flex items-center gap-2">
                        <Users className="w-4 h-4" />
                        Hub Nodes
                    </h4>
                    <div className="space-y-2">
                        {clusterAnalytics.hubNodes.map((hub, idx) => (
                            <button
                                key={hub.id}
                                onClick={() => onNodeClick?.(hub.id)}
                                className="w-full text-left p-2 rounded-lg hover:bg-muted/50 transition-colors border border-border/40"
                            >
                                <div className="flex items-center justify-between">
                                    <div className="flex-1 min-w-0">
                                        <div className="text-xs font-semibold truncate">{hub.label}</div>
                                        <div className="text-[10px] text-muted-foreground">
                                            {hub.connections} connections • {Math.round(hub.importance * 100)}% importance
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-1 ml-2">
                                        <span className="text-lg">{idx === 0 ? '🥇' : idx === 1 ? '🥈' : '🥉'}</span>
                                    </div>
                                </div>
                            </button>
                        ))}
                    </div>
                </div>

                {/* External Cluster Connections */}
                {Object.keys(clusterAnalytics.externalConnections).length > 0 && (
                    <div className="neo-card p-3">
                        <h4 className="text-xs font-bold mb-2 flex items-center gap-2">
                            <ArrowRight className="w-4 h-4" />
                            External Connections
                        </h4>
                        <div className="space-y-1.5">
                            {Object.entries(clusterAnalytics.externalConnections)
                                .sort(([, a], [, b]) => (b as number) - (a as number))
                                .map(([cluster, count]) => (
                                    <div key={cluster} className="flex items-center justify-between text-xs">
                                        <span className="capitalize">{cluster.replace(/_/g, ' ')}</span>
                                        <span className="font-bold text-accent-pink">{count}</span>
                                    </div>
                                ))}
                        </div>
                    </div>
                )}

                {/* Selected Nodes List */}
                {selectedNodes.length > 0 && (
                    <div className="neo-card p-3">
                        <h4 className="text-xs font-bold mb-2">
                            Selected Nodes ({selectedNodes.length})
                        </h4>
                        <div className="space-y-1 max-h-32 overflow-y-auto">
                            {selectedNodesData.map((node: any) => (
                                <div key={node.id}>
                                    {renderNodeButton(node, expandedNode === node.id)}
                                </div>
                            ))}
                        </div>
                    </div>
                )}
            </div>
        );
    }

    // Render single node view
    if (selectedNodes.length === 1 && nodeAnalysis) {
        const node = nodeAnalysis.node;

        return (
            <div className="space-y-4">
                {/* Header */}
                <div className="flex items-center justify-between">
                    <div>
                        <h3 className="text-xl font-bold mb-1">{node.label}</h3>
                        <div className="flex items-center gap-2 text-xs text-muted-foreground">
                            <Layers className="w-4 h-4" />
                            <span className="capitalize">{node.cluster.replace(/_/g, ' ')}</span>
                            <span>•</span>
                            <span>{node.type}</span>
                        </div>
                    </div>
                    <div className="flex items-center gap-2">
                        {isSingleCluster && (
                            <button
                                onClick={() => setViewMode("cluster")}
                                className="text-xs neo-button-secondary px-2 py-1"
                            >
                                View Cluster
                            </button>
                        )}
                        <button
                            onClick={(e) => handleDelete(node.id, node.label, e)}
                            disabled={deleting === node.id}
                            className="p-2 hover:bg-destructive/20 rounded transition-colors disabled:opacity-50"
                            title="Delete node"
                        >
                            <Trash2 size={16} className="text-destructive" />
                        </button>
                    </div>
                </div>

                {/* Node Properties Card */}
                <div className="neo-card p-3 bg-gradient-to-br from-accent-pink/10 to-accent-teal/10">
                    <h4 className="text-xs font-bold mb-2 flex items-center gap-2">
                        <Database className="w-4 h-4" />
                        Node Properties
                    </h4>
                    <div className="space-y-2 text-xs">
                        <div className="flex justify-between items-center p-2 bg-background/60 rounded">
                            <span className="text-muted-foreground">ID</span>
                            <span className="font-mono font-semibold">{node.id}</span>
                        </div>
                        <div className="flex justify-between items-center p-2 bg-background/60 rounded">
                            <span className="text-muted-foreground">Label</span>
                            <span className="font-semibold">{node.label}</span>
                        </div>
                        <div className="flex justify-between items-center p-2 bg-background/60 rounded">
                            <span className="text-muted-foreground">Type</span>
                            <span className="font-semibold capitalize">{node.type}</span>
                        </div>
                        <div className="flex justify-between items-center p-2 bg-background/60 rounded">
                            <span className="text-muted-foreground">Cluster</span>
                            <span className="font-semibold capitalize">{node.cluster.replace(/_/g, ' ')}</span>
                        </div>
                        <div className="flex justify-between items-center p-2 bg-background/60 rounded">
                            <span className="text-muted-foreground">Importance</span>
                            <div className="flex items-center gap-2">
                                <div className="w-20 bg-secondary rounded-full h-2">
                                    <div
                                        className="bg-accent-pink h-2 rounded-full transition-all"
                                        style={{ width: `${node.importance * 100}%` }}
                                    />
                                </div>
                                <span className="font-semibold">{Math.round(node.importance * 100)}%</span>
                            </div>
                        </div>
                        <div className="flex justify-between items-center p-2 bg-background/60 rounded">
                            <span className="text-muted-foreground">Size</span>
                            <span className="font-semibold">{node.size}</span>
                        </div>
                    </div>
                </div>

                {/* Connection Stats */}
                <div className="grid grid-cols-3 gap-2">
                    <div className="neo-card p-2 text-center">
                        <Activity className="w-4 h-4 mx-auto mb-1 text-accent-teal" />
                        <div className="text-lg font-bold">{nodeAnalysis.connections}</div>
                        <div className="text-[10px] text-muted-foreground">Total</div>
                    </div>
                    <div className="neo-card p-2 text-center">
                        <ArrowRight className="w-4 h-4 mx-auto mb-1 text-green-500 rotate-180" />
                        <div className="text-lg font-bold">{nodeAnalysis.incoming}</div>
                        <div className="text-[10px] text-muted-foreground">Incoming</div>
                    </div>
                    <div className="neo-card p-2 text-center">
                        <ArrowRight className="w-4 h-4 mx-auto mb-1 text-blue-500" />
                        <div className="text-lg font-bold">{nodeAnalysis.outgoing}</div>
                        <div className="text-[10px] text-muted-foreground">Outgoing</div>
                    </div>
                </div>

                {/* Network Impact */}
                <div className="grid grid-cols-2 gap-2">
                    <div className="neo-card p-3">
                        <div className="text-xs font-semibold mb-1">Cross-Cluster</div>
                        <div className="text-2xl font-bold text-accent-pink">{nodeAnalysis.crossCluster}</div>
                        <div className="text-[10px] text-muted-foreground">connections</div>
                    </div>
                    <div className="neo-card p-3">
                        <div className="text-xs font-semibold mb-1">Cluster Reach</div>
                        <div className="text-2xl font-bold text-accent-teal">{nodeAnalysis.clusterConnections}</div>
                        <div className="text-[10px] text-muted-foreground">clusters</div>
                    </div>
                </div>

                {/* Connected Node Types */}
                {Object.keys(nodeAnalysis.typeCounts).length > 0 && (
                    <div className="neo-card p-3">
                        <h4 className="text-xs font-bold mb-3">Connected Node Types</h4>
                        <div className="h-[120px]">
                            <ResponsiveContainer>
                                <PieChart>
                                    <Pie
                                        data={Object.entries(nodeAnalysis.typeCounts).map(([type, count]) => ({
                                            type,
                                            count
                                        }))}
                                        dataKey="count"
                                        nameKey="type"
                                        outerRadius={45}
                                        label={(entry) => `${entry.type}`}
                                        labelStyle={{ fontSize: 9 }}
                                    >
                                        {Object.keys(nodeAnalysis.typeCounts).map((_, index) => (
                                            <Cell key={index} fill={colors[index % colors.length]} />
                                        ))}
                                    </Pie>
                                    <Tooltip />
                                </PieChart>
                            </ResponsiveContainer>
                        </div>
                    </div>
                )}

                {/* Connected Nodes List */}
                <div className="neo-card p-3">
                    <h4 className="text-xs font-bold mb-2">
                        Connected Nodes ({nodeAnalysis.connectedNodes.length})
                    </h4>
                    <div className="space-y-1 max-h-40 overflow-y-auto">
                        {nodeAnalysis.connectedNodes.slice(0, 10).map((connectedNode: any) => (
                            <button
                                key={connectedNode.id}
                                onClick={() => onNodeClick?.(connectedNode.id)}
                                className="w-full text-left p-2 rounded hover:bg-muted/50 transition-colors"
                            >
                                <div className="text-xs font-semibold truncate">{connectedNode.label}</div>
                                <div className="text-[10px] text-muted-foreground">
                                    {connectedNode.type} • {connectedNode.cluster}
                                </div>
                            </button>
                        ))}
                        {nodeAnalysis.connectedNodes.length > 10 && (
                            <div className="text-[10px] text-center text-muted-foreground py-1">
                                +{nodeAnalysis.connectedNodes.length - 10} more
                            </div>
                        )}
                    </div>
                </div>
            </div>
        );
    }

    // Multi-select view (nodes from different clusters)
    return (
        <div className="space-y-4">
            <div>
                <h3 className="text-xl font-bold mb-1">Multi-Selection</h3>
                <p className="text-xs text-muted-foreground">
                    {selectedNodes.length} nodes across {clusters.length} clusters
                </p>
            </div>

            <div className="neo-card p-3">
                <h4 className="text-xs font-bold mb-2">Selected Nodes</h4>
                <div className="space-y-1 max-h-64 overflow-y-auto">
                    {selectedNodesData.map((node: any) => (
                        <div key={node.id}>
                            {renderNodeButton(node, expandedNode === node.id)}
                        </div>
                    ))}
                </div>
            </div>

            <div className="grid grid-cols-2 gap-2">
                <div className="neo-card p-3">
                    <div className="text-xs font-semibold mb-1">Clusters</div>
                    <div className="text-2xl font-bold">{clusters.length}</div>
                </div>
                <div className="neo-card p-3">
                    <div className="text-xs font-semibold mb-1">Nodes</div>
                    <div className="text-2xl font-bold">{selectedNodes.length}</div>
                </div>
            </div>
        </div>
    );
};

export default ArtifactAnatomy;