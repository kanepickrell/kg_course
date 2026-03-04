import { useState, useEffect, useRef } from "react";
import * as d3 from "d3";
import {
  Search,
  Loader2,
  ChevronRight,
  Database,
  GitBranch,
  Clock,
  Zap,
  Code,
  MessageSquare,
  Sparkles,
  Copy,
  Check,
  AlertTriangle,
  ChevronDown,
} from "lucide-react";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

// =====================================================
// TYPES
// =====================================================

interface QueryResult {
  success: boolean;
  question: string;
  sparql?: string;
  results: Record<string, any>[];
  result_count: number;
  answer?: string;
  timing_ms: number;
  error?: string;
}

interface ExampleCategory {
  category: string;
  questions: string[];
}

interface ConversationEntry {
  id: string;
  type: "question" | "answer";
  content: string;
  sparql?: string;
  results?: Record<string, any>[];
  resultCount?: number;
  timingMs?: number;
  error?: string;
  timestamp: Date;
  subgraph?: SubgraphData | null;
}

interface SubgraphNode {
  id: string;
  label: string;
  type: string;
  color: string;
  highlighted: boolean;
  x?: number;
  y?: number;
  vx?: number;
  vy?: number;
}

interface SubgraphEdge {
  id: string;
  source: string | SubgraphNode;
  target: string | SubgraphNode;
  type: string;
}

interface SubgraphData {
  nodes: SubgraphNode[];
  edges: SubgraphEdge[];
  highlighted_count: number;
  total_count: number;
}

// =====================================================
// MAIN COMPONENT
// =====================================================

