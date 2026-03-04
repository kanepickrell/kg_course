import * as d3 from "d3";

export interface GraphNode {
    id: string;
    label: string;
    cluster: string;
    type: string;
    importance: number;
    size: number;
}

export interface GraphEdge {
    id: string;
    source: string;
    target: string;
    type: string;
    weight: number;
}

export interface GraphData {
    nodes: GraphNode[];
    edges: GraphEdge[];
}

export interface ClusterInfo {
    [key: string]: {
        name: string;
        color: string;
        description: string;
    };
}

interface SimNode extends d3.SimulationNodeDatum {
    id: string;
    label: string;
    cluster: string;
    type: string;
    importance: number;
    size: number;
}

interface SimLink extends d3.SimulationLinkDatum<SimNode> {
    id: string;
    type: string;
    weight: number;
    source: SimNode;
    target: SimNode;
}

interface GraphRendererCallbacks {
    onNodeClick: (event: MouseEvent, nodeId: string, nodeData: GraphNode) => void;
    onNodeDoubleClick: (event: MouseEvent, nodeId: string, nodeData: GraphNode) => void;
    onEdgeClick?: (event: MouseEvent, edgeId: string, edgeData: any) => void;
    onNodeDragStart?: (nodeId: string) => void;
    onNodeDrag?: (nodeId: string) => void;
    onNodeDragEnd?: (nodeId: string) => void;
}

export class GraphRenderer {
    private svg!: d3.Selection<SVGSVGElement, unknown, null, undefined>;
    private container: d3.Selection<SVGGElement, unknown, null, undefined>;
    private edgeLayer!: d3.Selection<SVGGElement, unknown, null, undefined>;
    private nodeLayer!: d3.Selection<SVGGElement, unknown, null, undefined>;
    private simulation!: d3.Simulation<SimNode, SimLink>;
    private zoom!: d3.ZoomBehavior<SVGSVGElement, unknown>;

    private tooltip: d3.Selection<HTMLDivElement, unknown, HTMLElement, any> | null = null;

    private nodes: SimNode[] = [];
    private links: SimLink[] = [];
    private width: number = 0;
    private height: number = 0;

    private selectedNodes: Set<string> = new Set();
    private selectedEdge: string | null = null;
    private activeCluster: string | null = null;
    private isDragging = false;

    constructor(
        private containerElement: HTMLDivElement,
        private clusterInfo: ClusterInfo,
        private callbacks: GraphRendererCallbacks
    ) {
        this.initialize();
    }

    private initialize() {
        const rect = this.containerElement.getBoundingClientRect();
        this.width = rect.width;
        this.height = rect.height;

        this.svg = d3
            .select(this.containerElement)
            .append("svg")
            .attr("width", "100%")
            .attr("height", "100%")
            .style("background", "transparent");

        this.setupBackground();

        this.container = this.svg.append("g").attr("class", "graph-container");
        this.edgeLayer = this.container.append("g").attr("class", "edges");
        this.nodeLayer = this.container.append("g").attr("class", "nodes");

        this.setupZoom();
        this.setupMiniMap();
        this.initializeTooltip();
        this.setupSimulation();

        // Click on background to deselect edge
        this.svg.on("click", (event) => {
            if (event.target === this.svg.node()) {
                // Clicked on SVG background - could trigger deselect
            }
        });
    }

    private setupBackground() {
        const defs = this.svg.append("defs");

        const pattern = defs
            .append("pattern")
            .attr("id", "dots-pattern")
            .attr("x", 0)
            .attr("y", 0)
            .attr("width", 20)
            .attr("height", 20)
            .attr("patternUnits", "userSpaceOnUse");

        pattern
            .append("circle")
            .attr("cx", 1)
            .attr("cy", 1)
            .attr("r", 0.5)
            .style("fill", "#2a2a2a");

        this.svg
            .insert("rect", ":first-child")
            .attr("width", "100%")
            .attr("height", "100%")
            .style("fill", "url(#dots-pattern)");
    }

