// src/components/GemDrawer.tsx 
// Updated: Payload links now open in new tab instead of inline rendering

import React, { useState, useEffect } from "react";
import { SavedGem } from "./GemSaveModal";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Card } from "@/components/ui/card";
import { Trash2, ExternalLink, AlertTriangle } from "lucide-react";
import { toast } from "sonner";

interface GemDrawerProps {
  gems: SavedGem[];
  prospects?: SavedGem[];
  inspectedNode: any;
  onDeleteGem: (id: string) => void;
  onViewNode: (id: string) => void;
  onExportGems: () => void;
  onClearAll: () => void;
  onSaveGemFromInspector: (node: any) => void;
  onArtifactDeleted?: () => void;
}

const GemDrawer: React.FC<GemDrawerProps> = ({
  gems,
  prospects = [],
  inspectedNode,
  onDeleteGem,
  onViewNode,
  onExportGems,
  onClearAll,
  onSaveGemFromInspector,
  onArtifactDeleted,
}) => {
  const [fullNodeData, setFullNodeData] = useState<any>(null);
  const [deleting, setDeleting] = useState(false);

  const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

  // Fetch full node doc (metadata only - no payload loading)
  useEffect(() => {
    if (!inspectedNode) {
      setFullNodeData(null);
      return;
    }

    const load = async () => {
      try {
        const safeId = encodeURIComponent(inspectedNode.id);
        const res = await fetch(`${API_URL}/api/artifact/${safeId}`);

        const json = await res.json();
        if (json.success) {
          setFullNodeData(json.data);
          console.log("✅ Node metadata loaded:", json.data);
        } else {
          console.error("Artifact fetch returned error:", json);
        }
      } catch (err) {
        console.error("Failed to load node data:", err);
      }
    };

    load();
  }, [inspectedNode, API_URL]);

  // Delete artifact from database
  const handleDeleteArtifact = async () => {
    if (!inspectedNode) return;

    if (!confirm(`Delete "${inspectedNode.label}" from the database?\n\nThis will permanently remove this artifact and cannot be undone.`)) {
      return;
    }

    setDeleting(true);

    try {
      const [collection, key] = inspectedNode.id.split('/');
      
      const response = await fetch(`${API_URL}/api/artifact/${collection}/${key}`, {
        method: 'DELETE'
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to delete: ${response.statusText}`);
      }

      toast.success(`Deleted "${inspectedNode.label}" from database`);
      
      setFullNodeData(null);
      
      if (onArtifactDeleted) {
        onArtifactDeleted();
      }
      
    } catch (error) {
      console.error('Delete failed:', error);
      toast.error(error instanceof Error ? error.message : 'Failed to delete artifact');
    } finally {
      setDeleting(false);
    }
  };

  // Open payload in new tab
  const openPayloadInNewTab = () => {
    const payloadUrl = fullNodeData?.payload_url || fullNodeData?.dataUrl;
    if (!payloadUrl) {
      toast.error("No payload URL available for this artifact");
      return;
    }

    // Build full URL
    const fullUrl = payloadUrl.startsWith('http') 
      ? payloadUrl 
      : `${API_URL}${payloadUrl}`;
    
    console.log("🔗 Opening payload in new tab:", fullUrl);
    window.open(fullUrl, '_blank');
  };

  // Format field names to be more readable
  const formatFieldName = (key: string): string => {
    return key
      .replace(/^_/, '')
      .split('_')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');
  };

  // Check if a value is a reference to another node
  const isNodeReference = (value: string): boolean => {
    return typeof value === 'string' && value.includes('/') && 
           !value.startsWith('http') && !value.includes('@');
  };

  const renderField = (key: string, value: any, depth: number = 0) => {
    const displayName = formatFieldName(key);
    
    // Skip internal ArangoDB fields and payload_url in the main view
    if (depth === 0 && ['_key', '_id', '_rev', 'payload_url', 'dataUrl'].includes(key)) {
      return null;
    }

    // Arrays
    if (Array.isArray(value)) {
      if (value.length === 0) return null;
      
      return (
        <div key={key} className="mb-3">
          <div className="font-bold text-xs mb-1 flex items-center gap-2" style={{ color: 'rgb(200, 200, 200)' }}>
            <span style={{ color: 'rgb(130, 150, 70)' }}>▸</span>
            {displayName}
            <span className="text-[10px] font-normal" style={{ color: 'rgb(140, 140, 140)' }}>
              ({value.length} {value.length === 1 ? 'item' : 'items'})
            </span>
          </div>
          <div className="ml-3 space-y-1">
            {value.slice(0, 5).map((v, idx) => (
              <div key={idx} className="text-xs flex items-start gap-2">
                <span className="mt-0.5" style={{ color: 'rgb(140, 140, 140)' }}>•</span>
                {isNodeReference(String(v)) ? (
                  <button
                    onClick={() => onViewNode(String(v))}
                    className="text-left flex-1 hover:underline"
                    style={{ color: 'rgb(130, 150, 70)' }}
                  >
                    {String(v)}
                  </button>
                ) : (
                  <span className="flex-1 break-words" style={{ color: 'rgb(230, 230, 230)' }}>
                    {typeof v === 'object' ? JSON.stringify(v) : String(v)}
                  </span>
                )}
              </div>
            ))}
            {value.length > 5 && (
              <div className="text-[10px] italic" style={{ color: 'rgb(140, 140, 140)' }}>
                ... and {value.length - 5} more (view full payload for complete list)
              </div>
            )}
          </div>
        </div>
      );
    }

    // Objects (nested) - show summary only
    if (typeof value === "object" && value !== null) {
      const entries = Object.entries(value);
      if (entries.length === 0) return null;
      
      return (
        <div key={key} className="mb-3">
          <div className="font-bold text-xs mb-1 flex items-center gap-2" style={{ color: 'rgb(200, 200, 200)' }}>
            <span style={{ color: 'rgb(130, 150, 70)' }}>▸</span>
            {displayName}
            <span className="text-[10px] font-normal" style={{ color: 'rgb(140, 140, 140)' }}>
              ({entries.length} {entries.length === 1 ? 'field' : 'fields'})
            </span>
          </div>
          <div className="ml-3 text-[10px] italic" style={{ color: 'rgb(140, 140, 140)' }}>
            View full payload for details
          </div>
        </div>
      );
    }

    // Boolean values
    if (typeof value === 'boolean') {
      return (
        <div key={key} className="flex items-center justify-between py-1.5 text-xs">
          <span className="font-semibold" style={{ color: 'rgb(200, 200, 200)' }}>{displayName}</span>
          <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
            value 
              ? 'bg-green-500/20 text-green-600 border border-green-500/30' 
              : 'bg-red-500/20 text-red-600 border border-red-500/30'
          }`}>
            {value ? 'TRUE' : 'FALSE'}
          </span>
        </div>
      );
    }

    // Primitive values
    const displayValue = String(value);

    // Long text fields - truncate
    if (displayValue.length > 100) {
      return (
        <div key={key} className="mb-3">
          <div className="font-bold text-xs mb-1" style={{ color: 'rgb(200, 200, 200)' }}>
            {displayName}
          </div>
          <p className="text-xs leading-relaxed bg-secondary/30 p-2 rounded" style={{ color: 'rgb(160, 160, 160)' }}>
            {displayValue.slice(0, 100)}...
            <span className="text-[10px] italic ml-1">(view payload for full text)</span>
          </p>
        </div>
      );
    }

    // Node references (clickable)
    if (isNodeReference(displayValue)) {
      return (
        <div key={key} className="flex items-center justify-between py-1.5 text-xs">
          <span className="font-semibold" style={{ color: 'rgb(200, 200, 200)' }}>{displayName}</span>
          <button
            onClick={() => onViewNode(displayValue)}
            className="hover:underline font-mono text-[10px] text-right"
            style={{ color: 'rgb(130, 150, 70)' }}
          >
            {displayValue}
          </button>
        </div>
      );
    }

    // Regular fields
    return (
      <div key={key} className="flex items-center justify-between py-1.5 text-xs border-b border-border/30">
        <span className="font-semibold" style={{ color: 'rgb(200, 200, 200)' }}>{displayName}</span>
        <span className="text-right max-w-[60%] truncate" title={displayValue} style={{ color: 'rgb(160, 160, 160)' }}>
          {displayValue}
        </span>
      </div>
    );
  };

  // Check if node has payload URL
  const hasPayloadUrl = fullNodeData?.payload_url || fullNodeData?.dataUrl;

  return (
    <div className="w-full h-full flex flex-col p-4 overflow-y-auto">
      {/* Inspector */}
      {inspectedNode && (
        <Card className="p-4 mb-4 border-2 rounded-xl shadow-lg bg-gradient-to-br from-card to-secondary/20" style={{ borderColor: 'rgb(130, 150, 70, 0.4)' }}>
          {/* Header */}
          <div className="flex justify-between items-start mb-4 pb-3 border-b-2 border-border">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <div className="w-2 h-2 rounded-full animate-pulse" style={{ backgroundColor: 'rgb(130, 150, 70)' }} />
                <h2 className="text-lg font-bold truncate" style={{ color: 'rgb(230, 230, 230)' }}>
                  {fullNodeData?.icon && <span className="mr-2">{fullNodeData.icon}</span>}
                  {inspectedNode.label}
                </h2>
              </div>
              <div className="flex items-center gap-2 text-[10px] flex-wrap">
                <span className="px-2 py-0.5 bg-secondary border border-border rounded font-mono" style={{ color: 'rgb(180, 160, 130)' }}>
                  {inspectedNode.id}
                </span>
                {fullNodeData?.cluster && (
                  <span className="px-2 py-0.5 border rounded font-semibold" style={{ backgroundColor: 'rgba(130, 150, 70, 0.2)', borderColor: 'rgba(130, 150, 70, 0.3)', color: 'rgb(180, 200, 120)' }}>
                    {fullNodeData.cluster}
                  </span>
                )}
                {fullNodeData?._artifact_type && (
                  <span className="px-2 py-0.5 bg-accent-teal/20 border border-accent-teal/30 rounded text-accent-teal font-semibold">
                    {fullNodeData._artifact_type}
                  </span>
                )}
              </div>
            </div>

            {/* Action Buttons */}
            <div className="flex gap-2 flex-shrink-0">
              <Button
                size="sm"
                variant="default"
                onClick={() => onSaveGemFromInspector(inspectedNode)}
                className="neo-button text-xs flex items-center gap-1"
              >
                Save Gem
              </Button>
            </div>
          </div>
          
          {/* Content */}
          {fullNodeData ? (
            <div className="space-y-4">
              {/* Payload Link - Opens in New Tab */}
              {hasPayloadUrl && (
                <div className="neo-card p-3 bg-accent-orange/10 border border-accent-orange/30 rounded-lg">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <ExternalLink className="w-4 h-4 text-accent-orange" />
                      <span className="text-sm font-bold text-accent-orange">Full Payload Available</span>
                    </div>
                    <Button
                      size="sm"
                      variant="outline"
                      className="flex items-center gap-2 border-accent-orange/50 text-accent-orange hover:bg-accent-orange/10"
                      onClick={openPayloadInNewTab}
                    >
                      <ExternalLink size={14} />
                      Open in New Tab
                    </Button>
                  </div>
                  <div className="flex items-center gap-1 mt-2 text-[10px] text-muted-foreground">
                    <code className="bg-secondary px-1.5 py-0.5 rounded font-mono">
                      {fullNodeData.payload_url || fullNodeData.dataUrl}
                    </code>
                  </div>
                </div>
              )}

              {/* Quick Stats */}
              <div className="grid grid-cols-3 gap-2">
                <div className="neo-card p-2 bg-secondary/40 text-center">
                  <div className="text-xs font-bold" style={{ color: 'rgb(230, 230, 230)' }}>
                    {Object.keys(fullNodeData).filter(k => !k.startsWith('_') && k !== 'payload_url').length}
                  </div>
                  <div className="text-[9px]" style={{ color: 'rgb(140, 140, 140)' }}>Fields</div>
                </div>
                <div className="neo-card p-2 bg-secondary/40 text-center">
                  <div className="text-xs font-bold" style={{ color: 'rgb(230, 230, 230)' }}>
                    {hasPayloadUrl ? '✓' : '—'}
                  </div>
                  <div className="text-[9px]" style={{ color: 'rgb(140, 140, 140)' }}>Has Payload</div>
                </div>
                <div className="neo-card p-2 bg-secondary/40 text-center">
                  <div className="text-xs font-bold" style={{ color: 'rgb(230, 230, 230)' }}>
                    {fullNodeData._artifact_type || 'Unknown'}
                  </div>
                  <div className="text-[9px]" style={{ color: 'rgb(140, 140, 140)' }}>Type</div>
                </div>
              </div>

              {/* Metadata Fields (Lightweight View) */}
              <div>
                <h3 className="text-sm font-bold mb-2 flex items-center gap-2" style={{ color: 'rgb(200, 200, 200)' }}>
                  <span>📋</span>
                  Metadata
                  <span className="text-[10px] font-normal text-muted-foreground">
                    (stored in graph)
                  </span>
                </h3>
                <div className="space-y-1">
                  {Object.entries(fullNodeData)
                    .filter(([k]) => !k.startsWith('_') && k !== 'payload_url' && k !== 'dataUrl')
                    .map(([k, v]) => renderField(k, v))}
                </div>
              </div>

              {/* Technical Details - Collapsible */}
              <details className="group">
                <summary className="cursor-pointer text-sm font-bold transition-colors flex items-center gap-2" style={{ color: 'rgb(200, 200, 200)' }}>
                  <span className="group-open:rotate-90 transition-transform" style={{ color: 'rgb(140, 140, 140)' }}>▸</span>
                  🔍 Technical Details
                </summary>
                <div className="mt-2 space-y-1 ml-4">
                  <div className="flex justify-between text-xs py-1 border-b border-border/30">
                    <span className="font-semibold" style={{ color: 'rgb(200, 200, 200)' }}>Document Key</span>
                    <span className="font-mono text-[10px]" style={{ color: 'rgb(160, 160, 160)' }}>{fullNodeData._key}</span>
                  </div>
                  <div className="flex justify-between text-xs py-1 border-b border-border/30">
                    <span className="font-semibold" style={{ color: 'rgb(200, 200, 200)' }}>Document ID</span>
                    <span className="font-mono text-[10px]" style={{ color: 'rgb(160, 160, 160)' }}>{fullNodeData._id}</span>
                  </div>
                  <div className="flex justify-between text-xs py-1 border-b border-border/30">
                    <span className="font-semibold" style={{ color: 'rgb(200, 200, 200)' }}>Revision</span>
                    <span className="font-mono text-[10px]" style={{ color: 'rgb(160, 160, 160)' }}>{fullNodeData._rev}</span>
                  </div>
                  {fullNodeData._ingested_at && (
                    <div className="flex justify-between text-xs py-1 border-b border-border/30">
                      <span className="font-semibold" style={{ color: 'rgb(200, 200, 200)' }}>Ingested At</span>
                      <span className="font-mono text-[10px]" style={{ color: 'rgb(160, 160, 160)' }}>
                        {new Date(fullNodeData._ingested_at).toLocaleString()}
                      </span>
                    </div>
                  )}
                  {hasPayloadUrl && (
                    <div className="flex justify-between text-xs py-1 pt-2 border-t border-border/30">
                      <span className="font-semibold" style={{ color: 'rgb(200, 200, 200)' }}>Payload URL</span>
                      <button
                        onClick={openPayloadInNewTab}
                        className="font-mono text-[10px] hover:underline flex items-center gap-1"
                        style={{ color: 'rgb(130, 150, 70)' }}
                      >
                        {fullNodeData.payload_url || fullNodeData.dataUrl}
                        <ExternalLink className="w-3 h-3" />
                      </button>
                    </div>
                  )}
                </div>
              </details>

              {/* Danger Zone - Delete */}
              <details className="group">
                <summary className="cursor-pointer text-sm font-bold transition-colors flex items-center gap-2 text-destructive">
                  <span className="group-open:rotate-90 transition-transform">▸</span>
                  <AlertTriangle className="w-4 h-4" />
                  Danger Zone
                </summary>
                <div className="mt-3 p-3 border border-destructive/30 rounded-lg bg-destructive/5">
                  <p className="text-xs text-muted-foreground mb-3">
                    Permanently delete this artifact from the database. This action cannot be undone.
                  </p>
                  <Button
                    size="sm"
                    variant="destructive"
                    onClick={handleDeleteArtifact}
                    disabled={deleting}
                    className="w-full flex items-center justify-center gap-2"
                  >
                    {deleting ? (
                      <>
                        <div className="w-4 h-4 border-2 border-t-transparent border-white rounded-full animate-spin" />
                        Deleting...
                      </>
                    ) : (
                      <>
                        <Trash2 size={16} />
                        Delete "{inspectedNode.label}" Permanently
                      </>
                    )}
                  </Button>
                </div>
              </details>
            </div>
          ) : (
            <div className="flex items-center justify-center py-8">
              <div className="text-center">
                <div className="w-8 h-8 border-4 border-t-transparent rounded-full animate-spin mx-auto mb-2" style={{ borderColor: 'rgb(130, 150, 70)' }} />
                <p className="text-xs" style={{ color: 'rgb(140, 140, 140)' }}>Loading node data...</p>
              </div>
            </div>
          )}
        </Card>
      )}

      {/* Saved Findings */}
      <div className="flex justify-between items-center mb-3">
        <h2 className="text-md font-semibold" style={{ color: 'rgb(230, 230, 230)' }}>Saved Findings</h2>
        <div className="flex gap-2">
          <Button size="sm" variant="secondary" onClick={onExportGems}>
            Export
          </Button>
          <Button size="sm" variant="destructive" onClick={onClearAll}>
            Clear
          </Button>
        </div>
      </div>

      {/* Tabs */}
      <Tabs defaultValue="all" className="w-full">
        <TabsList className="mb-3">
          <TabsTrigger value="all">
            All ({gems.length + prospects.length})
          </TabsTrigger>
          <TabsTrigger value="gems">Gems ({gems.length})</TabsTrigger>
          <TabsTrigger value="prospects">
            Prospects ({prospects.length})
          </TabsTrigger>
        </TabsList>

        {/* ALL */}
        <TabsContent value="all">
          {gems.concat(prospects).length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              <p className="text-sm">No saved findings yet</p>
              <p className="text-xs mt-1">Select nodes and save them as gems</p>
            </div>
          ) : (
            gems.concat(prospects).map((item) => (
              <Card
                key={item.id}
                className="mb-3 p-3 border-2 border-primary/20 rounded-xl"
              >
                <div className="flex justify-between items-center">
                  <div>
                    <h3 className="font-bold" style={{ color: 'rgb(230, 230, 230)' }}>{item.label}</h3>
                    <p className="text-xs" style={{ color: 'rgb(140, 140, 140)' }}>{item.type}</p>
                  </div>

                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => onDeleteGem(item.id)}
                    title="Remove from saved gems"
                  >
                    <Trash2 size={16} />
                  </Button>
                </div>

                <div className="mt-2 flex justify-between text-xs">
                  <span style={{ color: 'rgb(160, 160, 160)' }}>{new Date(item.timestamp).toLocaleString()}</span>
                  <span
                    className="cursor-pointer hover:underline"
                    onClick={() => onViewNode(item.id)}
                    style={{ color: 'rgb(130, 150, 70)' }}
                  >
                    View in Graph
                  </span>
                </div>
              </Card>
            ))
          )}
        </TabsContent>

        {/* GEMS */}
        <TabsContent value="gems">
          {gems.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              <p className="text-sm">No gems saved</p>
            </div>
          ) : (
            gems.map((item) => (
              <Card
                key={item.id}
                className="mb-3 p-3 border-2 border-primary/20 rounded-xl"
              >
                <div className="flex justify-between items-center">
                  <h3 className="font-bold" style={{ color: 'rgb(230, 230, 230)' }}>{item.label}</h3>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => onDeleteGem(item.id)}
                    title="Remove from saved gems"
                  >
                    <Trash2 size={16} />
                  </Button>
                </div>
                <div className="mt-2 flex justify-between text-xs">
                  <span style={{ color: 'rgb(160, 160, 160)' }}>{new Date(item.timestamp).toLocaleString()}</span>
                  <span
                    className="cursor-pointer hover:underline"
                    onClick={() => onViewNode(item.id)}
                    style={{ color: 'rgb(130, 150, 70)' }}
                  >
                    View in Graph
                  </span>
                </div>
              </Card>
            ))
          )}
        </TabsContent>

        {/* PROSPECTS */}
        <TabsContent value="prospects">
          {prospects.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              <p className="text-sm">No prospects saved</p>
            </div>
          ) : (
            prospects.map((item) => (
              <Card
                key={item.id}
                className="mb-3 p-3 border-2 border-primary/20 rounded-xl"
              >
                <div className="flex justify-between items-center">
                  <h3 className="font-bold" style={{ color: 'rgb(230, 230, 230)' }}>{item.label}</h3>
                </div>
                <div className="mt-2 flex justify-between text-xs">
                  <span style={{ color: 'rgb(160, 160, 160)' }}>{new Date(item.timestamp).toLocaleString()}</span>
                  <span
                    className="cursor-pointer hover:underline"
                    onClick={() => onViewNode(item.id)}
                    style={{ color: 'rgb(130, 150, 70)' }}
                  >
                    View in Graph
                  </span>
                </div>
              </Card>
            ))
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default GemDrawer;