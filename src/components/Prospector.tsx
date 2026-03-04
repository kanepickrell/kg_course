import { useState, useEffect, useRef, useCallback } from "react";
import { motion, useInView } from "framer-motion";
import { Search, Filter, Loader2, Package, FileCode, Book, Wrench, Server, Database, TestTube, Users, User, RefreshCw } from "lucide-react";

interface ProspectorProps {
  selectedNodes: string[];
  onNodeSelect: (nodes: string[]) => void;
  onNodeInspect: (nodeData: any) => void;
}

interface GraphNode {
  id: string;
  label: string;
  type: string;
  cluster: string;
  description?: string;
  tags?: string[];
  importance?: number;
  _artifact_type?: string;
  owner?: string;
}

interface TeamInfo {
  label: string;
  color: string;
  uri?: string;
}

interface ArtifactType {
  label: string;
  uri: string;
  collection?: string;
  definition?: string;
}

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

// Default colors for teams (will be overridden by taxonomy metadata if available)
const DEFAULT_TEAM_COLORS: Record<string, string> = {
  "Automation": "#829646",
  "OPFOR": "#64783C",
  "Content Development": "#B4A082",
  "Range": "#8C8264",
  "default": "#6B7280"
};

// Icons for artifact types
const getTypeIcon = (type: string) => {
  const typeLower = type?.toLowerCase() || "";
  if (typeLower.includes("module") || typeLower.includes("library")) return <FileCode className="w-4 h-4" />;
  if (typeLower.includes("robot") || typeLower.includes("log") || typeLower.includes("test")) return <TestTube className="w-4 h-4" />;
  if (typeLower.includes("story") || typeLower.includes("development")) return <Book className="w-4 h-4" />;
  if (typeLower.includes("person")) return <User className="w-4 h-4" />;
  if (typeLower.includes("team")) return <Users className="w-4 h-4" />;
  if (typeLower.includes("playbook")) return <Book className="w-4 h-4" />;
  if (typeLower.includes("tool")) return <Wrench className="w-4 h-4" />;
  if (typeLower.includes("vm") || typeLower.includes("server")) return <Server className="w-4 h-4" />;
  return <Package className="w-4 h-4" />;
};

const AnimatedItem = ({ 
  children, 
  delay = 0, 
  index, 
  onMouseEnter, 
  onClick,
  isSelected 
}: any) => {
  const ref = useRef(null);
  const inView = useInView(ref, { amount: 0.3, once: false });
  
  return (
    <motion.div
      ref={ref}
      data-index={index}
      onMouseEnter={onMouseEnter}
      onClick={onClick}
      initial={{ scale: 0.95, opacity: 0, y: 20 }}
      animate={inView ? { scale: 1, opacity: 1, y: 0 } : { scale: 0.95, opacity: 0, y: 20 }}
      transition={{ duration: 0.3, delay }}
      className="mb-2"
    >
      {children}
    </motion.div>
  );
};