    private setupZoom() {
        this.zoom = d3
            .zoom<SVGSVGElement, unknown>()
            .scaleExtent([0.1, 4])
            .on("zoom", (event) => {
                this.container.attr("transform", event.transform);
                this.updateMiniMap();
            });

        this.svg.call(this.zoom);
    }

    private setupMiniMap() {
        const minimap = this.svg
            .append("g")
            .attr("class", "minimap")
            .attr("transform", `translate(${this.width - 210}, 10)`);

        minimap
            .append("rect")
            .attr("class", "minimap-shadow")
            .attr("width", 200)
            .attr("height", 150)
            .attr("x", 2)
            .attr("y", 2)
            .attr("rx", 8)
            .style("fill", "#000");

        minimap
            .append("rect")
            .attr("class", "minimap-bg")
            .attr("width", 200)
            .attr("height", 150)
            .attr("rx", 8)
            .style("fill", "#1a1a1a")
            .style("stroke", "#000")
            .style("stroke-width", 2);

        minimap.append("g").attr("class", "minimap-content");

        minimap
            .append("rect")
            .attr("class", "minimap-viewport")
            .style("fill", "none")
            .style("stroke", "#667eea")
            .style("stroke-width", 2);
    }

    private updateMiniMap() {
        const minimapContent = this.svg.select<SVGGElement>(".minimap-content");
        const minimapViewport = this.svg.select<SVGRectElement>(".minimap-viewport");

        if (this.nodes.length === 0) return;

        const bounds = this.getGraphBounds();
        const graphWidth = bounds.maxX - bounds.minX;
        const graphHeight = bounds.maxY - bounds.minY;

        const minimapWidth = 200;
        const minimapHeight = 150;
        const padding = 10;
        const scale = Math.min(
            (minimapWidth - 2 * padding) / graphWidth,
            (minimapHeight - 2 * padding) / graphHeight
        );

        const minimapNodes = minimapContent
            .selectAll<SVGCircleElement, SimNode>(".minimap-node")
            .data(this.nodes, (d: any) => d.id);

        minimapNodes
            .enter()
            .append("circle")
            .attr("class", "minimap-node")
            .attr("r", 2)
            .merge(minimapNodes as any)
            .attr("cx", (d) => padding + ((d.x || 0) - bounds.minX) * scale)
            .attr("cy", (d) => padding + ((d.y || 0) - bounds.minY) * scale)
            .style("fill", (d) => this.clusterInfo[d.cluster]?.color || "#999");

        minimapNodes.exit().remove();

        const transform = d3.zoomTransform(this.svg.node()!);
        const viewportWidth = this.width / transform.k;
        const viewportHeight = this.height / transform.k;

        const viewportX =
            ((-transform.x / transform.k - bounds.minX) * scale) + padding;
        const viewportY =
            ((-transform.y / transform.k - bounds.minY) * scale) + padding;

        minimapViewport
            .attr("x", viewportX)
            .attr("y", viewportY)
            .attr("width", viewportWidth * scale)
            .attr("height", viewportHeight * scale);
    }

    private setupSimulation() {
        this.simulation = d3
            .forceSimulation<SimNode, SimLink>()
            .force(
                "link",
                d3
                    .forceLink<SimNode, SimLink>()
                    .id((d: any) => d.id)
                    .distance(200)
                    .strength(0.5)
            )
            .force("charge", d3.forceManyBody<SimNode>().strength(-500))
            .force("collision", d3.forceCollide<SimNode>().radius(50).strength(0.7))
            .force("center", d3.forceCenter(0, 0))
            .alphaDecay(0.0228)
            .velocityDecay(0.4)
            .on("tick", () => this.tick());
    }

