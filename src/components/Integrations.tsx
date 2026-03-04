import { useState } from "react";
import { Database, RefreshCw, CheckCircle2, XCircle, AlertCircle, ExternalLink, Settings, Power } from "lucide-react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

interface Integration {
    id: string;
    name: string;
    icon: string;
    status: "connected" | "disconnected" | "error";
    lastSync?: Date;
    description: string;
    color: string;
}

const Integrations = () => {
    const [integrations, setIntegrations] = useState<Integration[]>([

        {
            id: "slack",
            name: "Slack",
            icon: "💬",
            status: "disconnected",
            description: "Agentic Teammate Messaging",
            color: "bg-green-500"
        },
        {
            id: "operator",
            name: "Operator",
            icon: ">_",
            status: "disconnected",
            description: "OPFOR Campaign Studio",
            color: "bg-blue-500"
        },
    ]);

    const getStatusIcon = (status: string) => {
        switch (status) {
            case "connected":
                return <CheckCircle2 className="w-4 h-4 text-green-500" />;
            case "error":
                return <XCircle className="w-4 h-4 text-red-500" />;
            default:
                return <AlertCircle className="w-4 h-4 text-muted-foreground" />;
        }
    };

    const handleToggleConnection = (integrationId: string) => {
        setIntegrations(prev => prev.map(int => {
            if (int.id === integrationId) {
                const newStatus = int.status === "connected" ? "disconnected" : "connected";
                toast.success(`${int.name} ${newStatus === "connected" ? "connected" : "disconnected"}`);
                return {
                    ...int,
                    status: newStatus,
                    lastSync: newStatus === "connected" ? new Date() : int.lastSync
                };
            }
            return int;
        }));
    };

    const handleSync = (integrationId: string) => {
        const integration = integrations.find(i => i.id === integrationId);
        if (integration?.status !== "connected") {
            toast.error("Integration must be connected to sync");
            return;
        }

        toast.success(`Syncing with ${integration.name}...`);

        setIntegrations(prev => prev.map(int =>
            int.id === integrationId ? { ...int, lastSync: new Date() } : int
        ));
    };

    const formatLastSync = (date?: Date) => {
        if (!date) return "Never";

        const now = Date.now();
        const diff = now - date.getTime();
        const minutes = Math.floor(diff / 60000);
        const hours = Math.floor(diff / 3600000);
        const days = Math.floor(diff / 86400000);

        if (minutes < 1) return "Just now";
        if (minutes < 60) return `${minutes}m ago`;
        if (hours < 24) return `${hours}h ago`;
        return `${days}d ago`;
    };

    return (
        <div className="space-y-3">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <Database className="w-4 h-4 text-accent-pink" />
                    <span className="text-xs font-bold text-muted-foreground">INTEGRATIONS</span>
                </div>
                <button className="p-1 hover:bg-muted rounded-md transition-colors">
                    <Settings className="w-3 h-3 text-muted-foreground" />
                </button>
            </div>

            {/* Integration Cards */}
            <div className="space-y-2">
                {integrations.map(integration => (
                    <div key={integration.id} className="neo-card p-3 hover:shadow-md transition-shadow">
                        {/* Integration Header */}
                        <div className="flex items-start justify-between mb-2">
                            <div className="flex items-center gap-2 flex-1">
                                <div className={`w-8 h-8 ${integration.color} rounded-lg flex items-center justify-center text-lg border-2 border-border`}>
                                    {integration.icon}
                                </div>
                                <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2">
                                        <h4 className="text-sm font-bold truncate">{integration.name}</h4>
                                        {getStatusIcon(integration.status)}
                                    </div>
                                    <p className="text-[10px] text-muted-foreground truncate">
                                        {integration.description}
                                    </p>
                                </div>
                            </div>
                        </div>

                        {/* Last Sync Info */}
                        {integration.lastSync && (
                            <div className="text-[10px] text-muted-foreground mb-2 flex items-center gap-1">
                                <RefreshCw className="w-3 h-3" />
                                Last sync: {formatLastSync(integration.lastSync)}
                            </div>
                        )}

                        {/* Action Buttons */}
                        <div className="flex gap-2">
                            <Button
                                onClick={() => handleToggleConnection(integration.id)}
                                size="sm"
                                variant={integration.status === "connected" ? "outline" : "default"}
                                className="flex-1 text-xs h-7"
                            >
                                <Power className="w-3 h-3 mr-1" />
                                {integration.status === "connected" ? "Disconnect" : "Connect"}
                            </Button>

                            {integration.status === "connected" && (
                                <Button
                                    onClick={() => handleSync(integration.id)}
                                    size="sm"
                                    variant="outline"
                                    className="text-xs h-7"
                                >
                                    <RefreshCw className="w-3 h-3" />
                                </Button>
                            )}

                            <Button
                                size="sm"
                                variant="ghost"
                                className="text-xs h-7 px-2"
                                onClick={() => toast.info(`Opening ${integration.name} settings...`)}
                            >
                                <ExternalLink className="w-3 h-3" />
                            </Button>
                        </div>
                    </div>
                ))}
            </div>

            {/* Quick Stats */}
            <div className="grid grid-cols-3 gap-2 pt-2">
                <div className="neo-card p-2 text-center">
                    <div className="text-lg font-bold text-green-500">
                        {integrations.filter(i => i.status === "connected").length}
                    </div>
                    <div className="text-[9px] text-muted-foreground">Connected</div>
                </div>
                <div className="neo-card p-2 text-center">
                    <div className="text-lg font-bold text-red-500">
                        {integrations.filter(i => i.status === "error").length}
                    </div>
                    <div className="text-[9px] text-muted-foreground">Errors</div>
                </div>
                <div className="neo-card p-2 text-center">
                    <div className="text-lg font-bold text-muted-foreground">
                        {integrations.length}
                    </div>
                    <div className="text-[9px] text-muted-foreground">Total</div>
                </div>
            </div>
        </div>
    );
};

export default Integrations;