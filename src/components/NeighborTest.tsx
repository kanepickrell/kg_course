import React, { useEffect, useRef, useState } from "react";
import { Graphin } from "@antv/graphin";

const API_BASE = "http://localhost:8000";

export default function NeighborTest() {
    const graphRef = useRef<any>(null);
    const [graphData, setGraphData] = useState({ nodes: [], edges: [] });
    const [selectedNode, setSelectedNode] = useState<string | null>(null);

    // 1️⃣ Load the base graph once
    useEffect(() => {
        fetch(`${API_BASE}/graph`)
            .then(r => r.json())
            .then(data => {
                console.log("✅ Full graph loaded", data);
                setGraphData(data);
            })
            .catch(e => console.error("❌ Graph load failed", e));
    }, []);

    // 2️⃣ Handle Graphin init
    const handleInit = () => {
        const graph = graphRef.current;
        if (!graph) return;

        // Basic click listener with cross-version safe ID extraction
        graph.on("node:click", (evt: any) => {
            let id = evt?.item?.getModel?.()?.id || evt?.item?._cfg?.id;
            if (!id) return console.warn("⚠️ No ID in click event", evt);
            console.log("🖱️ Node clicked:", id);
            setSelectedNode(id);

            // Optional highlight
            graph.setItemState(evt.item, "active", true);
            setTimeout(() => graph.setItemState(evt.item, "active", false), 500);
        });
    };

    // 3️⃣ When a node is selected, call /neighbors
    useEffect(() => {
        if (!selectedNode) return;
        const nodeKey = selectedNode.replace("nodes/", "");
        const depth = 2;

        console.log(`🔍 Fetching neighbors of ${nodeKey} (depth=${depth})`);
        fetch(`${API_BASE}/neighbors/${nodeKey}?depth=${depth}`)
            .then(r => r.json())
            .then(data => {
                console.log("✅ Neighbor data:", data);
                setGraphData({ nodes: data.nodes, edges: data.edges });
            })
            .catch(e => console.error("❌ Neighbor fetch failed", e));
    }, [selectedNode]);

    return (
        <div className="h-screen w-screen bg-gray-50">
            <Graphin
                ref={graphRef}
                data={graphData}
                options={{
                    layout: { type: "d3-force", nodeStrength: -1200, linkDistance: 180 },
                    behaviors: ["zoom-canvas", "drag-canvas", "click-select", "drag-element"],
                    animation: true,
                }}
                onInit={handleInit}
            />
        </div>
    );
}