    private tick() {
        this.edgeLayer
            .selectAll<SVGLineElement, SimLink>(".edge")
            .attr("x1", (d) => (d.source as SimNode).x || 0)
            .attr("y1", (d) => (d.source as SimNode).y || 0)
            .attr("x2", (d) => (d.target as SimNode).x || 0)
            .attr("y2", (d) => (d.target as SimNode).y || 0);

        // Also update hit areas
        this.edgeLayer
            .selectAll<SVGLineElement, SimLink>(".edge-hit-area")
            .attr("x1", (d) => (d.source as SimNode).x || 0)
            .attr("y1", (d) => (d.source as SimNode).y || 0)
            .attr("x2", (d) => (d.target as SimNode).x || 0)
            .attr("y2", (d) => (d.target as SimNode).y || 0);

        this.nodeLayer
            .selectAll<SVGGElement, SimNode>(".node-group")
            .attr("transform", (d) => `translate(${d.x || 0}, ${d.y || 0})`);

        this.updateMiniMap();
    }

    public updateData(data: GraphData) {
        const prevNodeMap = new Map<string, SimNode>(this.nodes.map((n) => [n.id, n]));

        this.nodes = data.nodes.map((n) => {
            const existing = prevNodeMap.get(n.id);
            return {
                id: n.id,
                label: n.label,
                cluster: n.cluster,
                type: n.type,
                importance: n.importance,
                size: n.size,
                x: existing?.x ?? Math.random() * 400 - 200,
                y: existing?.y ?? Math.random() * 400 - 200,
                vx: existing?.vx,
                vy: existing?.vy,
            } as SimNode;
        });

        const nodeById = new Map<string, SimNode>(this.nodes.map((n) => [n.id, n]));

        this.links = data.edges.map((e) => ({
            id: e.id,
            type: e.type,
            weight: e.weight,
            source: nodeById.get(e.source)!,
            target: nodeById.get(e.target)!,
        }));

        this.simulation.nodes(this.nodes);
        (this.simulation.force("link") as d3.ForceLink<SimNode, SimLink>).links(this.links);

        this.renderEdges();
        this.renderNodes();

        this.simulation.alpha(0.8).restart();

        setTimeout(() => this.fitView(), 800);
    }

    private renderEdges() {
        // First, render invisible wider hit areas for easier clicking
        const hitAreas = this.edgeLayer
            .selectAll<SVGLineElement, SimLink>(".edge-hit-area")
            .data(this.links, (d: any) => d.id);

        hitAreas
            .enter()
            .append("line")
            .attr("class", "edge-hit-area")
            .style("stroke", "transparent")
            .style("stroke-width", 20) // Wide hit area
            .style("cursor", "pointer")
            .on("click", (event: any, d) => this.handleEdgeClick(event, d))
            .on("mouseenter", (event: any, d) => this.handleEdgeHover(event, d))
            .on("mousemove", (event: any) => this.handleEdgeMove(event))
            .on("mouseleave", () => this.handleEdgeLeave());

        hitAreas.exit().remove();

        // Then render the visible edges
        const edges = this.edgeLayer
            .selectAll<SVGLineElement, SimLink>(".edge")
            .data(this.links, (d: any) => d.id);

        edges
            .enter()
            .append("line")
            .attr("class", "edge")
            .style("stroke", (d) => {
                const src = d.source as SimNode;
                const tgt = d.target as SimNode;
                return src.cluster !== tgt.cluster ? "#ff6b6b" : "#99ADD1";
            })
            .style("stroke-width", (d) => Math.max(2, (d.weight || 0.5) * 3))
            .style("stroke-opacity", (d) => {
                const src = d.source as SimNode;
                const tgt = d.target as SimNode;
                return src.cluster !== tgt.cluster ? 0.6 : 0.4;
            })
            .style("stroke-dasharray", (d) => {
                const src = d.source as SimNode;
                const tgt = d.target as SimNode;
                return src.cluster !== tgt.cluster ? "5,5" : "none";
            })
            .style("pointer-events", "none"); // Let hit area handle events

        edges.exit().remove();
        this.updateEdgeStyles();
    }

    private handleEdgeClick(event: MouseEvent, edge: SimLink) {
        event.stopPropagation();
        console.log("🔗 Edge clicked:", edge.id);
        
        if (this.callbacks.onEdgeClick) {
            this.callbacks.onEdgeClick(event, edge.id, {
                id: edge.id,
                type: edge.type,
                weight: edge.weight,
                source: (edge.source as SimNode).id,
                target: (edge.target as SimNode).id,
            });
        }
    }

