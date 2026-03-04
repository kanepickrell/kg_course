import { useState } from "react";
import { Sparkles, Database, Gem } from "lucide-react";
import ChatAssistant from "./ChatAssistant";
import Integrations from "./Integrations";
import GemCard from "./GemCard";
import { SavedGem } from "./GemSaveModal";

interface LeftSidebarProps {
    selectedNodes: string[];
    onShowNodes: (nodeIds: string[]) => void;
    gems: SavedGem[];
    onDeleteGem: (gemId: string) => void;
    onViewNode: (nodeId: string) => void;
}

type Tab = "assistant" | "integrations" | "gems";

const LeftSidebar: React.FC<LeftSidebarProps> = ({
    selectedNodes,
    onShowNodes,
    gems,
    onDeleteGem,
    onViewNode
}) => {
    const [activeTab, setActiveTab] = useState<Tab>("assistant");

    const tabs = [
        { id: "assistant" as Tab, label: "AI Assistant", icon: Sparkles, badge: null },
        { id: "integrations" as Tab, label: "Integrations", icon: Database, badge: null },
        { id: "gems" as Tab, label: "Saved Gems", icon: Gem, badge: gems.length > 0 ? gems.length : null }
    ];

    return (
        <div className="w-[420px] flex flex-col h-full overflow-hidden">
            {/* Tab Navigation */}
            <div className="flex-shrink-0 bg-muted/30 border-b-[3px] border-border">
                <div className="flex">
                    {tabs.map(tab => {
                        const Icon = tab.icon;
                        const isActive = activeTab === tab.id;

                        return (
                            <button
                                key={tab.id}
                                onClick={() => setActiveTab(tab.id)}
                                className={`
                  flex-1 flex items-center justify-center gap-2 p-3 
                  transition-all relative
                  ${isActive
                                        ? "bg-card border-b-4 border-accent-pink"
                                        : "hover:bg-muted/50"
                                    }
                `}
                            >
                                <Icon className={`w-4 h-4 ${isActive ? "text-accent-pink" : "text-muted-foreground"}`} />
                                <span className={`text-xs font-bold ${isActive ? "text-foreground" : "text-muted-foreground"}`}>
                                    {tab.label}
                                </span>
                                {tab.badge !== null && (
                                    <span className="ml-1 w-5 h-5 bg-accent-pink text-[10px] font-bold rounded-full flex items-center justify-center border-2 border-border text-foreground">
                                        {tab.badge}
                                    </span>
                                )}
                            </button>
                        );
                    })}
                </div>
            </div>

            {/* Tab Content */}
            <div className="flex-1 min-h-0 overflow-hidden neo-card">
                {activeTab === "assistant" && (
                    <ChatAssistant
                        selectedNodes={selectedNodes}
                        expanded={true}
                        onToggle={() => { }}
                        onShowNodes={onShowNodes}
                    />
                )}

                {activeTab === "integrations" && (
                    <div className="h-full overflow-y-auto p-4">
                        <Integrations />
                    </div>
                )}

                {activeTab === "gems" && (
                    <div className="h-full overflow-y-auto p-4">
                        {gems.length > 0 ? (
                            <div className="space-y-3">
                                <div className="flex items-center justify-between mb-4">
                                    <div>
                                        <h3 className="text-lg font-extrabold">Your Hidden Gems</h3>
                                        <p className="text-xs text-muted-foreground">
                                            {gems.length} {gems.length === 1 ? "gem" : "gems"} saved
                                        </p>
                                    </div>
                                </div>

                                <div className="space-y-3">
                                    {gems.map(gem => (
                                        <GemCard
                                            key={gem.id}
                                            gem={gem}
                                            onDelete={onDeleteGem}
                                            onView={onViewNode}
                                        />
                                    ))}
                                </div>
                            </div>
                        ) : (
                            <div className="h-full flex flex-col items-center justify-center text-center p-8">
                                <Gem className="w-16 h-16 text-muted-foreground/20 mb-4" />
                                <h3 className="text-lg font-bold mb-2">No Gems Yet</h3>
                                <p className="text-sm text-muted-foreground mb-4">
                                    Click on nodes in the graph and select "Save as Gem" to start your collection
                                </p>
                            </div>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
};

export default LeftSidebar;