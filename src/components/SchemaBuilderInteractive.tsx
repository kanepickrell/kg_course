// frontend/src/components/ingestion/SchemaBuilderInteractive.tsx

import React, { useState, DragEvent } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ArrowLeft, Plus, Trash2, GripVertical } from "lucide-react";
import { toast } from "sonner";

interface IdentifiedChunk {
  id: string;
  content: string;
  purpose: string;
  suggestedField: string;
  confidence: number;
}

interface SchemaBuilderInteractiveProps {
  artifactId: string;
  chunks: IdentifiedChunk[];
  suggestedStructure?: any;
  initialTypeName?: string;
  onComplete: (result: {
    typeName: string;
    metadataFields: string[];
    payloadStructure: any;
  }) => void;
  onBack: () => void;
}

interface PayloadField {
  id: string;
  name: string;
  type: "string" | "number" | "boolean" | "array" | "object";
  children?: PayloadField[];
}

const SchemaBuilderInteractive: React.FC<SchemaBuilderInteractiveProps> = ({
  artifactId,
  chunks,
  suggestedStructure,
  initialTypeName = "",
  onComplete,
  onBack,
}) => {
  const [typeName, setTypeName] = useState(initialTypeName);
  const [metadataSchema, setMetadataSchema] = useState<{ [key: string]: any }>({});
  const [payloadStructure, setPayloadStructure] = useState<PayloadField[]>([]);
  const [usedChunks, setUsedChunks] = useState<Set<string>>(new Set());
  const [draggedChunk, setDraggedChunk] = useState<IdentifiedChunk | null>(null);
  
  const handleChunkDragStart = (chunk: IdentifiedChunk) => {
    setDraggedChunk(chunk);
  };

  const handleDropToMetadata = (e: DragEvent) => {
    e.preventDefault();
    
    if (!draggedChunk) return;
    
    // Add to metadata schema
    setMetadataSchema(prev => ({
      ...prev,
      [draggedChunk.suggestedField]: draggedChunk.content
    }));
    
    // Mark as used
    setUsedChunks(prev => new Set(prev).add(draggedChunk.id));
    
    toast.success(`Added "${draggedChunk.suggestedField}" to metadata`);
    setDraggedChunk(null);
  };

  const handleDropToPayload = (e: DragEvent) => {
    e.preventDefault();
    
    if (!draggedChunk) return;
    
    // Add to payload structure
    const newField: PayloadField = {
      id: `field_${Date.now()}`,
      name: draggedChunk.suggestedField,
      type: inferType(draggedChunk.content),
      children: []
    };
    
    setPayloadStructure(prev => [...prev, newField]);
    setUsedChunks(prev => new Set(prev).add(draggedChunk.id));
    
    toast.success(`Added "${draggedChunk.suggestedField}" to payload`);
    setDraggedChunk(null);
  };

  const inferType = (content: string): "string" | "number" | "array" | "object" => {
    if (content.includes("[") || content.toLowerCase().includes("list")) return "array";
    if (content.includes("{") || content.toLowerCase().includes("object")) return "object";
    if (!isNaN(Number(content))) return "number";
    return "string";
  };

  const removeFromMetadata = (field: string) => {
    const newMetadata = { ...metadataSchema };
    delete newMetadata[field];
    setMetadataSchema(newMetadata);
    
    // Find and unmark the chunk
    const chunk = chunks.find(c => c.suggestedField === field);
    if (chunk) {
      setUsedChunks(prev => {
        const newSet = new Set(prev);
        newSet.delete(chunk.id);
        return newSet;
      });
    }
  };

  const removeFromPayload = (fieldId: string) => {
    setPayloadStructure(prev => prev.filter(f => f.id !== fieldId));
  };

  const addManualField = (target: "metadata" | "payload", type: PayloadField["type"] = "string") => {
    const fieldName = prompt(`Enter field name:`);
    if (!fieldName) return;

    if (target === "metadata") {
      setMetadataSchema(prev => ({
        ...prev,
        [fieldName]: ""
      }));
      toast.success(`Added "${fieldName}" to metadata`);
    } else {
      const newField: PayloadField = {
        id: `manual_${Date.now()}`,
        name: fieldName,
        type,
        children: type === "object" || type === "array" ? [] : undefined
      };
      setPayloadStructure(prev => [...prev, newField]);
      toast.success(`Added "${fieldName}" to payload`);
    }
  };

  const handleComplete = async () => {
    if (!typeName.trim()) {
      toast.error("Please name this artifact type");
      return;
    }

    if (Object.keys(metadataSchema).length === 0) {
      toast.error("Please add at least one metadata field");
      return;
    }

    const result = {
      typeName: typeName.trim(),
      metadataFields: Object.keys(metadataSchema),
      payloadStructure: payloadStructure.reduce((acc, field) => {
        acc[field.name] = field.type;
        return acc;
      }, {} as any)
    };

    onComplete(result);
  };

  const renderPayloadField = (field: PayloadField, depth: number = 0) => {
    return (
      <div 
        key={field.id}
        className="mb-2"
        style={{ marginLeft: `${depth * 20}px` }}
      >
        <div className="flex items-center gap-2 p-2 bg-secondary rounded hover:bg-secondary/80 transition-colors">
          <GripVertical size={14} className="text-muted-foreground" />
          <span className="text-sm font-semibold">{field.name}</span>
          <span className="text-xs px-2 py-0.5 bg-accent-teal/20 text-accent-teal rounded">
            {field.type}
          </span>
          <button
            onClick={() => removeFromPayload(field.id)}
            className="ml-auto text-red-400 hover:text-red-300"
          >
            <Trash2 size={14} />
          </button>
        </div>
        
        {field.children && field.children.length > 0 && (
          <div className="mt-1">
            {field.children.map(child => renderPayloadField(child, depth + 1))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="space-y-6">
      {/* Header: Type Name */}
      <div className="neo-card p-4 bg-accent-teal/10 border-accent-teal/30">
        <label className="text-sm font-semibold mb-2 block">
          What should we call this type of artifact?
        </label>
        <input
          type="text"
          value={typeName}
          onChange={(e) => setTypeName(e.target.value)}
          className="neo-input w-full"
          placeholder="e.g., Library Module, Attack Scenario, Tool Configuration"
        />
        <div className="mt-2 flex items-center gap-2 text-xs">
          <span className="font-bold text-accent-teal">✨ NEW TYPE</span>
          <span className="text-muted-foreground">
            This will create a new artifact type in ProtoGraph
          </span>
        </div>
      </div>

      {/* Main Grid: Chunks + Schema Builder */}
      <div className="grid grid-cols-2 gap-6">
        {/* LEFT: AI-Identified Chunks */}
        <div>
          <h3 className="font-bold mb-4 flex items-center gap-2">
            <span>AI-Identified Data Chunks</span>
            <span className="text-xs text-muted-foreground">
              ({chunks.length} detected)
            </span>
          </h3>
          
          <div className="space-y-3 max-h-[600px] overflow-y-auto pr-2">
            {chunks.map(chunk => (
              <div
                key={chunk.id}
                draggable={!usedChunks.has(chunk.id)}
                onDragStart={() => handleChunkDragStart(chunk)}
                className={`neo-card p-3 transition-all ${
                  usedChunks.has(chunk.id)
                    ? 'opacity-40 cursor-not-allowed'
                    : 'cursor-move hover:border-accent-teal hover:scale-102'
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="font-semibold text-sm">{chunk.suggestedField}</span>
                  {usedChunks.has(chunk.id) && (
                    <span className="text-xs text-accent-teal">✓ Used</span>
                  )}
                </div>
                <div className="text-xs text-muted-foreground mb-1">{chunk.purpose}</div>
                <div className="text-xs mt-1 line-clamp-2 bg-secondary/50 p-1 rounded">
                  {chunk.content}
                </div>
                <div className="text-xs text-accent-teal mt-1 font-semibold">
                  {(chunk.confidence * 100).toFixed(0)}% confident
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* RIGHT: Schema Structure Builder */}
        <div>
          <h3 className="font-bold mb-4">Define Structure</h3>

          {/* Metadata Section */}
          <div className="mb-6">
            <div className="flex items-center justify-between mb-2">
              <h4 className="font-semibold text-sm">Metadata (Searchable)</h4>
              <Button
                onClick={() => addManualField("metadata")}
                variant="ghost"
                size="sm"
                className="text-xs"
              >
                <Plus size={12} className="mr-1" />
                Add Field
              </Button>
            </div>
            
            <div
              className="neo-card p-4 min-h-32 bg-accent-teal/10 border-accent-teal/30"
              onDrop={handleDropToMetadata}
              onDragOver={(e) => e.preventDefault()}
            >
              {Object.keys(metadataSchema).length === 0 ? (
                <div className="text-center text-sm text-muted-foreground py-8">
                  Drop chunks here to make them searchable in the graph
                </div>
              ) : (
                <div className="space-y-2">
                  {Object.keys(metadataSchema).map(field => (
                    <div
                      key={field}
                      className="flex items-center justify-between p-2 bg-secondary rounded"
                    >
                      <span className="text-sm font-semibold">{field}</span>
                      <button
                        onClick={() => removeFromMetadata(field)}
                        className="text-red-400 hover:text-red-300"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Payload Section */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <h4 className="font-semibold text-sm">Payload Structure</h4>
              <div className="flex gap-1">
                <Button
                  onClick={() => addManualField("payload", "array")}
                  variant="ghost"
                  size="sm"
                  className="text-xs"
                >
                  <Plus size={12} className="mr-1" />
                  Array
                </Button>
                <Button
                  onClick={() => addManualField("payload", "object")}
                  variant="ghost"
                  size="sm"
                  className="text-xs"
                >
                  <Plus size={12} className="mr-1" />
                  Object
                </Button>
                <Button
                  onClick={() => addManualField("payload", "string")}
                  variant="ghost"
                  size="sm"
                  className="text-xs"
                >
                  <Plus size={12} className="mr-1" />
                  Field
                </Button>
              </div>
            </div>

            <div
              className="neo-card p-4 min-h-32 bg-secondary/20"
              onDrop={handleDropToPayload}
              onDragOver={(e) => e.preventDefault()}
            >
              {payloadStructure.length === 0 ? (
                <div className="text-center text-sm text-muted-foreground py-8">
                  Drop chunks here or use buttons above to build payload structure
                </div>
              ) : (
                <div className="space-y-1">
                  {payloadStructure.map(field => renderPayloadField(field))}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Summary */}
      <div className="neo-card p-4 bg-secondary/50">
        <h4 className="font-semibold mb-2 text-sm">Summary</h4>
        <div className="grid grid-cols-3 gap-4 text-sm">
          <div>
            <span className="text-muted-foreground">Type Name:</span>
            <p className="font-bold">{typeName || "(not set)"}</p>
          </div>
          <div>
            <span className="text-muted-foreground">Metadata Fields:</span>
            <p className="font-bold">{Object.keys(metadataSchema).length}</p>
          </div>
          <div>
            <span className="text-muted-foreground">Payload Fields:</span>
            <p className="font-bold">{payloadStructure.length}</p>
          </div>
        </div>
      </div>

      {/* Actions */}
      <div className="flex gap-3">
        <Button
          onClick={onBack}
          variant="outline"
          className="flex-1 flex items-center gap-2"
        >
          <ArrowLeft size={16} />
          Back
        </Button>
        <Button
          onClick={handleComplete}
          className="neo-button-primary flex-1"
          disabled={!typeName.trim() || Object.keys(metadataSchema).length === 0}
        >
          Save Schema & Continue
        </Button>
      </div>
    </div>
  );
};

export default SchemaBuilderInteractive;