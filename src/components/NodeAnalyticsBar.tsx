import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronUp, ChevronDown, X } from "lucide-react";
import { Button } from "@/components/ui/button";

interface NodeAnalyticsBarProps {
    selectedNodes: string[];
    data: any;
    onNodeClick?: (nodeId: string) => void;
    onClose: () => void;
}

const NodeAnalyticsBar: React.FC<NodeAnalyticsBarProps> = ({
    selectedNodes,
    data,
    onNodeClick,
    onClose
}) => {
    const [isExpanded, setIsExpanded] = useState(true);

    if (selectedNodes.length === 0) return null;

    const selectedNodesData = data.nodes.filter((n: any) => selectedNodes.includes(n.id));

    return (
        <div className="w-full mb-4">
            {/* Collapsed State */}
            {!isExpanded && (
                <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    className="neo-card bg-card/95 backdrop-blur-md border-2 border-border overflow-hidden"
                >
                    <button
                        onClick={() => setIsExpanded(true)}
                        className="w-full p-3 flex items-center justify-between hover:bg-muted/30 transition-colors"
                    >
                        <div className="flex items-center gap-3">
                            <div className="flex items-center gap-2">
                                <span className="text-sm font-bold">
                                    Node Analytics
                                </span>
                                <span className="px-2 py-0.5 bg-accent-pink/20 border border-accent-pink/40 rounded-full text-xs font-bold">
                                    {selectedNodes.length} selected
                                </span>
                            </div>
                            <div className="flex gap-1 max-w-md overflow-hidden">
                                {selectedNodesData.slice(0, 3).map((node: any) => (
                                    <span
                                        key={node.id}
                                        className="px-2 py-0.5 bg-secondary border border-border rounded text-xs truncate max-w-[100px]"
                                    >
                                        {node.label}
                                    </span>
                                ))}
                                {selectedNodes.length > 3 && (
                                    <span className="px-2 py-0.5 text-xs text-muted-foreground">
                                        +{selectedNodes.length - 3} more
                                    </span>
                                )}
                            </div>
                        </div>
                        <ChevronDown className="w-4 h-4 text-muted-foreground" />
                    </button>
                </motion.div>
            )}

            {/* Expanded State */}
            <AnimatePresence>
                {isExpanded && (
                    <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: "auto", opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.3 }}
                        className="neo-card bg-card/95 backdrop-blur-md border-2 border-border overflow-hidden"
                    >
                        {/* Header */}
                        <div className="p-4 border-b-2 border-border bg-muted/30 flex items-center justify-between">
                            <div className="flex items-center gap-3">
                                <h3 className="text-lg font-extrabold">Node Analytics</h3>
                                <span className="px-3 py-1 bg-accent-pink/20 border-2 border-accent-pink/40 rounded-full text-sm font-bold">
                                    {selectedNodes.length} {selectedNodes.length === 1 ? "node" : "nodes"}
                                </span>
                            </div>
                            <div className="flex items-center gap-2">
                                <Button
                                    onClick={() => setIsExpanded(false)}
                                    size="sm"
                                    variant="ghost"
                                    className="h-7 w-7 p-0"
                                >
                                    <ChevronUp className="w-4 h-4" />
                                </Button>
                                <Button
                                    onClick={onClose}
                                    size="sm"
                                    variant="ghost"
                                    className="h-7 w-7 p-0"
                                >
                                    <X className="w-4 h-4" />
                                </Button>
                            </div>
                        </div>

                        {/* Horizontal Scrollable Content */}
                        <div className="p-4 overflow-x-auto">
                            <div className="flex gap-4 min-w-max">
                                {selectedNodesData.map((node: any) => {
                                    // Calculate connections for this node
                                    const connections = data.edges.filter(
                                        (e: any) => e.source === node.id || e.target === node.id
                                    );
                                    const incomingEdges = data.edges.filter((e: any) => e.target === node.id);
                                    const outgoingEdges = data.edges.filter((e: any) => e.source === node.id);

                                    return (
                                        <div
                                            key={node.id}
                                            className="neo-card p-4 w-[280px] flex-shrink-0 hover:shadow-lg transition-shadow cursor-pointer"
                                            onClick={() => onNodeClick?.(node.id)}
                                        >
                                            {/* Node Header */}
                                            <div className="mb-3">
                                                <h4 className="text-sm font-bold mb-1 truncate">{node.label}</h4>
                                                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                                                    <span className="px-2 py-0.5 bg-secondary border border-border rounded">
                                                        {node.type}
                                                    </span>
                                                    <span className="capitalize">{node.cluster.replace(/_/g, ' ')}</span>
                                                </div>
                                            </div>

                                            {/* Quick Stats Grid */}
                                            <div className="grid grid-cols-3 gap-2 mb-3">
                                                <div className="neo-card p-2 text-center">
                                                    <div className="text-lg font-bold text-blue-500">{connections.length}</div>
                                                    <div className="text-[9px] text-muted-foreground">Total</div>
                                                </div>
                                                <div className="neo-card p-2 text-center">
                                                    <div className="text-lg font-bold text-green-500">{incomingEdges.length}</div>
                                                    <div className="text-[9px] text-muted-foreground">In</div>
                                                </div>
                                                <div className="neo-card p-2 text-center">
                                                    <div className="text-lg font-bold text-orange-500">{outgoingEdges.length}</div>
                                                    <div className="text-[9px] text-muted-foreground">Out</div>
                                                </div>
                                            </div>

                                            {/* Importance Bar */}
                                            <div className="space-y-1">
                                                <div className="flex justify-between text-[10px]">
                                                    <span className="text-muted-foreground">Importance</span>
                                                    <span className="font-bold">{Math.round(node.importance * 100)}%</span>
                                                </div>
                                                <div className="h-2 bg-secondary rounded-full overflow-hidden border border-border">
                                                    <div
                                                        className="h-full bg-gradient-to-r from-accent-pink to-accent-teal transition-all"
                                                        style={{ width: `${node.importance * 100}%` }}
                                                    />
                                                </div>
                                            </div>

                                            {/* Additional Metadata */}
                                            <div className="mt-3 pt-3 border-t border-border space-y-1 text-[10px]">
                                                <div className="flex justify-between">
                                                    <span className="text-muted-foreground">ID:</span>
                                                    <span className="font-mono font-semibold">{node.id}</span>
                                                </div>
                                                {node.status && (
                                                    <div className="flex justify-between">
                                                        <span className="text-muted-foreground">Status:</span>
                                                        <span className="font-semibold capitalize">{node.status}</span>
                                                    </div>
                                                )}
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        </div>

                        {/* Summary Footer */}
                        {selectedNodes.length > 1 && (
                            <div className="p-3 border-t-2 border-border bg-muted/20">
                                <div className="flex items-center justify-between text-xs">
                                    <div className="flex gap-4">
                                        <div>
                                            <span className="text-muted-foreground">Avg Importance: </span>
                                            <span className="font-bold">
                                                {Math.round(
                                                    selectedNodesData.reduce((sum: number, n: any) => sum + n.importance, 0) /
                                                    selectedNodesData.length * 100
                                                )}%
                                            </span>
                                        </div>
                                        <div>
                                            <span className="text-muted-foreground">Clusters: </span>
                                            <span className="font-bold">
                                                {new Set(selectedNodesData.map((n: any) => n.cluster)).size}
                                            </span>
                                        </div>
                                        <div>
                                            <span className="text-muted-foreground">Types: </span>
                                            <span className="font-bold">
                                                {new Set(selectedNodesData.map((n: any) => n.type)).size}
                                            </span>
                                        </div>
                                    </div>
                                    <button
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            onClose();
                                        }}
                                        className="text-accent-pink hover:text-accent-pink/80 font-semibold"
                                    >
                                        Clear Selection
                                    </button>
                                </div>
                            </div>
                        )}
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
};

export default NodeAnalyticsBar;