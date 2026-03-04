/**
 * React Flow Integration for Neural Routing Visualization
 * ========================================================
 * 
 * Helpers to apply neural routing overlay styles to your React Flow graph.
 * 
 * Usage in your GraphExplorer:
 * 
 * ```tsx
 * import { useNeuralOverlay, applyNeuralOverlay } from './neuralOverlayHelpers';
 * 
 * function GraphExplorer() {
 *   const [nodes, setNodes] = useNodesState(initialNodes);
 *   const [edges, setEdges] = useEdgesState(initialEdges);
 *   const { overlayStyles, runExperiment, ... } = useNeuralOverlay();
 *   
 *   // Apply overlay when it changes
 *   useEffect(() => {
 *     if (overlayStyles) {
 *       const { styledNodes, styledEdges } = applyNeuralOverlay(
 *         nodes, edges, overlayStyles, nodeToAgentMap
 *       );
 *       setNodes(styledNodes);
 *       setEdges(styledEdges);
 *     }
 *   }, [overlayStyles]);
 * }
 * ```
 */

import { Node, Edge, MarkerType } from 'reactflow';

// Types from NeuralExperimentVisualizer
interface NodeOverlayStyle {
  glowColor?: string;
  glowIntensity?: number;
  opacity?: number;
  scale?: number;
  borderColor?: string;
  borderWidth?: number;
  pulsing?: boolean;
}

interface EdgeOverlayStyle {
  color?: string;
  width?: number;
  animated?: boolean;
  opacity?: number;
  dashArray?: string;
}

interface AgentHighlight {
  agent_id: string;
  state: 'dormant' | 'entry' | 'activated' | 'contributing';
  signal: number;
  hop: number;
}

interface OverlayStyles {
  nodeStyles: Record<string, NodeOverlayStyle>;
  edgeStyles: Record<string, EdgeOverlayStyle>;
  agentHighlights: Record<string, AgentHighlight>;
}

// Activation colors
const ACTIVATION_COLORS = {
  dormant: '#4B5563',
  entry: '#F59E0B',
  activated: '#3B82F6',
  contributing: '#10B981',
  propagation: '#8B5CF6',
};

/**
 * Apply neural overlay styles to React Flow nodes and edges
 */
export function applyNeuralOverlay(
  nodes: Node[],
  edges: Edge[],
  overlayStyles: OverlayStyles,
  nodeToAgent: Record<string, string>,
  options: {
    dimDormant?: boolean;
    showAgentBoundaries?: boolean;
  } = {}
): { styledNodes: Node[]; styledEdges: Edge[] } {
  const { dimDormant = true, showAgentBoundaries = true } = options;

  // Style nodes
  const styledNodes = nodes.map(node => {
    const nodeStyle = overlayStyles.nodeStyles[node.id];
    const agentId = nodeToAgent[node.id];
    const agentHighlight = agentId ? overlayStyles.agentHighlights[agentId] : null;

    // Default styles
    let style: React.CSSProperties = { ...node.style };

    if (nodeStyle) {
      // Active node - apply highlight
      style = {
        ...style,
        boxShadow: nodeStyle.glowColor 
          ? `0 0 ${10 + (nodeStyle.glowIntensity || 0) * 20}px ${nodeStyle.glowColor}`
          : undefined,
        border: nodeStyle.borderColor 
          ? `${nodeStyle.borderWidth || 2}px solid ${nodeStyle.borderColor}`
          : undefined,
        transform: nodeStyle.scale 
          ? `scale(${nodeStyle.scale})`
          : undefined,
        opacity: nodeStyle.opacity ?? 1,
        transition: 'all 0.3s ease-out',
      };

      // Add pulsing animation class via className
      if (nodeStyle.pulsing) {
        return {
          ...node,
          style,
          className: `${node.className || ''} neural-pulse`,
          data: {
            ...node.data,
            _neuralState: agentHighlight?.state,
            _neuralSignal: agentHighlight?.signal,
          },
        };
      }
    } else if (dimDormant && agentHighlight?.state === 'dormant') {
      // Dormant node - dim it
      style = {
        ...style,
        opacity: 0.3,
        filter: 'grayscale(50%)',
        transition: 'all 0.3s ease-out',
      };
    }

    return {
      ...node,
      style,
      data: {
        ...node.data,
        _neuralState: agentHighlight?.state,
        _neuralSignal: agentHighlight?.signal,
        _agentId: agentId,
      },
    };
  });

  // Style edges
  const styledEdges = edges.map(edge => {
    // Check if this edge is part of propagation path
    // The edge key format from the backend is "sourceAgent_targetAgent"
    // We need to check if source/target nodes belong to those agents
    
    const sourceAgent = nodeToAgent[edge.source];
    const targetAgent = nodeToAgent[edge.target];
    const propKey = `${sourceAgent}_${targetAgent}`;
    const propStyle = overlayStyles.edgeStyles[propKey];

    if (propStyle) {
      return {
        ...edge,
        animated: propStyle.animated,
        style: {
          stroke: propStyle.color || ACTIVATION_COLORS.propagation,
          strokeWidth: propStyle.width || 2,
          opacity: propStyle.opacity ?? 1,
        },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: propStyle.color || ACTIVATION_COLORS.propagation,
        },
      };
    }

    // Check if both endpoints are activated
    const sourceHighlight = sourceAgent ? overlayStyles.agentHighlights[sourceAgent] : null;
    const targetHighlight = targetAgent ? overlayStyles.agentHighlights[targetAgent] : null;
    
    const sourceActive = sourceHighlight && sourceHighlight.state !== 'dormant';
    const targetActive = targetHighlight && targetHighlight.state !== 'dormant';

    if (sourceActive && targetActive) {
      // Edge between two activated clusters - subtle highlight
      return {
        ...edge,
        style: {
          ...edge.style,
          stroke: '#6B7280',
          strokeWidth: 1.5,
          opacity: 0.7,
        },
      };
    } else if (sourceActive || targetActive) {
      // Edge from active to dormant - dim
      return {
        ...edge,
        style: {
          ...edge.style,
          opacity: 0.3,
        },
      };
    } else {
      // Both dormant - very dim
      return {
        ...edge,
        style: {
          ...edge.style,
          opacity: 0.15,
        },
      };
    }
  });

  return { styledNodes, styledEdges };
}