    private renderNodes() {
        const nodes = this.nodeLayer
            .selectAll<SVGGElement, SimNode>(".node-group")
            .data(this.nodes, (d: any) => d.id);

        const nodesEnter = nodes
            .enter()
            .append("g")
            .attr("class", "node-group")
            .style("cursor", "pointer")
            .call(this.createDragBehavior());

        nodesEnter
            .append("circle")
            .attr("class", "node-glow")
            .attr("r", (d) => (d.size || 60) / 2 + 4)
            .style("fill", (d) => this.clusterInfo[d.cluster]?.color || "#999")
            .style("opacity", 0.3)
            .style("filter", "blur(8px)");

        nodesEnter
            .append("circle")
            .attr("class", "node-circle")
            .attr("r", (d) => (d.size || 60) / 2)
            .style("fill", (d) => this.clusterInfo[d.cluster]?.color || "#999")
            .style("stroke", "#000")
            .style("stroke-width", 2);

        const labels = nodesEnter
            .append("text")
            .attr("class", "node-label")
            .attr("text-anchor", "middle")
            .attr("dominant-baseline", "middle")
            .style("font-size", "9px")
            .style("font-weight", "700")
            .style("font-family", "system-ui, -apple-system, sans-serif")
            .style("fill", "#1a1a1a")
            .style("pointer-events", "none")
            .style("user-select", "none");

        labels.each(function (d: SimNode) {
            const text = d3.select(this as SVGTextElement);
            const words = d.label.split(/\s+/);
            const maxWidth = (d.size || 60) - 16;
            let line: string[] = [];
            let tspan = text.append("tspan").attr("x", 0).attr("y", 0);
            let lineNumber = 0;
            const lineHeight = 1.1;

            words.forEach((word) => {
                line.push(word);
                tspan.text(line.join(" "));
                if ((tspan.node() as any).getComputedTextLength() > maxWidth && line.length > 1) {
                    line.pop();
                    tspan.text(line.join(" "));
                    line = [word];
                    tspan = text
                        .append("tspan")
                        .attr("x", 0)
                        .attr("dy", lineHeight + "em")
                        .text(word);
                    lineNumber++;
                }
            });

            const totalHeight = lineNumber * lineHeight;
            text.attr("y", -totalHeight * 4.5);
        });

        nodesEnter.on("click", (event: any, d: SimNode) => {
            if (this.isDragging) return;
            event.stopPropagation?.();
            this.callbacks.onNodeClick(event as MouseEvent, d.id, d);
        });

        nodesEnter.on("dblclick", (event: any, d: SimNode) => {
            event.stopPropagation?.();
            this.callbacks.onNodeDoubleClick(event as MouseEvent, d.id, d);
        });

        nodes.merge(nodesEnter);
        nodes.exit().remove();

        this.updateNodeStyles();
    }

    private createDragBehavior() {
        return d3
            .drag<SVGGElement, SimNode>()
            .on("start", (event, d) => {
                this.isDragging = false;
                if (!event.active) this.simulation.alphaTarget(0.1).restart();
                d.fx = d.x;
                d.fy = d.y;
                this.callbacks.onNodeDragStart?.(d.id);
            })
            .on("drag", (event, d) => {
                this.isDragging = true;
                d.fx = event.x;
                d.fy = event.y;
                this.callbacks.onNodeDrag?.(d.id);
            })
            .on("end", (event, d) => {
                if (!event.active) this.simulation.alphaTarget(0);
                d.fx = null;
                d.fy = null;
                this.callbacks.onNodeDragEnd?.(d.id);
                setTimeout(() => (this.isDragging = false), 100);
            });
    }

    public updateSelection(selectedIds: string[]) {
        this.selectedNodes = new Set(selectedIds);
        this.updateNodeStyles();
        this.updateEdgeStyles();
    }

    public updateEdgeSelection(edgeId: string | null) {
        this.selectedEdge = edgeId;
        this.updateEdgeStyles();
    }

