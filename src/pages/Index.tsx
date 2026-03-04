import { useState, useEffect, useRef } from "react";
import { toast } from "sonner";
import Header from "@/components/Header";
import GraphExplorer, { GraphExplorerRef } from "@/components/GraphExplorer";
import Prospector from "@/components/Prospector";
import GemDrawer from "@/components/GemDrawer";
import GemSaveModal, { SavedGem } from "@/components/GemSaveModal";
import GraphHealthMonitor from "@/components/GraphHealthMonitor";
import { ReactFlowProvider } from "reactflow";
import { Crosshair, List, Activity, PanelRightClose, PanelRightOpen } from "lucide-react";

const Index = () => {
  const [selectedNodes, setSelectedNodes] = useState<string[]>([]);
  const [explorerMode, setExplorerMode] = useState<"mining" | "discovery">("discovery");
  const [gems, setGems] = useState<SavedGem[]>([]);
  const [gemModalOpen, setGemModalOpen] = useState(false);
  const [selectedNodeForGem, setSelectedNodeForGem] = useState<any>(null);
  const [selectedNodesForProspect, setSelectedNodesForProspect] = useState<any[]>([]);
  const [modalMode, setModalMode] = useState<"gem" | "prospect">("gem");
  const [activeTab, setActiveTab] = useState<"health" | "gems">("gems");
  const [inspectedNode, setInspectedNode] = useState(null);
  const [mainViewMode, setMainViewMode] = useState<"explorer" | "prospector">("explorer");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  const graphExplorerRef = useRef<GraphExplorerRef>(null);

  useEffect(() => {
    const savedMode = localStorage.getItem("graph-explorer-mode") as "mining" | "discovery";
    if (savedMode) setExplorerMode(savedMode);

    const savedGems = localStorage.getItem("hidden-gems");
    if (savedGems) {
      try {
        const parsed = JSON.parse(savedGems);
        const gemsWithDates = parsed.map((g: any) => ({
          ...g,
          capturedAt: new Date(g.capturedAt),
        }));
        setGems(gemsWithDates);
      } catch (e) {
        console.error("Failed to load gems:", e);
      }
    }

    // Load sidebar state
    const savedSidebarState = localStorage.getItem("sidebar-collapsed");
    if (savedSidebarState) {
      setSidebarCollapsed(savedSidebarState === "true");
    }
  }, []);

  useEffect(() => {
    localStorage.setItem("graph-explorer-mode", explorerMode);
  }, [explorerMode]);

  useEffect(() => {
    localStorage.setItem("hidden-gems", JSON.stringify(gems));
  }, [gems]);

  useEffect(() => {
    localStorage.setItem("sidebar-collapsed", String(sidebarCollapsed));
  }, [sidebarCollapsed]);

  const handleCaptureGem = (nodeData: any) => {
    setSelectedNodeForGem(nodeData);
    setSelectedNodesForProspect([]);
    setModalMode("gem");
    setGemModalOpen(true);
  };

  const handleSaveGem = (gem: SavedGem) => {
    setGems((prev) => [...prev, gem]);
    const icon = gem.type === "prospect" ? "⛏️" : "💎";
    const title =
      gem.type === "prospect"
        ? `Saved "${gem.label}" to Prospects!`
        : `Saved "${gem.label}" to Hidden Gems!`;
    toast.success(`${icon} ${title}`, {
      description:
        gem.type === "prospect"
          ? `${gem.nodeCount} nodes captured for further investigation`
          : "View it in the Saved Gems tab",
    });
  };

  const handleDeleteGem = (gemId: string) => {
    const gem = gems.find((g) => g.id === gemId);
    setGems((prev) => prev.filter((g) => g.id !== gemId));
    const type = gem?.type === "prospect" ? "Prospect" : "Gem";
    toast.info(`${type} removed from collection`);
  };

  const handleViewNodeFromGem = (nodeId: string) => {
    setSelectedNodes([nodeId]);
    setExplorerMode("discovery");
    setMainViewMode("explorer");
    // Expand sidebar if collapsed so user can see the gem
    if (sidebarCollapsed) {
      setSidebarCollapsed(false);
    }
    setTimeout(() => {
      graphExplorerRef.current?.focusNode(nodeId, 800);
    }, 100);
  };

  const handleExportGems = () => {
    const dataStr = JSON.stringify(gems, null, 2);
    const blob = new Blob([dataStr], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `protograph-gems-${new Date().toISOString().split("T")[0]}.json`;
    link.click();
    URL.revokeObjectURL(url);
    toast.success("💎 Gems exported successfully!");
  };

  const handleClearAllGems = () => {
    if (confirm(`Are you sure you want to delete all ${gems.length} saved items?`)) {
      setGems([]);
      localStorage.removeItem("hidden-gems");
      toast.info("All gems and prospects cleared");
    }
  };

  const handleDiscoveryComplete = () => {
    toast.success("🔍 Discovery complete!", {
      description: "New connection suggestions are ready for review",
    });
    // Optionally refresh graph data
    graphExplorerRef.current?.refreshData?.();
  };

  const handleRefreshGraph = () => {
    // Trigger a graph data reload without full page refresh
    graphExplorerRef.current?.refreshData?.();
  };

  const toggleSidebar = () => {
    setSidebarCollapsed((prev) => !prev);
  };

  return (
    <div className="h-screen w-screen flex flex-col overflow-hidden bg-background">
      {/* Header */}
      <div className="flex-shrink-0">
        <Header
          onDiscoveryPromptClick={(prompt) => {
            setExplorerMode("discovery");
            console.log("Discovery prompt:", prompt);
          }}
          onNodeSelect={setSelectedNodes}
          onNodeFocus={(nodeId) => {
            graphExplorerRef.current?.focusNode(nodeId, 800);
          }}
        />
      </div>

      {/* Main Content */}
      <div className="flex-1 min-h-0 flex overflow-hidden">
        {/* Main View Area */}
        <div className="flex-1 min-w-0 p-3">
          <div className="h-full neo-card bg-card overflow-hidden flex flex-col">
            {/* View Mode Toggle */}
            <div className="flex-shrink-0 flex items-center justify-between px-4 py-2 border-b-2 border-border bg-secondary/20">
              <div className="flex items-center gap-2">
                <div className="flex items-center gap-1 bg-background border-2 border-border rounded-lg p-0.5">
                  <button
                    onClick={() => setMainViewMode("explorer")}
                    className={`px-3 py-1.5 text-xs font-bold rounded flex items-center gap-2 transition-all ${
                      mainViewMode === "explorer"
                        ? "bg-cactus-green text-white shadow-sm"
                        : "text-muted-foreground hover:text-white"
                    }`}
                  >
                    <Crosshair className="w-3.5 h-3.5" />
                    EXPLORER
                  </button>
                  <button
                    onClick={() => setMainViewMode("prospector")}
                    className={`px-3 py-1.5 text-xs font-bold rounded flex items-center gap-2 transition-all ${
                      mainViewMode === "prospector"
                        ? "bg-cactus-green text-white shadow-sm"
                        : "text-muted-foreground hover:text-white"
                    }`}
                  >
                    <List className="w-3.5 h-3.5" />
                    PROSPECTOR
                  </button>
                </div>
              </div>

              <div className="flex items-center gap-3">
                {mainViewMode === "explorer" && (
                  <div className="text-xs text-muted-foreground text-white font-mono">
                    VISUAL GRAPH MODE
                  </div>
                )}
                {mainViewMode === "prospector" && (
                  <div className="text-xs text-muted-foreground text-white font-mono">
                    LIST VIEW MODE
                  </div>
                )}

                {/* Sidebar Toggle Button */}
                <button
                  onClick={toggleSidebar}
                  className="p-1.5 rounded hover:bg-secondary/50 text-muted-foreground hover:text-white transition-colors"
                  title={sidebarCollapsed ? "Show sidebar" : "Hide sidebar"}
                >
                  {sidebarCollapsed ? (
                    <PanelRightOpen className="w-4 h-4" />
                  ) : (
                    <PanelRightClose className="w-4 h-4" />
                  )}
                </button>
              </div>
            </div>

            {/* View Content */}
            <div className="flex-1 min-h-0">
              {mainViewMode === "explorer" ? (
                <ReactFlowProvider>
                  <GraphExplorer
                    ref={graphExplorerRef}
                    selectedNodes={selectedNodes}
                    onNodeSelect={setSelectedNodes}
                    mode={explorerMode}
                    onModeChange={setExplorerMode}
                    onNodeInspect={(node) => {
                      setInspectedNode(node);
                      setActiveTab("gems");
                      // Expand sidebar if collapsed so user can see the inspected node
                      if (sidebarCollapsed) {
                        setSidebarCollapsed(false);
                      }
                    }}
                    onNodeDeleted={() => {
                      // Refresh the graph
                      window.location.reload();
                    }}
                  />
                </ReactFlowProvider>
              ) : (
                <Prospector
                  selectedNodes={selectedNodes}
                  onNodeSelect={setSelectedNodes}
                  onNodeInspect={(node) => {
                    setInspectedNode(node);
                    setActiveTab("gems");
                    // Expand sidebar if collapsed
                    if (sidebarCollapsed) {
                      setSidebarCollapsed(false);
                    }
                  }}
                />
              )}
            </div>
          </div>
        </div>

        {/* Right Sidebar - Collapsible */}
        <div
          className={`flex-shrink-0 flex flex-col border-l-3 border-border bg-card h-full transition-all duration-300 ease-in-out ${
            sidebarCollapsed ? "w-0 overflow-hidden opacity-0" : "w-[380px] opacity-100"
          }`}
        >
          {/* Tab Header */}
          <div className="flex-shrink-0 flex items-center border-b-2 border-border bg-secondary/10">
            <button
              onClick={() => setActiveTab("gems")}
              className={`flex-1 py-2.5 text-xs font-bold transition-all relative ${
                activeTab === "gems"
                  ? "bg-card border-b-3 border-cactus-green text-white"
                  : "text-muted-foreground hover:bg-secondary/30 hover:text-white"
              }`}
            >
              <span className="flex items-center justify-center gap-2">
                <span>💎</span> GEMS
              </span>
              {gems.length > 0 && (
                <span className="absolute right-2 top-1 w-5 h-5 bg-cactus-green text-black text-[10px] font-bold rounded-full flex items-center justify-center border-2 border-border">
                  {gems.length}
                </span>
              )}
            </button>

            <button
              onClick={() => setActiveTab("health")}
              className={`flex-1 py-2.5 text-xs font-bold transition-all ${
                activeTab === "health"
                  ? "bg-card border-b-3 border-teal-500 text-white"
                  : "text-muted-foreground hover:bg-secondary/30 hover:text-white"
              }`}
            >
              <span className="flex items-center justify-center gap-2">
                <Activity className="w-4 h-4" /> HEALTH
              </span>
            </button>
          </div>

          {/* Content Area */}
          <div className="flex-1 min-h-0 overflow-hidden">
            {activeTab === "health" && (
              <div className="h-full overflow-y-auto">
                <GraphHealthMonitor
                  onDiscoveryComplete={handleDiscoveryComplete}
                />
              </div>
            )}

            {activeTab === "gems" && (
              <div className="h-full overflow-hidden">
                <GemDrawer
                  gems={gems}
                  inspectedNode={inspectedNode}
                  onDeleteGem={handleDeleteGem}
                  onViewNode={handleViewNodeFromGem}
                  onExportGems={handleExportGems}
                  onClearAll={handleClearAllGems}
                  onSaveGemFromInspector={(node) => {
                    setSelectedNodeForGem(node);
                    setGemModalOpen(true);
                  }}
                />
              </div>
            )}
          </div>
        </div>

        {/* Collapsed Sidebar Indicator - Shows when sidebar is collapsed */}
        {sidebarCollapsed && (
          <div className="flex-shrink-0 w-10 flex flex-col items-center border-l border-border bg-card/50 h-full">
            <button
              onClick={toggleSidebar}
              className="mt-4 p-2 rounded hover:bg-secondary/50 text-muted-foreground hover:text-white transition-colors"
              title="Show sidebar"
            >
              <PanelRightOpen className="w-4 h-4" />
            </button>
            
            {/* Vertical indicator icons */}
            <div className="mt-4 flex flex-col items-center gap-3">
              <button
                onClick={() => {
                  setSidebarCollapsed(false);
                  setActiveTab("gems");
                }}
                className="p-1.5 rounded hover:bg-secondary/50 transition-colors relative"
                title="Gems"
              >
                <span className="text-sm">💎</span>
                {gems.length > 0 && (
                  <span className="absolute -top-1 -right-1 w-4 h-4 bg-cactus-green text-black text-[8px] font-bold rounded-full flex items-center justify-center">
                    {gems.length > 9 ? "9+" : gems.length}
                  </span>
                )}
              </button>
              
              <button
                onClick={() => {
                  setSidebarCollapsed(false);
                  setActiveTab("health");
                }}
                className="p-1.5 rounded hover:bg-secondary/50 text-muted-foreground hover:text-teal-400 transition-colors"
                title="Health"
              >
                <Activity className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Modal */}
      <GemSaveModal
        open={gemModalOpen}
        onClose={() => {
          setGemModalOpen(false);
          setSelectedNodeForGem(null);
          setSelectedNodesForProspect([]);
        }}
        node={selectedNodeForGem}
        nodes={selectedNodesForProspect}
        mode={modalMode}
        onSave={handleSaveGem}
      />
    </div>
  );
};

export default Index;