export default function IntelligenceConsole() {
  const [query, setQuery] = useState("");
  const [isQuerying, setIsQuerying] = useState(false);
  const [conversation, setConversation] = useState<ConversationEntry[]>([]);
  const [examples, setExamples] = useState<ExampleCategory[]>([]);
  const [expandedSparql, setExpandedSparql] = useState<Set<string>>(new Set());
  const [expandedResults, setExpandedResults] = useState<Set<string>>(new Set());
  const [expandedGraphs, setExpandedGraphs] = useState<Set<string>>(new Set());
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const inputRef = useRef<HTMLInputElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchExamples();
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [conversation]);

  const fetchExamples = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/query/examples`);
      if (res.ok) {
        const data = await res.json();
        setExamples(data.examples || []);
      }
    } catch (err) {
      console.error("Failed to fetch examples:", err);
    }
  };

  const handleQuery = async (questionText?: string) => {
    const q = questionText || query.trim();
    if (!q || isQuerying) return;

    const questionId = `q-${Date.now()}`;
    const answerId = `a-${Date.now()}`;

    // Add question to conversation
    setConversation((prev) => [
      ...prev,
      {
        id: questionId,
        type: "question",
        content: q,
        timestamp: new Date(),
      },
    ]);

    setQuery("");
    setIsQuerying(true);

    try {
      const res = await fetch(`${API_BASE}/api/query/natural`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q, show_sparql: true }),
      });

      const data: QueryResult = await res.json();

      // Fetch subgraph for visualization
      let subgraph: SubgraphData | null = null;
      if (data.success && data.results && data.results.length > 0) {
        try {
          const sgRes = await fetch(`${API_BASE}/api/query/subgraph`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ results: data.results }),
          });
          if (sgRes.ok) {
            const sgData = await sgRes.json();
            if (sgData.nodes && sgData.nodes.length > 0) {
              subgraph = sgData;
            }
          }
        } catch (err) {
          console.warn("Subgraph fetch failed:", err);
        }
      }

      setConversation((prev) => [
        ...prev,
        {
          id: answerId,
          type: "answer",
          content: data.answer || data.error || "No response",
          sparql: data.sparql,
          results: data.results,
          resultCount: data.result_count,
          timingMs: data.timing_ms,
          error: data.error,
          timestamp: new Date(),
          subgraph,
        },
      ]);
    } catch (err: any) {
      setConversation((prev) => [
        ...prev,
        {
          id: answerId,
          type: "answer",
          content: "Failed to reach the query engine.",
          error: err.message,
          timestamp: new Date(),
        },
      ]);
    } finally {
      setIsQuerying(false);
      inputRef.current?.focus();
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleQuery();
    }
  };

  const toggleSparql = (id: string) => {
    setExpandedSparql((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const toggleResults = (id: string) => {
    setExpandedResults((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const toggleGraph = (id: string) => {
    setExpandedGraphs((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const copySparql = (id: string, sparql: string) => {
    navigator.clipboard.writeText(sparql);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const hasConversation = conversation.length > 0;

  return (
    <div className="h-full flex flex-col bg-[#080808]">
      {/* Header */}
      <div className="border-b border-[#1a1a1a] bg-[#0a0a0a] px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded bg-[#6EBE46]/10 flex items-center justify-center">
              <Zap className="w-4 h-4 text-[#6EBE46]" />
            </div>
            <div>
              <h1
                className="text-base font-bold text-white tracking-wide"
                style={{ fontFamily: "'Rajdhani', sans-serif" }}
              >
                Intelligence Console
              </h1>
              <p
                className="text-[10px] text-[#444] tracking-widest uppercase"
                style={{ fontFamily: "'JetBrains Mono', monospace" }}
              >
                Natural Language → SPARQL → Knowledge Graph
              </p>
            </div>
          </div>
          <div
            className="flex items-center gap-4 text-[10px] text-[#333]"
            style={{ fontFamily: "'JetBrains Mono', monospace" }}
          >
            <span className="flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-[#6EBE46] animate-pulse" />
              GraphDB Connected
            </span>
            <span>PROTOGRAPH • ATLAS</span>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Conversation Panel */}
        <div className="flex-1 flex flex-col">
          <div ref={scrollRef} className="flex-1 overflow-y-auto">
            {!hasConversation ? (
              /* Empty State */
              <div className="flex flex-col items-center justify-center h-full px-8">
                <div className="w-16 h-16 rounded-xl bg-[#6EBE46]/5 border border-[#6EBE46]/10 flex items-center justify-center mb-6">
                  <Database className="w-8 h-8 text-[#6EBE46]/40" />
                </div>
                <h2
                  className="text-xl font-bold text-white mb-2"
                  style={{ fontFamily: "'Rajdhani', sans-serif" }}
                >
                  Query Your Knowledge Graph
                </h2>
                <p className="text-sm text-[#555] text-center max-w-md mb-8">
                  Ask questions in plain English. The system translates to SPARQL,
                  queries GraphDB, and returns precise answers from your ontology.
                </p>

                {/* Example Categories */}
                <div className="grid grid-cols-2 gap-3 w-full max-w-2xl">
                  {examples.map((cat) => (
                    <div
                      key={cat.category}
                      className="p-3 bg-[#0e0e0e] border border-[#1a1a1a] rounded-lg"
                    >
                      <h3
                        className="text-[10px] font-bold text-[#6EBE46]/60 uppercase tracking-wider mb-2"
                        style={{ fontFamily: "'JetBrains Mono', monospace" }}
                      >
                        {cat.category}
                      </h3>
                      <div className="space-y-1.5">
                        {cat.questions.map((q, i) => (
                          <button
                            key={i}
                            onClick={() => handleQuery(q)}
                            className="w-full text-left px-2.5 py-1.5 text-xs text-[#666] hover:text-white hover:bg-[#6EBE46]/5 rounded transition-all group"
                          >
                            <span className="text-[#333] group-hover:text-[#6EBE46] mr-1.5">→</span>
                            {q}
                          </button>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              /* Conversation Thread */
              <div className="max-w-3xl mx-auto py-6 px-4 space-y-4">
                {conversation.map((entry) =>
                  entry.type === "question" ? (
                    /* User Question */
                    <div key={entry.id} className="flex justify-end">
                      <div className="bg-[#6EBE46]/10 border border-[#6EBE46]/20 rounded-lg px-4 py-2.5 max-w-lg">
                        <p className="text-sm text-white">{entry.content}</p>
                      </div>
                    </div>
                  ) : (
                    /* System Answer */
                    <div key={entry.id} className="space-y-2">
                      {/* Answer text */}
                      <div className="bg-[#111] border border-[#1a1a1a] rounded-lg px-4 py-3">
                        {entry.error ? (
                          <div className="flex items-start gap-2">
                            <AlertTriangle className="w-4 h-4 text-red-400 flex-shrink-0 mt-0.5" />
                            <p className="text-sm text-red-300">{entry.content}</p>
                          </div>
                        ) : (
                          <p className="text-sm text-[#ccc] leading-relaxed">{entry.content}</p>
                        )}

                        {/* Metadata bar */}
                        <div className="flex items-center gap-3 mt-3 pt-2 border-t border-[#1a1a1a]">
                          {entry.timingMs !== undefined && (
                            <span className="flex items-center gap-1 text-[10px] text-[#444]">
                              <Clock className="w-3 h-3" />
                              {entry.timingMs}ms
                            </span>
                          )}
                          {entry.resultCount !== undefined && (
                            <span className="flex items-center gap-1 text-[10px] text-[#444]">
                              <Database className="w-3 h-3" />
                              {entry.resultCount} results
                            </span>
                          )}
                          {entry.sparql && (
                            <button
                              onClick={() => toggleSparql(entry.id)}
                              className="flex items-center gap-1 text-[10px] text-[#555] hover:text-[#6EBE46] transition-colors"
                            >
                              <Code className="w-3 h-3" />
                              {expandedSparql.has(entry.id) ? "Hide" : "Show"} SPARQL
                            </button>
                          )}
                          {entry.results && entry.results.length > 0 && (
                            <button
                              onClick={() => toggleResults(entry.id)}
                              className="flex items-center gap-1 text-[10px] text-[#555] hover:text-[#6EBE46] transition-colors"
                            >
                              <GitBranch className="w-3 h-3" />
                              {expandedResults.has(entry.id) ? "Hide" : "Show"} Data
                            </button>
                          )}
                          {entry.subgraph && entry.subgraph.nodes.length > 0 && (
                            <button
                              onClick={() => toggleGraph(entry.id)}
                              className="flex items-center gap-1 text-[10px] text-[#555] hover:text-[#6EBE46] transition-colors"
                            >
                              <Zap className="w-3 h-3" />
                              {expandedGraphs.has(entry.id) ? "Hide" : "Show"} Graph
                              <span className="text-[9px] text-[#333]">
                                ({entry.subgraph.highlighted_count}/{entry.subgraph.total_count})
                              </span>
                            </button>
                          )}
                        </div>
                      </div>

                      {/* Expandable SPARQL */}
                      {entry.sparql && expandedSparql.has(entry.id) && (
                        <div className="bg-[#0a0a0a] border border-[#1a1a1a] rounded-lg overflow-hidden">
                          <div className="flex items-center justify-between px-3 py-1.5 bg-[#0e0e0e] border-b border-[#1a1a1a]">
                            <span
                              className="text-[10px] text-[#444] uppercase tracking-wider"
                              style={{ fontFamily: "'JetBrains Mono', monospace" }}
                            >
                              Generated SPARQL
                            </span>
                            <button
                              onClick={() => copySparql(entry.id, entry.sparql!)}
                              className="flex items-center gap-1 text-[10px] text-[#555] hover:text-white"
                            >
                              {copiedId === entry.id ? (
                                <Check className="w-3 h-3 text-[#6EBE46]" />
                              ) : (
                                <Copy className="w-3 h-3" />
                              )}
                            </button>
                          </div>
                          <pre
                            className="p-3 text-xs text-[#8B8B8B] overflow-x-auto"
                            style={{ fontFamily: "'JetBrains Mono', monospace" }}
                          >
                            {entry.sparql}
                          </pre>
                        </div>
                      )}

                      {/* Expandable Results Table */}
                      {entry.results && entry.results.length > 0 && expandedResults.has(entry.id) && (
                        <div className="bg-[#0a0a0a] border border-[#1a1a1a] rounded-lg overflow-hidden">
                          <div className="px-3 py-1.5 bg-[#0e0e0e] border-b border-[#1a1a1a]">
                            <span
                              className="text-[10px] text-[#444] uppercase tracking-wider"
                              style={{ fontFamily: "'JetBrains Mono', monospace" }}
                            >
                              Query Results ({entry.results.length})
                            </span>
                          </div>
                          <div className="overflow-x-auto">
                            <table className="w-full text-xs">
                              <thead>
                                <tr className="border-b border-[#1a1a1a]">
                                  {Object.keys(entry.results[0]).map((key) => (
                                    <th
                                      key={key}
                                      className="px-3 py-2 text-left text-[10px] text-[#555] font-medium uppercase tracking-wider"
                                      style={{ fontFamily: "'JetBrains Mono', monospace" }}
                                    >
                                      {key}
                                    </th>
                                  ))}
                                </tr>
                              </thead>
                              <tbody>
                                {entry.results.slice(0, 15).map((row, i) => (
                                  <tr key={i} className="border-b border-[#111] hover:bg-[#111]">
                                    {Object.values(row).map((val, j) => (
                                      <td key={j} className="px-3 py-1.5 text-[#888]">
                                        {formatCellValue(String(val || ""))}
                                      </td>
                                    ))}
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </div>
                      )}

                      {/* Expandable Graph Visualization */}
                      {entry.subgraph && entry.subgraph.nodes.length > 0 && expandedGraphs.has(entry.id) && (
                        <div className="bg-[#0a0a0a] border border-[#1a1a1a] rounded-lg overflow-hidden">
                          <div className="flex items-center justify-between px-3 py-1.5 bg-[#0e0e0e] border-b border-[#1a1a1a]">
                            <span
                              className="text-[10px] text-[#444] uppercase tracking-wider"
                              style={{ fontFamily: "'JetBrains Mono', monospace" }}
                            >
                              Subgraph • {entry.subgraph.highlighted_count} matched • {entry.subgraph.total_count} total
                            </span>
                            <div className="flex items-center gap-3">
                              {/* Legend */}
                              {Array.from(new Set(entry.subgraph.nodes.map((n) => n.type))).slice(0, 5).map((type) => {
                                const node = entry.subgraph!.nodes.find((n) => n.type === type);
                                return (
                                  <span key={type} className="flex items-center gap-1 text-[9px] text-[#555]">
                                    <span
                                      className="w-2 h-2 rounded-full"
                                      style={{ backgroundColor: node?.color || "#555" }}
                                    />
                                    {type}
                                  </span>
                                );
                              })}
                            </div>
                          </div>
                          <MiniGraph
                            nodes={entry.subgraph.nodes}
                            edges={entry.subgraph.edges}
                          />
                        </div>
                      )}
                    </div>
                  )
                )}

                {/* Loading indicator */}
                {isQuerying && (
                  <div className="flex items-center gap-2 px-4 py-3">
                    <div className="flex gap-1">
                      <span className="w-1.5 h-1.5 rounded-full bg-[#6EBE46] animate-bounce" style={{ animationDelay: "0ms" }} />
                      <span className="w-1.5 h-1.5 rounded-full bg-[#6EBE46] animate-bounce" style={{ animationDelay: "150ms" }} />
                      <span className="w-1.5 h-1.5 rounded-full bg-[#6EBE46] animate-bounce" style={{ animationDelay: "300ms" }} />
                    </div>
                    <span className="text-xs text-[#444]">Generating SPARQL & querying graph...</span>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Input Bar */}
          <div className="border-t border-[#1a1a1a] bg-[#0a0a0a] px-4 py-3">
            <div className="max-w-3xl mx-auto flex items-center gap-3">
              <div className="flex-1 relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#333]" />
                <input
                  ref={inputRef}
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Ask a question about your knowledge graph..."
                  disabled={isQuerying}
                  className="w-full pl-10 pr-4 py-2.5 bg-[#111] border border-[#1a1a1a] rounded-lg text-sm text-white placeholder-[#333] focus:outline-none focus:border-[#6EBE46]/30 focus:ring-1 focus:ring-[#6EBE46]/10 disabled:opacity-50"
                  style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: "13px" }}
                />
              </div>
              <button
                onClick={() => handleQuery()}
                disabled={isQuerying || !query.trim()}
                className="px-4 py-2.5 bg-[#6EBE46] hover:bg-[#5EA836] text-black font-medium rounded-lg text-sm disabled:opacity-30 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
              >
                {isQuerying ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Sparkles className="w-4 h-4" />
                )}
                Query
              </button>
            </div>
            <p
              className="max-w-3xl mx-auto text-[10px] text-[#222] mt-2 pl-10"
              style={{ fontFamily: "'JetBrains Mono', monospace" }}
            >
              Queries are translated to SPARQL and executed against GraphDB in real-time
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

// =====================================================
// HELPERS
// =====================================================

function formatCellValue(val: string): string {
  // Shorten URIs for display
  if (val.startsWith("https://proto.atlas/data/")) {
    return val.replace("https://proto.atlas/data/", "");
  }
  if (val.startsWith("https://proto.atlas/ontology/")) {
    return val.replace("https://proto.atlas/ontology/", "proto:");
  }
  if (val.startsWith("https://proto.atlas/taxonomy/")) {
    return val.replace("https://proto.atlas/taxonomy/", "tax:");
  }
  if (val.startsWith("https://proto.atlas/relationship/")) {
    return val.replace("https://proto.atlas/relationship/", "rel:");
  }
  // Truncate long strings
  if (val.length > 80) {
    return val.slice(0, 77) + "...";
  }
  return val;
}

// =====================================================
// MINI GRAPH (inline D3 force-directed)
// =====================================================

function MiniGraph({
  nodes,
  edges,
}: {
  nodes: SubgraphNode[];
  edges: SubgraphEdge[];
}) {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!svgRef.current || nodes.length === 0) return;

    const width = svgRef.current.clientWidth || 700;
    const height = 320;

    // Clear previous
    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    svg
      .attr("width", width)
      .attr("height", height)
      .attr("viewBox", `0 0 ${width} ${height}`);

    // Deep clone nodes and edges for D3 mutation
    const simNodes: any[] = nodes.map((n) => ({ ...n }));
    const simEdges: any[] = edges.map((e) => ({
      ...e,
      source: typeof e.source === "string" ? e.source : (e.source as SubgraphNode).id,
      target: typeof e.target === "string" ? e.target : (e.target as SubgraphNode).id,
    }));

    const g = svg.append("g");

    // Zoom
    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.3, 3])
      .on("zoom", (event) => g.attr("transform", event.transform));
    svg.call(zoom);

    // Simulation
    const simulation = d3.forceSimulation(simNodes)
      .force("link", d3.forceLink(simEdges).id((d: any) => d.id).distance(80))
      .force("charge", d3.forceManyBody().strength(-200))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collision", d3.forceCollide().radius(25));

    // Edges
    const link = g.append("g")
      .selectAll("line")
      .data(simEdges)
      .join("line")
      .attr("stroke", "#222")
      .attr("stroke-width", 1)
      .attr("stroke-opacity", 0.6);

    // Edge labels
    const edgeLabel = g.append("g")
      .selectAll("text")
      .data(simEdges)
      .join("text")
      .text((d: any) => d.type)
      .attr("font-size", "8px")
      .attr("fill", "#333")
      .attr("text-anchor", "middle")
      .style("font-family", "'JetBrains Mono', monospace");

    // Nodes
    const node = g.append("g")
      .selectAll("circle")
      .data(simNodes)
      .join("circle")
      .attr("r", (d: any) => d.highlighted ? 10 : 6)
      .attr("fill", (d: any) => d.color || "#555")
      .attr("stroke", (d: any) => d.highlighted ? "#fff" : "none")
      .attr("stroke-width", (d: any) => d.highlighted ? 2 : 0)
      .attr("opacity", (d: any) => d.highlighted ? 1 : 0.5)
      .style("cursor", "pointer")
      .call(
        d3.drag<SVGCircleElement, any>()
          .on("start", (event, d) => {
            if (!event.active) simulation.alphaTarget(0.3).restart();
            d.fx = d.x;
            d.fy = d.y;
          })
          .on("drag", (event, d) => {
            d.fx = event.x;
            d.fy = event.y;
          })
          .on("end", (event, d) => {
            if (!event.active) simulation.alphaTarget(0);
            d.fx = null;
            d.fy = null;
          })
      );

    // Node labels
    const label = g.append("g")
      .selectAll("text")
      .data(simNodes)
      .join("text")
      .text((d: any) => d.label)
      .attr("font-size", (d: any) => d.highlighted ? "11px" : "9px")
      .attr("fill", (d: any) => d.highlighted ? "#eee" : "#555")
      .attr("text-anchor", "middle")
      .attr("dy", (d: any) => (d.highlighted ? -16 : -12))
      .style("font-family", "'JetBrains Mono', monospace")
      .style("pointer-events", "none");

    // Tick
    simulation.on("tick", () => {
      link
        .attr("x1", (d: any) => d.source.x)
        .attr("y1", (d: any) => d.source.y)
        .attr("x2", (d: any) => d.target.x)
        .attr("y2", (d: any) => d.target.y);

      edgeLabel
        .attr("x", (d: any) => (d.source.x + d.target.x) / 2)
        .attr("y", (d: any) => (d.source.y + d.target.y) / 2);

      node
        .attr("cx", (d: any) => d.x)
        .attr("cy", (d: any) => d.y);

      label
        .attr("x", (d: any) => d.x)
        .attr("y", (d: any) => d.y);
    });

    return () => {
      simulation.stop();
    };
  }, [nodes, edges]);

  return (
    <svg
      ref={svgRef}
      className="w-full"
      style={{ height: "320px", background: "#080808" }}
    />
  );
}