    public updateClusterFilter(activeCluster: string | null) {
        this.activeCluster = activeCluster;
        this.updateNodeStyles();
        this.updateEdgeStyles();
    }

    private updateNodeStyles() {
        this.nodeLayer
            .selectAll<SVGGElement, SimNode>(".node-group")
            .each((d, i, nodes) => {
                const group = d3.select(nodes[i]);
                const isSelected = this.selectedNodes.has(d.id);
                const isInActiveCluster = !this.activeCluster || d.cluster === this.activeCluster;
                const isDimmed = this.activeCluster && !isInActiveCluster;
                const cluster = this.clusterInfo[d.cluster];

                group.style("display", "block");

                group
                    .select<SVGCircleElement>(".node-circle")
                    .style("stroke", isSelected ? "#667eea" : "#000")
                    .style("stroke-width", isSelected ? 4 : 2)
                    .transition()
                    .duration(200)
                    .style("opacity", isDimmed ? 0.4 : 1);

                group
                    .select<SVGCircleElement>(".node-glow")
                    .transition()
                    .duration(200)
                    .attr("r", isSelected ? (d.size || 60) / 2 + 15 : (d.size || 60) / 2 + 4)
                    .style("fill", isSelected ? "#667eea" : cluster?.color || "#999")
                    .style("opacity", isSelected ? 0.8 : isDimmed ? 0.15 : 0.3)
                    .style("filter", isSelected ? "blur(25px)" : "blur(8px)");

                group
                    .select<SVGTextElement>(".node-label")
                    .transition()
                    .duration(200)
                    .style("opacity", isDimmed ? 0.5 : 1);
            });
    }

    private updateEdgeStyles() {
        this.edgeLayer
            .selectAll<SVGLineElement, SimLink>(".edge")
            .each((d, i, edges) => {
                const edge = d3.select(edges[i]);
                const isSelected = this.selectedEdge === d.id;
                const src = d.source as SimNode;
                const tgt = d.target as SimNode;
                const isCrossCluster = src.cluster !== tgt.cluster;

                // Determine base opacity
                let opacity = isCrossCluster ? 0.6 : 0.4;
                if (this.activeCluster) {
                    const inCluster = src.cluster === this.activeCluster || tgt.cluster === this.activeCluster;
                    opacity = inCluster ? (isCrossCluster ? 0.75 : 0.55) : 0.25;
                }

                // Apply selected edge styles
                if (isSelected) {
                    edge
                        .style("stroke", "#00d4ff")
                        .style("stroke-width", 5)
                        .style("stroke-opacity", 1)
                        .style("stroke-dasharray", "none")
                        .style("filter", "drop-shadow(0 0 8px #00d4ff)");
                } else {
                    edge
                        .transition()
                        .duration(200)
                        .style("stroke", isCrossCluster ? "#ff6b6b" : "#99ADD1")
                        .style("stroke-width", Math.max(2, (d.weight || 0.5) * 3))
                        .style("stroke-opacity", opacity)
                        .style("stroke-dasharray", isCrossCluster ? "5,5" : "none")
                        .style("filter", "none");
                }
            });
    }

    public fitView(duration: number = 800) {
        if (this.nodes.length === 0) return;

        const bounds = this.getGraphBounds();
        const width = bounds.maxX - bounds.minX;
        const height = bounds.maxY - bounds.minY;
        const centerX = (bounds.minX + bounds.maxX) / 2;
        const centerY = (bounds.minY + bounds.maxY) / 2;

        const scale = Math.min(
            this.width / (width + 200),
            this.height / (height + 200),
            1.2
        );

        const transform = d3.zoomIdentity
            .translate(this.width / 2, this.height / 2)
            .scale(scale)
            .translate(-centerX, -centerY);

        this.svg.transition().duration(duration).call(this.zoom.transform, transform);
    }

