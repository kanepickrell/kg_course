// components/graph/D3GraphCanvas.tsx
import React, {
    useEffect,
    useRef,
    useImperativeHandle,
    forwardRef,
} from "react";
import * as d3 from "d3";
import {
    GraphRenderer,
    GraphData,
    ClusterInfo,
    GraphNode,
} from "@/lib/graph/GraphRenderer";

// ========================
// NEURAL OVERLAY TYPES
// ========================

export type NeuralNodeState = 'dormant' | 'entry' | 'activated' | 'contributing';

export interface NeuralOverlay {
    nodeStates: Map<string, NeuralNodeState>;
    nodeSignals: Map<string, number>;
    propagationEdges: Map<string, { source: string; target: string; signal: number }>;
    activationOrder: string[]; // Order nodes were activated for animation
    currentStep: number;
}

// ========================
// COMPONENT PROPS
// ========================

interface D3GraphCanvasProps {
    graphData: GraphData;
    selectedNodes: string[];
    selectedEdge?: string | null;
    activeCluster: string | null;
    clusterInfo: ClusterInfo;
    highlightedNodes?: string[];
    neuralOverlay?: NeuralOverlay | null;
    onNodeClick: (event: MouseEvent, nodeId: string, nodeData: GraphNode) => void;
    onNodeDoubleClick: (event: MouseEvent, nodeId: string, nodeData: GraphNode) => void;
    onEdgeClick?: (event: MouseEvent, edgeId: string, edgeData: any) => void;
    onNodeDragStart?: (nodeId: string) => void;
    onNodeDrag?: (nodeId: string) => void;
    onNodeDragEnd?: (nodeId: string) => void;
}

export interface D3GraphCanvasRef {
    fitView: (duration?: number) => void;
    focusNode: (nodeId: string, duration?: number) => void;
}

// ========================
// NEURAL STYLE CONSTANTS
// ========================

const NEURAL_COLORS = {
    dormant: '#4B5563',
    entry: '#F59E0B',
    activated: '#3B82F6',
    contributing: '#10B981',
    propagationEdge: '#A855F7',
};

// ========================
// COMPONENT
// ========================