const Prospector = ({ selectedNodes, onNodeSelect, onNodeInspect }: ProspectorProps) => {
  const [loading, setLoading] = useState(true);
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [filteredNodes, setFilteredNodes] = useState<GraphNode[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [filterMode, setFilterMode] = useState<"all" | "team" | "type">("all");
  const [activeTeam, setActiveTeam] = useState<string | null>(null);
  const [activeType, setActiveType] = useState<string | null>(null);
  const [hoveredIndex, setHoveredIndex] = useState(-1);
  
  // Dynamic data from ontology/taxonomy
  const [teams, setTeams] = useState<Record<string, TeamInfo>>({});
  const [artifactTypes, setArtifactTypes] = useState<ArtifactType[]>([]);
  
  const listRef = useRef<HTMLDivElement>(null);
  const [topGradientOpacity, setTopGradientOpacity] = useState(0);
  const [bottomGradientOpacity, setBottomGradientOpacity] = useState(1);

  // Fetch teams from taxonomy
  const fetchTeams = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/ontology/taxonomies/teams`);
      if (res.ok) {
        const data = await res.json();
        const teamsMap: Record<string, TeamInfo> = {};
        
        (data.terms || []).forEach((term: any) => {
          teamsMap[term.label] = {
            label: term.label,
            color: term.metadata?.color || DEFAULT_TEAM_COLORS[term.label] || DEFAULT_TEAM_COLORS.default,
            uri: term.uri
          };
          // Also add aliases as keys pointing to same team
          (term.aliases || []).forEach((alias: string) => {
            teamsMap[alias] = teamsMap[term.label];
          });
        });
        
        setTeams(teamsMap);
        console.log("✓ Loaded teams from taxonomy:", Object.keys(teamsMap));
      }
    } catch (err) {
      console.error("Failed to fetch teams:", err);
      // Fallback to defaults
      setTeams(
        Object.fromEntries(
          Object.entries(DEFAULT_TEAM_COLORS)
            .filter(([k]) => k !== "default")
            .map(([k, v]) => [k, { label: k, color: v }])
        )
      );
    }
  };

  // Fetch artifact types from ontology
  const fetchArtifactTypes = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/ontology/concepts?include_abstract=false`);
      if (res.ok) {
        const data = await res.json();
        const types = (data.concepts || []).map((c: any) => ({
          label: c.label,
          uri: c.uri,
          collection: c.collection,
          definition: c.definition
        }));
        setArtifactTypes(types);
        console.log("✓ Loaded artifact types from ontology:", types.map((t: ArtifactType) => t.label));
      }
    } catch (err) {
      console.error("Failed to fetch artifact types:", err);
    }
  };

  // Fetch graph data
  const fetchNodes = async () => {
    try {
      setLoading(true);
      const response = await fetch(`${API_BASE}/graph`);
      if (!response.ok) throw new Error("Failed to fetch graph data");
      
      const data = await response.json();
      
      // Normalize nodes - use _artifact_type if available, fall back to type
      const normalizedNodes = (data.nodes || []).map((node: any) => ({
        ...node,
        type: node._artifact_type || node.type || "Unknown",
        cluster: node.owner || node.cluster || "Unknown"
      }));
      
      const sortedNodes = normalizedNodes.sort((a: GraphNode, b: GraphNode) => 
        (b.importance || 0) - (a.importance || 0)
      );
      
      setNodes(sortedNodes);
      setFilteredNodes(sortedNodes);
    } catch (err) {
      console.error("Failed to load nodes:", err);
    } finally {
      setLoading(false);
    }
  };

  // Initial load
  useEffect(() => {
    Promise.all([fetchTeams(), fetchArtifactTypes()]).then(() => {
      fetchNodes();
    });
  }, []);

  // Filter nodes based on search and filters
  useEffect(() => {
    let result = [...nodes];

    // Search filter
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      result = result.filter(node => 
        node.label?.toLowerCase().includes(query) ||
        node.description?.toLowerCase().includes(query) ||
        node.type?.toLowerCase().includes(query) ||
        node.tags?.some(tag => tag.toLowerCase().includes(query))
      );
    }

    // Team filter
    if (activeTeam) {
      result = result.filter(node => {
        const nodeTeam = node.owner || node.cluster;
        // Check direct match or alias match
        return nodeTeam === activeTeam || 
               teams[nodeTeam]?.label === activeTeam ||
               nodeTeam?.toLowerCase() === activeTeam.toLowerCase();
      });
    }

    // Type filter
    if (activeType) {
      result = result.filter(node => {
        const nodeType = node._artifact_type || node.type;
        return nodeType === activeType || 
               nodeType?.toLowerCase() === activeType.toLowerCase();
      });
    }

    setFilteredNodes(result);
  }, [nodes, searchQuery, activeTeam, activeType, teams]);

  // Scroll gradient handling
  const handleScroll = useCallback((e: any) => {
    const { scrollTop, scrollHeight, clientHeight } = e.target;
    setTopGradientOpacity(Math.min(scrollTop / 50, 1));
    const bottomDistance = scrollHeight - (scrollTop + clientHeight);
    setBottomGradientOpacity(scrollHeight <= clientHeight ? 0 : Math.min(bottomDistance / 50, 1));
  }, []);

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement) return;

      if (e.key === "ArrowDown") {
        e.preventDefault();
        setHoveredIndex(prev => Math.min(prev + 1, filteredNodes.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setHoveredIndex(prev => Math.max(prev - 1, 0));
      } else if (e.key === "Enter" && hoveredIndex >= 0) {
        e.preventDefault();
        const node = filteredNodes[hoveredIndex];
        onNodeSelect([node.id]);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [hoveredIndex, filteredNodes, onNodeSelect]);

  // Auto-scroll to hovered item
  useEffect(() => {
    if (hoveredIndex < 0 || !listRef.current) return;
    
    const container = listRef.current;
    const item = container.querySelector(`[data-index="${hoveredIndex}"]`);
    
    if (item) {
      const itemTop = (item as HTMLElement).offsetTop;
      const itemBottom = itemTop + (item as HTMLElement).offsetHeight;
      const containerTop = container.scrollTop;
      const containerBottom = containerTop + container.clientHeight;

      if (itemTop < containerTop + 50) {
        container.scrollTo({ top: itemTop - 50, behavior: "smooth" });
      } else if (itemBottom > containerBottom - 50) {
        container.scrollTo({ top: itemBottom - container.clientHeight + 50, behavior: "smooth" });
      }
    }
  }, [hoveredIndex]);

  // Get color for a team
  const getTeamColor = (teamName: string): string => {
    if (teams[teamName]) return teams[teamName].color;
    // Try case-insensitive match
    const match = Object.entries(teams).find(([k]) => k.toLowerCase() === teamName?.toLowerCase());
    if (match) return match[1].color;
    return DEFAULT_TEAM_COLORS.default;
  };

  // Get display name for a team
  const getTeamDisplayName = (teamName: string): string => {
    if (teams[teamName]) return teams[teamName].label;
    const match = Object.entries(teams).find(([k]) => k.toLowerCase() === teamName?.toLowerCase());
    if (match) return match[1].label;
    return teamName || "Unknown";
  };

  // Get unique teams from current nodes
  const getUniqueTeams = (): string[] => {
    const teamSet = new Set<string>();
    nodes.forEach(node => {
      const team = node.owner || node.cluster;
      if (team && team !== "Unknown") {
        // Normalize to canonical name if possible
        const canonical = teams[team]?.label || team;
        teamSet.add(canonical);
      }
    });
    return Array.from(teamSet).sort();
  };

  // Get unique types from current nodes
  const getUniqueTypes = (): string[] => {
    const typeSet = new Set<string>();
    nodes.forEach(node => {
      const type = node._artifact_type || node.type;
      if (type && type !== "Unknown") {
        typeSet.add(type);
      }
    });
    return Array.from(typeSet).sort();
  };

  const handleRefresh = () => {
    Promise.all([fetchTeams(), fetchArtifactTypes()]).then(() => {
      fetchNodes();
    });
  };

  if (loading) {
    return (
      <div className="w-full h-full flex items-center justify-center">
        <div className="text-center">
          <Loader2 className="w-8 h-8 animate-spin text-cactus-green mx-auto mb-3" />
          <p className="text-sm font-semibold text-white">Loading artifacts...</p>
        </div>
      </div>
    );
  }

  const uniqueTeams = getUniqueTeams();
  const uniqueTypes = getUniqueTypes();

  return (
    <div className="h-full flex flex-col bg-background">
      {/* Search and Filter Bar */}
      <div className="flex-shrink-0 p-3 space-y-2 border-b-2 border-border bg-secondary/10">
        {/* Search */}
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search artifacts..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-10 py-2 bg-background border-2 border-border rounded-lg text-sm text-white focus:outline-none focus:ring-2 focus:ring-cactus-green"
          />
          <button
            onClick={handleRefresh}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-cactus-green transition-colors"
            title="Refresh data"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>

        {/* Filter Modes */}
        <div className="flex items-center gap-2">
          <Filter className="w-4 h-4 text-muted-foreground" />
          <div className="flex items-center gap-1 flex-1">
            <button
              onClick={() => {
                setFilterMode("all");
                setActiveTeam(null);
                setActiveType(null);
              }}
              className={`px-3 py-1 text-xs font-bold rounded transition-all ${
                filterMode === "all"
                  ? "bg-cactus-green text-black"
                  : "bg-secondary text-muted-foreground hover:bg-secondary/70 hover:text-white"
              }`}
            >
              All ({nodes.length})
            </button>
            <button
              onClick={() => setFilterMode(filterMode === "team" ? "all" : "team")}
              className={`px-3 py-1 text-xs font-bold rounded transition-all ${
                filterMode === "team"
                  ? "bg-cactus-accent text-black"
                  : "bg-secondary text-muted-foreground hover:bg-secondary/70 hover:text-white"
              }`}
            >
              By Team ({uniqueTeams.length})
            </button>
            <button
              onClick={() => setFilterMode(filterMode === "type" ? "all" : "type")}
              className={`px-3 py-1 text-xs font-bold rounded transition-all ${
                filterMode === "type"
                  ? "bg-cactus-accent text-black"
                  : "bg-secondary text-muted-foreground hover:bg-secondary/70 hover:text-white"
              }`}
            >
              By Type ({uniqueTypes.length})
            </button>
          </div>
        </div>

        {/* Team Filters - Dynamic from taxonomy */}
        {filterMode === "team" && (
          <div className="flex items-center gap-2 flex-wrap">
            {uniqueTeams.length === 0 ? (
              <span className="text-xs text-muted-foreground">No teams found in data</span>
            ) : (
              uniqueTeams.map((team) => (
                <button
                  key={team}
                  onClick={() => setActiveTeam(activeTeam === team ? null : team)}
                  className={`px-3 py-1 text-xs font-bold rounded border-2 transition-all ${
                    activeTeam === team
                      ? "border-border bg-card text-white"
                      : "border-transparent bg-secondary text-white hover:border-border"
                  }`}
                  style={{
                    backgroundColor: activeTeam === team ? getTeamColor(team) + "20" : undefined,
                    borderColor: activeTeam === team ? getTeamColor(team) : undefined,
                  }}
                >
                  {getTeamDisplayName(team)}
                </button>
              ))
            )}
          </div>
        )}

        {/* Type Filters - Dynamic from ontology */}
        {filterMode === "type" && (
          <div className="flex items-center gap-2 flex-wrap">
            {uniqueTypes.length === 0 ? (
              <span className="text-xs text-muted-foreground">No artifact types found in data</span>
            ) : (
              uniqueTypes.map(type => (
                <button
                  key={type}
                  onClick={() => setActiveType(activeType === type ? null : type)}
                  className={`px-3 py-1 text-xs font-bold rounded border-2 transition-all flex items-center gap-1 ${
                    activeType === type
                      ? "border-cactus-green bg-cactus-green/10 text-white"
                      : "border-transparent bg-secondary text-white hover:border-border"
                  }`}
                >
                  {getTypeIcon(type)}
                  {type}
                </button>
              ))
            )}
          </div>
        )}
      </div>

      {/* Results Count */}
      <div className="flex-shrink-0 px-3 py-2 text-xs text-muted-foreground font-mono border-b border-border bg-secondary/5">
        Showing {filteredNodes.length} of {nodes.length} artifacts
        {activeTeam && <span className="ml-2 text-cactus-green">• Team: {activeTeam}</span>}
        {activeType && <span className="ml-2 text-cactus-green">• Type: {activeType}</span>}
      </div>

      {/* Artifact List */}
      <div className="flex-1 min-h-0 relative">
        <div
          ref={listRef}
          onScroll={handleScroll}
          className="h-full overflow-y-auto px-3 py-2 scroll-smooth"
          style={{ scrollbarWidth: "thin" }}
        >
          {filteredNodes.length === 0 ? (
            <div className="flex items-center justify-center h-full">
              <div className="text-center">
                <div className="text-4xl mb-2">🔍</div>
                <p className="text-sm font-semibold mb-1 text-white">No artifacts found</p>
                <p className="text-xs text-muted-foreground">
                  Try adjusting your filters or search
                </p>
              </div>
            </div>
          ) : (
            filteredNodes.map((node, index) => {
              const nodeTeam = node.owner || node.cluster;
              const nodeType = node._artifact_type || node.type;
              const teamColor = getTeamColor(nodeTeam);
              
              return (
                <AnimatedItem
                  key={node.id}
                  delay={Math.min(index * 0.02, 0.3)}
                  index={index}
                  onMouseEnter={() => setHoveredIndex(index)}
                  onClick={() => onNodeSelect([node.id])}
                  isSelected={selectedNodes.includes(node.id)}
                >
                  <div
                    className={`neo-card p-3 cursor-pointer transition-all border-2 ${
                      selectedNodes.includes(node.id)
                        ? "border-cactus-green bg-cactus-green/5 shadow-lg"
                        : hoveredIndex === index
                        ? "border-cactus-tan/50 bg-secondary/30"
                        : "border-border hover:border-border/50"
                    }`}
                    onDoubleClick={() => onNodeInspect(node)}
                  >
                    <div className="flex items-start gap-3">
                      {/* Icon */}
                      <div
                        className="flex-shrink-0 w-10 h-10 rounded-lg flex items-center justify-center border-2 border-border text-white"
                        style={{
                          backgroundColor: teamColor + "20",
                          borderColor: teamColor,
                        }}
                      >
                        {getTypeIcon(nodeType)}
                      </div>

                      {/* Content */}
                      <div className="flex-1 min-w-0">
                        <div className="font-bold text-sm mb-1 truncate text-white">
                          {node.label}
                        </div>
                        
                        {node.description && (
                          <div className="text-xs text-muted-foreground mb-2 line-clamp-2">
                            {node.description}
                          </div>
                        )}

                        <div className="flex items-center gap-1.5 flex-wrap">
                          {nodeTeam && nodeTeam !== "Unknown" && (
                            <span
                              className="px-2 py-0.5 text-[10px] font-bold rounded border"
                              style={{
                                backgroundColor: teamColor + "20",
                                borderColor: teamColor,
                                color: "#ffffff",
                              }}
                            >
                              {getTeamDisplayName(nodeTeam)}
                            </span>
                          )}
                          
                          {nodeType && nodeType !== "Unknown" && (
                            <span className="px-2 py-0.5 bg-secondary border border-border rounded text-[10px] font-semibold text-white">
                              {nodeType}
                            </span>
                          )}

                          {node.importance && node.importance > 0.7 && (
                            <span className="px-2 py-0.5 bg-cactus-green/20 border border-cactus-green/30 text-white rounded text-[10px] font-bold">
                              HIGH PRIORITY
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                </AnimatedItem>
              );
            })
          )}
        </div>

        {/* Gradients */}
        <div
          className="absolute top-0 left-0 right-0 h-12 pointer-events-none transition-opacity duration-300"
          style={{
            opacity: topGradientOpacity,
            background: "linear-gradient(to bottom, rgb(0, 0, 0) 0%, transparent 100%)",
          }}
        />
        <div
          className="absolute bottom-0 left-0 right-0 h-20 pointer-events-none transition-opacity duration-300"
          style={{
            opacity: bottomGradientOpacity,
            background: "linear-gradient(to top, rgb(0, 0, 0) 0%, transparent 100%)",
          }}
        />
      </div>

      {/* Bottom Status Bar */}
      <div className="flex-shrink-0 px-3 py-2 border-t-2 border-border bg-secondary/10 flex items-center justify-between text-xs">
        <div className="text-muted-foreground font-mono">
          {selectedNodes.length > 0 && `${selectedNodes.length} selected`}
        </div>
        <div className="text-muted-foreground">
          Use ↑↓ to navigate • Enter to select • Double-click to inspect
        </div>
      </div>
    </div>
  );
};

export default Prospector;