    public focusNode(nodeId: string, duration: number = 800) {
        const node = this.nodes.find((n) => n.id === nodeId);
        if (!node) return;

        const transform = d3.zoomIdentity
            .translate(this.width / 2, this.height / 2)
            .scale(1.2)
            .translate(-node.x!, -node.y!);

        this.svg.transition().duration(duration).call(this.zoom.transform, transform);
    }

    private getGraphBounds() {
        const xs = this.nodes.map((n) => n.x || 0);
        const ys = this.nodes.map((n) => n.y || 0);

        return {
            minX: Math.min(...xs),
            maxX: Math.max(...xs),
            minY: Math.min(...ys),
            maxY: Math.max(...ys),
        };
    }

    private initializeTooltip(): void {
        d3.select("body").select(".edge-tooltip").remove();

        this.tooltip = d3.select("body")
            .append("div")
            .attr("class", "edge-tooltip")
            .style("position", "absolute")
            .style("visibility", "hidden")
            .style("background-color", "rgba(0, 0, 0, 0.9)")
            .style("color", "#fff")
            .style("padding", "8px 12px")
            .style("border-radius", "6px")
            .style("font-size", "12px")
            .style("font-weight", "600")
            .style("pointer-events", "none")
            .style("z-index", "10000")
            .style("box-shadow", "0 4px 6px rgba(0, 0, 0, 0.3)")
            .style("border", "2px solid #00d4ff")
            .style("font-family", "system-ui, -apple-system, sans-serif");
    }

    private handleEdgeHover(event: MouseEvent, edge: SimLink): void {
        if (!this.tooltip) return;

        // Don't change styles if this edge is selected
        if (this.selectedEdge !== edge.id) {
            d3.select(event.target as SVGLineElement)
                .each((d, i, nodes) => {
                    // Find the corresponding visible edge line
                    this.edgeLayer
                        .selectAll<SVGLineElement, SimLink>(".edge")
                        .filter((e) => e.id === edge.id)
                        .attr("stroke", "#00d4ff")
                        .attr("stroke-width", 4)
                        .attr("opacity", 1);
                });
        }

        const type = this.formatRelationshipType(edge.type);
        const src = edge.source as SimNode;
        const tgt = edge.target as SimNode;

        const content = `
            <div style="margin-bottom: 4px;">
                <strong style="color: #00d4ff; font-size: 13px;">${type}</strong>
            </div>
            <div style="font-size: 11px; opacity: 0.9; margin-bottom: 2px;">
                ${src.label} → ${tgt.label}
            </div>
            <div style="font-size: 10px; opacity: 0.7; margin-top: 4px;">
                Weight: ${(edge.weight * 100).toFixed(0)}%
            </div>
            <div style="font-size: 9px; opacity: 0.5; margin-top: 4px; font-style: italic;">
                Click to select
            </div>
        `;

        this.tooltip.html(content).style("visibility", "visible");
        this.handleEdgeMove(event);
    }

    private handleEdgeMove(event: MouseEvent): void {
        if (!this.tooltip) return;

        const tooltipNode = this.tooltip.node();
        if (!tooltipNode) return;

        const tooltipWidth = tooltipNode.offsetWidth;
        const tooltipHeight = tooltipNode.offsetHeight;

        let left = event.pageX + 15;
        let top = event.pageY - tooltipHeight - 15;

        if (left + tooltipWidth > window.innerWidth) {
            left = event.pageX - tooltipWidth - 15;
        }

        if (top < 0) {
            top = event.pageY + 15;
        }

        this.tooltip.style("left", `${left}px`).style("top", `${top}px`);
    }

    private handleEdgeLeave(): void {
        if (!this.tooltip) return;

        this.tooltip.style("visibility", "hidden");

        // Reset edge styles (but preserve selected edge)
        this.updateEdgeStyles();
    }

    private formatRelationshipType(type: string): string {
        return type
            .replace(/_/g, " ")
            .replace(/([A-Z])/g, " $1")
            .split(" ")
            .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
            .join(" ")
            .trim();
    }

    public destroy() {
        if (this.tooltip) {
            this.tooltip.remove();
        }
        this.simulation.stop();
        this.svg.remove();
    }
}