export const D3GraphCanvas = forwardRef<D3GraphCanvasRef, D3GraphCanvasProps>(
    (
        {
            graphData,
            selectedNodes,
            selectedEdge,
            activeCluster,
            clusterInfo,
            highlightedNodes = [],
            neuralOverlay,
            onNodeClick,
            onNodeDoubleClick,
            onEdgeClick,
            onNodeDragStart,
            onNodeDrag,
            onNodeDragEnd,
        },
        ref
    ) => {
        const containerRef = useRef<HTMLDivElement>(null);
        const rendererRef = useRef<GraphRenderer | null>(null);
        const pulseAnimationRef = useRef<number | null>(null);
        const neuralAnimationRef = useRef<number | null>(null);

        // Keep callbacks in a ref so we don't have to re-init the renderer
        const callbacksRef = useRef({
            onNodeClick,
            onNodeDoubleClick,
            onEdgeClick,
            onNodeDragStart,
            onNodeDrag,
            onNodeDragEnd,
        });

        useEffect(() => {
            callbacksRef.current = {
                onNodeClick,
                onNodeDoubleClick,
                onEdgeClick,
                onNodeDragStart,
                onNodeDrag,
                onNodeDragEnd,
            };
        }, [onNodeClick, onNodeDoubleClick, onEdgeClick, onNodeDragStart, onNodeDrag, onNodeDragEnd]);

        // Expose methods to parent
        useImperativeHandle(ref, () => ({
            fitView: (duration?: number) => {
                rendererRef.current?.fitView(duration);
            },
            focusNode: (nodeId: string, duration?: number) => {
                rendererRef.current?.focusNode(nodeId, duration);
            },
        }));

        // Initialize renderer ONCE
        useEffect(() => {
            if (!containerRef.current) return;

            console.log("🎨 Initializing D3 GraphRenderer...");

            rendererRef.current = new GraphRenderer(
                containerRef.current,
                clusterInfo,
                {
                    onNodeClick: (event, nodeId, nodeData) => {
                        callbacksRef.current.onNodeClick?.(event, nodeId, nodeData);
                    },
                    onNodeDoubleClick: (event, nodeId, nodeData) => {
                        callbacksRef.current.onNodeDoubleClick?.(
                            event,
                            nodeId,
                            nodeData
                        );
                    },
                    onEdgeClick: (event, edgeId, edgeData) => {
                        callbacksRef.current.onEdgeClick?.(event, edgeId, edgeData);
                    },
                    onNodeDragStart: (nodeId) => {
                        callbacksRef.current.onNodeDragStart?.(nodeId);
                    },
                    onNodeDrag: (nodeId) => {
                        callbacksRef.current.onNodeDrag?.(nodeId);
                    },
                    onNodeDragEnd: (nodeId) => {
                        callbacksRef.current.onNodeDragEnd?.(nodeId);
                    },
                }
            );

            return () => {
                console.log("🧹 Destroying D3 GraphRenderer...");
                rendererRef.current?.destroy();
                rendererRef.current = null;
            };
            // eslint-disable-next-line react-hooks/exhaustive-deps
        }, []);

        // Update data when graph data changes
        useEffect(() => {
            if (rendererRef.current && graphData.nodes.length > 0) {
                rendererRef.current.updateData(graphData);
            }
        }, [graphData]);

        // Update selection highlighting
        useEffect(() => {
            rendererRef.current?.updateSelection(selectedNodes);
        }, [selectedNodes]);

        // Update edge selection highlighting
        useEffect(() => {
            rendererRef.current?.updateEdgeSelection(selectedEdge || null);
        }, [selectedEdge]);

        // Update cluster filter
        useEffect(() => {
            rendererRef.current?.updateClusterFilter(activeCluster);
        }, [activeCluster]);

        // Handle search result highlighting with pulse animation
        useEffect(() => {
            if (!containerRef.current || !graphData) return;

            const svg = d3.select(containerRef.current).select('svg');
            if (svg.empty()) return;

            // Cancel existing search animation
            if (pulseAnimationRef.current) {
                cancelAnimationFrame(pulseAnimationRef.current);
                pulseAnimationRef.current = null;
            }

            // Don't apply search highlights if neural overlay is active
            if (neuralOverlay) return;

            // Reset all nodes - use the actual data binding
            const nodeGroups = svg.select('.nodes').selectAll<SVGGElement, any>('.node-group');
            
            nodeGroups
                .classed('search-highlighted', false)
                .select('.node-circle')
                .interrupt()
                .attr('filter', null)
                .attr('transform', null);

            if (highlightedNodes.length === 0) return;

            const highlightSet = new Set(highlightedNodes);
            console.log(`✨ Highlighting ${highlightedNodes.length} nodes`);

            // Apply highlights by filtering on data
            nodeGroups
                .filter((d: any) => highlightSet.has(d.id))
                .classed('search-highlighted', true)
                .raise()
                .select('.node-circle')
                .attr('stroke', '#9AE66A')
                .attr('stroke-width', 4);

            // Pulse animation
            let scale = 1;
            let growing = true;

            const pulse = () => {
                scale += growing ? 0.012 : -0.012;
                if (scale >= 1.25) growing = false;
                if (scale <= 1) growing = true;

                svg.selectAll('.node-group.search-highlighted .node-circle')
                    .attr('transform', `scale(${scale})`);

                pulseAnimationRef.current = requestAnimationFrame(pulse);
            };

            pulseAnimationRef.current = requestAnimationFrame(pulse);

            return () => {
                if (pulseAnimationRef.current) {
                    cancelAnimationFrame(pulseAnimationRef.current);
                }
            };
        }, [highlightedNodes, graphData, neuralOverlay]);

        // ========================
        // NEURAL OVERLAY RENDERING
        // ========================

        useEffect(() => {
            if (!containerRef.current) return;

            const svg = d3.select(containerRef.current).select('svg');
            if (svg.empty()) return;

            // Cancel any existing neural animation
            if (neuralAnimationRef.current) {
                cancelAnimationFrame(neuralAnimationRef.current);
                neuralAnimationRef.current = null;
            }

            const nodeGroups = svg.select('.nodes').selectAll<SVGGElement, any>('.node-group');
            const edgeLines = svg.select('.edges').selectAll<SVGLineElement, any>('.edge');

            // Clear neural styling if no overlay
            if (!neuralOverlay) {
                nodeGroups
                    .classed('neural-dormant neural-entry neural-activated neural-contributing', false)
                    .each(function() {
                        const group = d3.select(this);
                        group.select('.node-circle')
                            .transition()
                            .duration(300)
                            .style('filter', null)
                            .style('opacity', null);
                        group.select('.node-glow')
                            .transition()
                            .duration(300)
                            .style('opacity', null);
                    });

                edgeLines
                    .classed('neural-propagation', false)
                    .transition()
                    .duration(300)
                    .style('filter', null)
                    .style('opacity', null);

                return;
            }

            console.log(`⚡ Applying neural overlay: ${neuralOverlay.nodeStates.size} node states`);

            // Apply node states - filter by data id
            nodeGroups.each(function(d: any) {
                const group = d3.select(this);
                const nodeId = d.id;
                const state = neuralOverlay.nodeStates.get(nodeId) || 'dormant';
                const signal = neuralOverlay.nodeSignals.get(nodeId) || 0;

                // Remove all neural classes first
                group.classed('neural-dormant neural-entry neural-activated neural-contributing', false);
                group.classed(`neural-${state}`, true);

                const circle = group.select('.node-circle');
                const glow = group.select('.node-glow');

                // Get color based on state
                const color = NEURAL_COLORS[state];
                const strokeWidth = state === 'dormant' ? 2 : 3 + signal * 3;
                const opacity = state === 'dormant' ? 0.25 : 1;
                const glowOpacity = state === 'dormant' ? 0.1 : 0.4 + signal * 0.4;
                const glowRadius = state === 'dormant' ? 0 : 4 + signal * 12;

                circle
                    .transition()
                    .duration(400)
                    .style('stroke', color)
                    .style('stroke-width', strokeWidth)
                    .style('opacity', opacity)
                    .style('filter', glowRadius > 0 
                        ? `drop-shadow(0 0 ${glowRadius}px ${color})` 
                        : null
                    );

                glow
                    .transition()
                    .duration(400)
                    .style('fill', color)
                    .style('opacity', glowOpacity)
                    .style('filter', state !== 'dormant' ? `blur(${12 + signal * 8}px)` : 'blur(8px)');
            });

            // Apply edge styling for propagation paths
            edgeLines.each(function(d: any) {
                const edge = d3.select(this);
                const sourceId = typeof d.source === 'object' ? d.source.id : d.source;
                const targetId = typeof d.target === 'object' ? d.target.id : d.target;

                // Check if this edge is in the propagation paths
                let isPropagationEdge = false;
                let edgeSignal = 0;

                neuralOverlay.propagationEdges.forEach((propEdge) => {
                    if ((sourceId === propEdge.source && targetId === propEdge.target) ||
                        (sourceId === propEdge.target && targetId === propEdge.source)) {
                        isPropagationEdge = true;
                        edgeSignal = propEdge.signal;
                    }
                });

                if (isPropagationEdge) {
                    edge.classed('neural-propagation', true);
                    edge
                        .transition()
                        .duration(400)
                        .style('stroke', NEURAL_COLORS.propagationEdge)
                        .style('stroke-width', 3 + edgeSignal * 3)
                        .style('stroke-opacity', 0.9)
                        .style('stroke-dasharray', 'none')
                        .style('filter', `drop-shadow(0 0 6px ${NEURAL_COLORS.propagationEdge})`);
                } else {
                    edge.classed('neural-propagation', false);
                    edge
                        .transition()
                        .duration(400)
                        .style('stroke-opacity', 0.15)
                        .style('filter', null);
                }
            });

            // Animated pulse for activated nodes
            let pulsePhase = 0;

            const animatePulse = () => {
                pulsePhase += 0.04;
                const pulseFactor = 1 + Math.sin(pulsePhase) * 0.08;

                svg.selectAll('.node-group.neural-entry .node-circle, .node-group.neural-activated .node-circle, .node-group.neural-contributing .node-circle')
                    .attr('transform', `scale(${pulseFactor})`);

                neuralAnimationRef.current = requestAnimationFrame(animatePulse);
            };

            neuralAnimationRef.current = requestAnimationFrame(animatePulse);

            return () => {
                if (neuralAnimationRef.current) {
                    cancelAnimationFrame(neuralAnimationRef.current);
                }
            };
        }, [neuralOverlay]);

        return (
            <div
                ref={containerRef}
                className="w-full h-full relative"
                style={{
                    overflow: "hidden",
                    background: "transparent",
                }}
            />
        );
    }
);

D3GraphCanvas.displayName = "D3GraphCanvas";