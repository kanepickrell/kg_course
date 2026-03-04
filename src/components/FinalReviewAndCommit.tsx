// frontend/src/components/ingestion/FinalReviewAndCommit.tsx

import React, { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Loader2, CheckCircle2, Database, FileText, Link as LinkIcon } from "lucide-react";
import { toast } from "sonner";

interface FinalReviewAndCommitProps {
  artifactId: string;
  fullData: any;
  finalMetadataFields: string[];
  dataUrl: string;
  storageLocation: string;
  suggestedType: string;
  onSuccess: () => void;
  onBack: () => void;
}

const FinalReviewAndCommit: React.FC<FinalReviewAndCommitProps> = ({
  artifactId,
  fullData,
  finalMetadataFields,
  dataUrl,
  storageLocation,
  suggestedType,
  onSuccess,
  onBack
}) => {
  const [committing, setCommitting] = useState(false);

  const extractMetadata = () => {
    const metadata: any = {
      _key: artifactId.replace(/[^a-zA-Z0-9_-]/g, '_'),
      type: suggestedType,
      dataUrl,
      storage_location: storageLocation,
      ingested_at: new Date().toISOString(),
      payload_size: JSON.stringify(fullData).length
    };

    finalMetadataFields.forEach(field => {
      metadata[field] = fullData[field];
    });

    return metadata;
  };

  const metadata = extractMetadata();
  const payloadFields = Object.keys(fullData).filter(k => !finalMetadataFields.includes(k));

  const handleCommit = async () => {
    setCommitting(true);

    try {
      // Call commit-with-payload endpoint
      const response = await fetch(`${import.meta.env.VITE_API_URL}/api/ingest/commit-with-payload`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          artifact_id: metadata._key,
          metadata,
          full_data: fullData
        })
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const result = await response.json();

      toast.success(`✅ Artifact saved successfully!`, {
        description: `Node ID: ${result.nodeId}`,
        duration: 5000
      });

      // Auto-trigger connection discovery
      toast.info("🔍 Discovering connections...", {
        description: "This may take 30-60 seconds",
        duration: 3000
      });

      onSuccess();

    } catch (error) {
      console.error("Commit failed:", error);
      toast.error("❌ Failed to save artifact", {
        description: error instanceof Error ? error.message : "Unknown error"
      });
    } finally {
      setCommitting(false);
    }
  };

  const formatBytes = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(2)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  };

  return (
    <div className="w-full max-w-6xl mx-auto p-6">
      <Card className="neo-card p-6">
        {/* Header */}
        <div className="mb-6">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-8 h-8 rounded-full bg-accent-teal/20 flex items-center justify-center">
              <span className="text-accent-teal font-bold">4</span>
            </div>
            <h2 className="text-2xl font-bold">Final Review & Commit</h2>
          </div>
          <p className="text-muted text-sm">
            Review your metadata schema before saving to ProtoGraph. This cannot be easily undone.
          </p>
        </div>

        <div className="grid grid-cols-2 gap-6">
          {/* Left: Metadata Preview */}
          <div>
            <div className="flex items-center gap-2 mb-3">
              <Database className="text-accent-teal" size={20} />
              <h3 className="text-lg font-bold">📊 Metadata (ArangoDB)</h3>
            </div>
            
            <div className="neo-card bg-accent-teal/10 border-accent-teal/30 p-4 mb-4">
              <div className="flex items-center justify-between mb-3">
                <Badge variant="outline" className="text-accent-teal border-accent-teal">
                  {finalMetadataFields.length} fields
                </Badge>
                <Badge variant="outline" className="text-accent-teal border-accent-teal">
                  {formatBytes(JSON.stringify(metadata).length)}
                </Badge>
              </div>

              <div className="space-y-2 max-h-96 overflow-y-auto neo-scrollbar">
                {Object.entries(metadata).map(([key, value]) => (
                  <div key={key} className="p-2 bg-secondary/30 rounded">
                    <div className="flex items-start justify-between gap-2">
                      <span className="font-semibold text-xs text-accent-teal">{key}:</span>
                      <span className="text-xs text-right break-all">
                        {typeof value === 'string' && value.length > 50
                          ? value.substring(0, 50) + '...'
                          : Array.isArray(value)
                          ? `[${value.length} items]`
                          : typeof value === 'object'
                          ? '[Object]'
                          : String(value)}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="neo-card bg-secondary/50 p-3">
              <div className="flex items-center gap-2 mb-2">
                <LinkIcon size={14} className="text-accent-orange" />
                <h4 className="font-bold text-xs">Data URL Reference</h4>
              </div>
              <code className="text-xs bg-secondary p-2 rounded block overflow-x-auto">
                {dataUrl}
              </code>
            </div>
          </div>

          {/* Right: Payload Preview */}
          <div>
            <div className="flex items-center gap-2 mb-3">
              <FileText className="text-accent-blue" size={20} />
              <h3 className="text-lg font-bold">📦 Payload (File Storage)</h3>
            </div>

            <div className="neo-card bg-accent-blue/10 border-accent-blue/30 p-4 mb-4">
              <div className="flex items-center justify-between mb-3">
                <Badge variant="outline" className="text-accent-blue border-accent-blue">
                  {payloadFields.length} fields
                </Badge>
                <Badge variant="outline" className="text-accent-blue border-accent-blue">
                  {formatBytes(JSON.stringify(fullData).length)}
                </Badge>
              </div>

              <div className="space-y-1 max-h-96 overflow-y-auto neo-scrollbar">
                {payloadFields.map(field => (
                  <div key={field} className="flex items-center justify-between text-xs p-2 bg-secondary/30 rounded">
                    <span className="font-semibold">{field}</span>
                    <span className="text-muted">
                      {typeof fullData[field] === 'object'
                        ? `[${Array.isArray(fullData[field]) ? fullData[field].length + ' items' : 'Object'}]`
                        : formatBytes(JSON.stringify(fullData[field]).length)}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            <div className="neo-card bg-secondary/50 p-3">
              <div className="flex items-center justify-between text-xs mb-2">
                <span className="text-muted">Storage Location:</span>
                <Badge variant="outline">
                  {storageLocation === 'local' && '💾 Local'}
                  {storageLocation === 's3' && '☁️ S3'}
                  {storageLocation === 'github' && '🐙 GitHub'}
                </Badge>
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-muted">Will be loaded:</span>
                <span className="font-semibold">On demand</span>
              </div>
            </div>
          </div>
        </div>

        {/* Impact Summary */}
        <div className="neo-card bg-gradient-to-r from-accent-teal/20 to-accent-blue/20 p-4 mt-6">
          <h4 className="font-bold mb-3">🎯 Impact Summary</h4>
          <div className="grid grid-cols-4 gap-4">
            <div className="text-center">
              <p className="text-2xl font-bold text-accent-teal">
                {((1 - JSON.stringify(metadata).length / JSON.stringify(fullData).length) * 100).toFixed(1)}%
              </p>
              <p className="text-xs text-muted">Graph Size Reduction</p>
            </div>
            <div className="text-center">
              <p className="text-2xl font-bold text-accent-blue">{finalMetadataFields.length}</p>
              <p className="text-xs text-muted">Searchable Fields</p>
            </div>
            <div className="text-center">
              <p className="text-2xl font-bold text-accent-orange">{payloadFields.length}</p>
              <p className="text-xs text-muted">Lazy-Loaded Fields</p>
            </div>
            <div className="text-center">
              <p className="text-2xl font-bold text-green-600">Fast</p>
              <p className="text-xs text-muted">Query Performance</p>
            </div>
          </div>
        </div>

        {/* Warning */}
        <div className="neo-card bg-yellow-500/10 border-yellow-500/30 p-4 mt-6">
          <p className="text-sm">
            ⚠️ <strong>Important:</strong> This will create a permanent node in your knowledge graph.
            The metadata structure should match your team's conventions.
          </p>
        </div>

        {/* Actions */}
        <div className="flex gap-3 mt-6">
          <Button variant="outline" onClick={onBack} disabled={committing}>
            ← Back
          </Button>
          <Button 
            onClick={handleCommit}
            className="neo-button-primary flex-1"
            disabled={committing}
          >
            {committing ? (
              <>
                <Loader2 className="animate-spin mr-2" size={16} />
                Saving to ProtoGraph...
              </>
            ) : (
              <>
                <CheckCircle2 className="mr-2" size={16} />
                Commit to ProtoGraph
              </>
            )}
          </Button>
        </div>
      </Card>
    </div>
  );
};

export default FinalReviewAndCommit;