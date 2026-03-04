import React, { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Loader2, Settings, ExternalLink, RefreshCw, CheckCircle2, XCircle } from "lucide-react";
import { toast } from "sonner";

interface Plugin {
  id: string;
  name: string;
  description: string;
  endpoint: string;
  icon: string;
  active: boolean;
  collections: string[];
  created_at: string;
  updated_at: string;
}

interface PluginManagerProps {
  open: boolean;
  onClose: () => void;
}

const PluginManager: React.FC<PluginManagerProps> = ({ open, onClose }) => {
  const [plugins, setPlugins] = useState<Plugin[]>([]);
  const [loading, setLoading] = useState(true);
  const [toggling, setToggling] = useState<string | null>(null);

  const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

  useEffect(() => {
    if (open) {
      loadPlugins();
    }
  }, [open]);

  const loadPlugins = async () => {
    setLoading(true);
    try {
      const response = await fetch(`${API_URL}/api/plugins`);
      const data = await response.json();
      
      if (data.success) {
        setPlugins(data.plugins);
      }
    } catch (error) {
      console.error("Failed to load plugins:", error);
      toast.error("Failed to load plugins");
    } finally {
      setLoading(false);
    }
  };

  const togglePlugin = async (pluginId: string, currentState: boolean) => {
    setToggling(pluginId);
    
    try {
      const endpoint = currentState ? "deactivate" : "activate";
      const response = await fetch(`${API_URL}/api/plugins/${pluginId}/${endpoint}`, {
        method: "POST"
      });
      
      const data = await response.json();
      
      if (data.success) {
        toast.success(data.message);
        loadPlugins(); // Reload to get updated state
      } else {
        toast.error("Failed to toggle plugin");
      }
    } catch (error) {
      console.error("Failed to toggle plugin:", error);
      toast.error("Failed to toggle plugin");
    } finally {
      setToggling(null);
    }
  };

  const testPlugin = async (pluginId: string, endpoint: string) => {
    try {
      const response = await fetch(`${API_URL}${endpoint}`);
      const data = await response.json();
      
      if (data.success) {
        toast.success(`✅ Plugin working! Found ${data.count} items`);
      } else {
        toast.error("Plugin test failed");
      }
    } catch (error) {
      console.error("Plugin test failed:", error);
      toast.error("Plugin test failed");
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <Card className="w-full max-w-4xl max-h-[90vh] overflow-hidden neo-card">
        {/* Header */}
        <div className="p-6 border-b border-border">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-2xl font-bold flex items-center gap-2">
                🔌 Plugin Manager
              </h2>
              <p className="text-sm text-muted-foreground mt-1">
                Expose ProtoGraph data to external tools and integrations
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={loadPlugins}
                disabled={loading}
              >
                <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
              </Button>
              <Button variant="ghost" size="sm" onClick={onClose}>
                ✕
              </Button>
            </div>
          </div>
        </div>

        {/* Content */}
        <div className="p-6 max-h-[calc(90vh-140px)] overflow-y-auto">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-8 h-8 animate-spin text-accent-teal" />
            </div>
          ) : plugins.length === 0 ? (
            <div className="text-center py-12">
              <p className="text-muted-foreground">No plugins available</p>
            </div>
          ) : (
            <div className="space-y-4">
              {plugins.map(plugin => (
                <Card key={plugin.id} className="neo-card p-4 border-2 hover:border-accent-teal/30 transition-colors">
                  <div className="flex items-start gap-4">
                    {/* Icon */}
                    <div className="w-12 h-12 bg-accent-teal/10 rounded-lg flex items-center justify-center text-2xl flex-shrink-0">
                      {plugin.icon}
                    </div>

                    {/* Details */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-start justify-between gap-4 mb-2">
                        <div>
                          <h3 className="font-bold text-lg">{plugin.name}</h3>
                          <p className="text-sm text-muted-foreground">{plugin.description}</p>
                        </div>

                        {/* Toggle */}
                        <div className="flex items-center gap-2">
                          {plugin.active ? (
                            <Badge variant="default" className="bg-green-500/20 text-green-500 border-green-500/30">
                              <CheckCircle2 className="w-3 h-3 mr-1" />
                              Active
                            </Badge>
                          ) : (
                            <Badge variant="outline" className="text-muted-foreground">
                              <XCircle className="w-3 h-3 mr-1" />
                              Inactive
                            </Badge>
                          )}
                          <Switch
                            checked={plugin.active}
                            onCheckedChange={() => togglePlugin(plugin.id, plugin.active)}
                            disabled={toggling === plugin.id}
                          />
                        </div>
                      </div>

                      {/* Metadata */}
                      <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground mb-3">
                        <div className="flex items-center gap-1">
                          <span className="font-mono text-accent-teal">GET</span>
                          <code className="bg-secondary px-2 py-0.5 rounded">
                            {plugin.endpoint}
                          </code>
                        </div>
                        <span>•</span>
                        <div>
                          <strong>Collections:</strong> {plugin.collections.join(", ")}
                        </div>
                      </div>

                      {/* Actions */}
                      {plugin.active && (
                        <div className="flex gap-2">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => testPlugin(plugin.id, plugin.endpoint)}
                            className="text-xs"
                          >
                            <ExternalLink className="w-3 h-3 mr-1" />
                            Test Endpoint
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            disabled
                            className="text-xs"
                          >
                            <Settings className="w-3 h-3 mr-1" />
                            Configure Mappings
                          </Button>
                        </div>
                      )}
                    </div>
                  </div>
                </Card>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-border bg-secondary/20">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>
              {plugins.filter(p => p.active).length} of {plugins.length} plugins active
            </span>
            <span>ProtoGraph Plugin System v1.0</span>
          </div>
        </div>
      </Card>
    </div>
  );
};

export default PluginManager;