/**
 * Create agent boundary nodes for visualization
 * These are invisible nodes that group cluster members
 */
export function createAgentBoundaryNodes(
  agents: Array<{
    agent_id: string;
    node_ids: string[];
    keywords: string[];
  }>,
  existingNodes: Node[],
  overlayStyles: OverlayStyles
): Node[] {
  const nodePositions = new Map(
    existingNodes.map(n => [n.id, { x: n.position.x, y: n.position.y }])
  );

  return agents.map(agent => {
    const highlight = overlayStyles.agentHighlights[agent.agent_id];
    const color = ACTIVATION_COLORS[highlight?.state || 'dormant'];

    // Calculate bounding box of all nodes in this agent
    const positions = agent.node_ids
      .map(id => nodePositions.get(id))
      .filter(Boolean) as { x: number; y: number }[];

    if (positions.length === 0) {
      return null;
    }

    const minX = Math.min(...positions.map(p => p.x)) - 50;
    const maxX = Math.max(...positions.map(p => p.x)) + 50;
    const minY = Math.min(...positions.map(p => p.y)) - 30;
    const maxY = Math.max(...positions.map(p => p.y)) + 30;

    return {
      id: `boundary_${agent.agent_id}`,
      type: 'group',
      position: { x: minX, y: minY },
      style: {
        width: maxX - minX + 100,
        height: maxY - minY + 60,
        backgroundColor: `${color}10`,
        border: `2px dashed ${color}40`,
        borderRadius: 12,
        zIndex: -1,
      },
      data: {
        label: agent.agent_id,
        keywords: agent.keywords,
        state: highlight?.state,
      },
      selectable: false,
      draggable: false,
    };
  }).filter(Boolean) as Node[];
}


/**
 * CSS styles for neural overlay animations
 * Add this to your global CSS or as a style tag
 */
export const neuralOverlayStyles = `
  @keyframes neural-pulse {
    0%, 100% {
      transform: scale(1);
      box-shadow: 0 0 10px currentColor;
    }
    50% {
      transform: scale(1.05);
      box-shadow: 0 0 25px currentColor;
    }
  }

  .neural-pulse {
    animation: neural-pulse 1.5s ease-in-out infinite;
  }

  @keyframes neural-flow {
    0% {
      stroke-dashoffset: 24;
    }
    100% {
      stroke-dashoffset: 0;
    }
  }

  .react-flow__edge.animated path {
    stroke-dasharray: 5;
    animation: neural-flow 0.5s linear infinite;
  }

  /* Agent boundary hover effect */
  .agent-boundary:hover {
    background-color: rgba(255, 255, 255, 0.05) !important;
  }

  /* Legend styles */
  .neural-legend {
    display: flex;
    gap: 16px;
    padding: 8px 16px;
    background: rgba(17, 24, 39, 0.9);
    border-radius: 8px;
    font-size: 12px;
  }

  .neural-legend-item {
    display: flex;
    align-items: center;
    gap: 6px;
    color: #9CA3AF;
  }

  .neural-legend-dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
  }
`;


/**
 * Legend component showing activation states
 */
export function NeuralLegend() {
  return (
    <div className="neural-legend">
      <div className="neural-legend-item">
        <div className="neural-legend-dot" style={{ backgroundColor: ACTIVATION_COLORS.entry }} />
        <span>Entry Point</span>
      </div>
      <div className="neural-legend-item">
        <div className="neural-legend-dot" style={{ backgroundColor: ACTIVATION_COLORS.activated }} />
        <span>Activated</span>
      </div>
      <div className="neural-legend-item">
        <div className="neural-legend-dot" style={{ backgroundColor: ACTIVATION_COLORS.contributing }} />
        <span>Contributing</span>
      </div>
      <div className="neural-legend-item">
        <div className="neural-legend-dot" style={{ backgroundColor: ACTIVATION_COLORS.propagation }} />
        <span>Propagation</span>
      </div>
      <div className="neural-legend-item">
        <div className="neural-legend-dot" style={{ backgroundColor: ACTIVATION_COLORS.dormant }} />
        <span>Dormant</span>
      </div>
    </div>
  );
}


export { ACTIVATION_COLORS };
