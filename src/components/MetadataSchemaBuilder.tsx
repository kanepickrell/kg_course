// frontend/src/components/MetadataSchemaBuilder.tsx

import React, { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { AlertCircle, Plus, X, Link as LinkIcon } from "lucide-react";
import { toast } from "sonner";

interface MetadataSchemaBuilderProps {
  artifactId: string;
  fullData: any;
  suggestedType: string;
  onComplete: (schema: MetadataSchema) => void;
  onBack: () => void;
}

interface MetadataSchema {
  typeName: string;
  metadataFields: string[];
  payloadStructure: Record<string, string>;
  storageLocation: "local" | "s3" | "github";
  dataUrl: string;
}

const MetadataSchemaBuilder: React.FC<MetadataSchemaBuilderProps> = ({
  artifactId,
  fullData,
  suggestedType,
  onComplete,
  onBack
}) => {
  const [selectedFields, setSelectedFields] = useState<string[]>([]);
  const [customField, setCustomField] = useState("");
  const [storageLocation, setStorageLocation] = useState<"local" | "s3" | "github">("local");
  const [dataUrl, setDataUrl] = useState("");
  const [artifactTypeName, setArtifactTypeName] = useState(suggestedType || "");
  const [isNewType] = useState(true);

  // Extract all field names from fullData
  const allFields = Object.keys(fullData).filter(key => !key.startsWith('_'));

  // Auto-select common metadata fields
  useEffect(() => {
    const autoSelect = allFields.filter(field => 
      ['name', 'title', 'category', 'subcategory', 'description', 
       'tags', 'tactic', 'technique', 'cluster', 'riskLevel', 'importance',
       'icon', 'executionType', 'estimatedDuration'].includes(field)
    );
    setSelectedFields(autoSelect);
  }, [fullData]);

  // Auto-generate dataUrl based on storage location
  useEffect(() => {
    const cleanId = artifactId.replace(/[^a-zA-Z0-9_-]/g, '_');
    
    switch (storageLocation) {
      case 'local':
        setDataUrl(`/api/ingest/payloads/${cleanId}.json`);
        break;
      case 's3':
        setDataUrl(`s3://protograph-payloads/${artifactTypeName}/${cleanId}.json`);
        break;
      case 'github':
        setDataUrl(`https://raw.githubusercontent.com/your-org/protograph-data/main/${artifactTypeName}/${cleanId}.json`);
        break;
    }
  }, [artifactId, storageLocation, artifactTypeName]);

  const toggleField = (field: string) => {
    if (selectedFields.includes(field)) {
      setSelectedFields(selectedFields.filter(f => f !== field));
    } else {
      setSelectedFields([...selectedFields, field]);
    }
  };

  const addCustomField = () => {
    if (customField && !selectedFields.includes(customField) && !allFields.includes(customField)) {
      setSelectedFields([...selectedFields, customField]);
      setCustomField("");
      toast.success(`Added custom field: ${customField}`);
    }
  };

  const getFieldValue = (field: string) => {
    const value = fullData[field];
    if (typeof value === 'string') {
      return value.length > 50 ? value.substring(0, 50) + '...' : value;
    }
    if (Array.isArray(value)) {
      return `[${value.length} items]`;
    }
    if (typeof value === 'object' && value !== null) {
      return '[Object]';
    }
    return String(value);
  };

  const estimateMetadataSize = () => {
    const metadata = selectedFields.reduce((acc, field) => {
      if (field in fullData) {
        acc[field] = fullData[field];
      }
      return acc;
    }, {} as any);
    return JSON.stringify(metadata).length;
  };

  const estimatePayloadSize = () => {
    return JSON.stringify(fullData).length;
  };

  const handleContinue = () => {
    if (!artifactTypeName.trim()) {
      toast.error("Please name this artifact type");
      return;
    }
    
    if (selectedFields.length === 0) {
      toast.error("Please select at least one metadata field");
      return;
    }

    // Build payload structure from remaining fields
    const payloadFields = allFields.filter(field => !selectedFields.includes(field));
    const payloadStructure: Record<string, string> = {};
    
    payloadFields.forEach(field => {
      const value = fullData[field];
      if (Array.isArray(value)) {
        payloadStructure[field] = "array";
      } else if (typeof value === 'object' && value !== null) {
        payloadStructure[field] = "object";
      } else if (typeof value === 'number') {
        payloadStructure[field] = "number";
      } else if (typeof value === 'boolean') {
        payloadStructure[field] = "boolean";
      } else {
        payloadStructure[field] = "string";
      }
    });

    const schema: MetadataSchema = {
      typeName: artifactTypeName.trim(),
      metadataFields: selectedFields,
      payloadStructure: payloadStructure,
      storageLocation: storageLocation,
      dataUrl: dataUrl
    };

    console.log("📋 Schema built:", schema);
    onComplete(schema);
  };

  // Categorize fields
  const recommendedFields = allFields.filter(field => 
    ['name', 'title', 'category', 'subcategory', 'description', 
     'tags', 'tactic', 'technique', 'cluster', 'riskLevel', 'importance', 
     'icon', 'executionType', 'estimatedDuration'].includes(field)
  );

  const otherFields = allFields.filter(field => !recommendedFields.includes(field));

  return (
    <div className="w-full">
      {/* Type Name Input */}
      <div className="neo-card p-4 bg-accent-teal/10 border-accent-teal/30 mb-6">
        <label className="text-sm font-semibold mb-2 block">
          What should we call this type of artifact?
        </label>
        <input
          type="text"
          value={artifactTypeName}
          onChange={(e) => setArtifactTypeName(e.target.value)}
          className="w-full p-2 bg-secondary border-2 border-border rounded focus:border-accent-teal focus:outline-none transition-colors"
          placeholder="e.g., Library Module, Attack Scenario, Tool Configuration"
        />
        
        {isNewType && (
          <div className="mt-2 flex items-center gap-2 text-xs text-accent-teal">
            <span className="font-bold">✨ NEW TYPE</span>
            <span>This will create a new artifact type in ProtoGraph</span>
          </div>
        )}
        
        <p className="text-xs text-muted-foreground mt-2">
          AI suggested: <strong>{suggestedType}</strong>
        </p>
      </div>

      {/* Info Alert */}
      <div className="neo-card bg-accent-blue/10 border-accent-blue/30 p-4 mb-6">
        <div className="flex gap-3">
          <AlertCircle className="text-accent-blue flex-shrink-0 mt-1" size={20} />
          <div>
            <h3 className="font-bold mb-1">What are Metadata Fields?</h3>
            <p className="text-sm text-muted-foreground">
              Metadata fields are lightweight, searchable properties that help ProtoGraph find and connect
              artifacts. Choose fields that are: <strong>short</strong>, <strong>searchable</strong>, and 
              <strong> used for filtering</strong>.
            </p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-6">
        {/* Left Column: Field Selection */}
        <div>
          <h3 className="text-lg font-bold mb-3">📊 Available Fields</h3>
          
          {/* Recommended Fields */}
          {recommendedFields.length > 0 && (
            <div className="mb-4">
              <Label className="text-xs text-muted-foreground mb-2 block">RECOMMENDED METADATA</Label>
              <div className="space-y-2 max-h-64 overflow-y-auto neo-scrollbar">
                {recommendedFields.map(field => (
                  <div 
                    key={field} 
                    className="flex items-center gap-3 p-2 rounded hover:bg-secondary/50 cursor-pointer"
                    onClick={() => toggleField(field)}
                  >
                    <Checkbox 
                      checked={selectedFields.includes(field)}
                      onCheckedChange={() => toggleField(field)}
                    />
                    <div className="flex-1 min-w-0">
                      <div className="font-semibold text-sm">{field}</div>
                      <div className="text-xs text-muted-foreground truncate">
                        {getFieldValue(field)}
                      </div>
                    </div>
                    {selectedFields.includes(field) && (
                      <Badge variant="outline" className="text-accent-teal border-accent-teal text-xs">
                        ✓
                      </Badge>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Other Fields */}
          {otherFields.length > 0 && (
            <div className="mb-4">
              <Label className="text-xs text-muted-foreground mb-2 block">OTHER FIELDS (Usually Payload)</Label>
              <div className="space-y-2 max-h-48 overflow-y-auto neo-scrollbar">
                {otherFields.map(field => (
                  <div 
                    key={field} 
                    className="flex items-center gap-3 p-2 rounded hover:bg-secondary/50 cursor-pointer"
                    onClick={() => toggleField(field)}
                  >
                    <Checkbox 
                      checked={selectedFields.includes(field)}
                      onCheckedChange={() => toggleField(field)}
                    />
                    <div className="flex-1 min-w-0">
                      <div className="font-semibold text-sm">{field}</div>
                      <div className="text-xs text-muted-foreground truncate">
                        {getFieldValue(field)}
                      </div>
                    </div>
                    {selectedFields.includes(field) && (
                      <Badge variant="outline" className="text-accent-teal border-accent-teal text-xs">
                        ✓
                      </Badge>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Add Custom Field */}
          <div className="mt-4">
            <Label className="text-xs text-muted-foreground mb-2 block">ADD CUSTOM FIELD</Label>
            <div className="flex gap-2">
              <Input
                placeholder="field_name"
                value={customField}
                onChange={(e) => setCustomField(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && addCustomField()}
                className="text-sm"
              />
              <Button size="sm" onClick={addCustomField} className="px-3">
                <Plus size={16} />
              </Button>
            </div>
          </div>
        </div>

        {/* Right Column: Preview */}
        <div>
          <h3 className="text-lg font-bold mb-3">👁️ Preview</h3>

          {/* Metadata Preview */}
          <div className="neo-card bg-accent-teal/10 border-accent-teal/30 p-4 mb-4">
            <div className="flex items-center justify-between mb-3">
              <h4 className="font-bold text-sm">📊 Metadata (In Graph)</h4>
              <Badge variant="outline" className="text-accent-teal border-accent-teal text-xs">
                {(estimateMetadataSize() / 1024).toFixed(2)} KB
              </Badge>
            </div>
            <div className="space-y-1 max-h-48 overflow-y-auto neo-scrollbar">
              {selectedFields.map(field => (
                <div key={field} className="flex items-center justify-between text-xs bg-secondary/50 p-2 rounded">
                  <span className="font-semibold">{field}</span>
                  <button 
                    onClick={(e) => {
                      e.stopPropagation();
                      toggleField(field);
                    }} 
                    className="text-red-500 hover:text-red-700"
                  >
                    <X size={14} />
                  </button>
                </div>
              ))}
              {selectedFields.length === 0 && (
                <p className="text-xs text-muted-foreground italic text-center py-4">
                  No fields selected
                </p>
              )}
            </div>
          </div>

          {/* Storage Location */}
          <div className="neo-card bg-secondary/50 p-4 mb-4">
            <Label className="text-sm font-bold mb-2 block">📦 Payload Storage</Label>
            <div className="space-y-2">
              {(['local', 's3', 'github'] as const).map(location => (
                <div key={location} className="flex items-center gap-2">
                  <input
                    type="radio"
                    id={location}
                    checked={storageLocation === location}
                    onChange={() => setStorageLocation(location)}
                    className="cursor-pointer"
                  />
                  <label htmlFor={location} className="text-sm cursor-pointer flex-1">
                    {location === 'local' && '💾 Local File System'}
                    {location === 's3' && '☁️ S3/MinIO'}
                    {location === 'github' && '🐙 GitHub Repository'}
                  </label>
                </div>
              ))}
            </div>
          </div>

          {/* Data URL Preview */}
          <div className="neo-card bg-accent-orange/10 border-accent-orange/30 p-4 mb-4">
            <div className="flex items-center gap-2 mb-2">
              <LinkIcon size={16} className="text-accent-orange" />
              <h4 className="font-bold text-sm">Generated Data URL</h4>
            </div>
            <code className="text-xs bg-secondary/50 p-2 rounded block overflow-x-auto">
              {dataUrl}
            </code>
            <p className="text-xs text-muted-foreground mt-2">
              This URL will be stored in the graph node for on-demand payload loading.
            </p>
          </div>

          {/* Size Comparison */}
          <div className="neo-card p-4">
            <h4 className="font-bold text-sm mb-3">📊 Size Comparison</h4>
            <div className="space-y-2">
              <div className="flex justify-between items-center">
                <span className="text-xs">Metadata (graph):</span>
                <Badge variant="outline" className="text-accent-teal border-accent-teal text-xs">
                  {(estimateMetadataSize() / 1024).toFixed(2)} KB
                </Badge>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-xs">Full Payload:</span>
                <Badge variant="outline" className="text-xs">
                  {(estimatePayloadSize() / 1024).toFixed(2)} KB
                </Badge>
              </div>
              <div className="flex justify-between items-center pt-2 border-t">
                <span className="text-xs font-bold">Space Saved:</span>
                <Badge variant="outline" className="text-green-600 border-green-600 text-xs">
                  {((1 - estimateMetadataSize() / estimatePayloadSize()) * 100).toFixed(1)}%
                </Badge>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Actions */}
      <div className="flex gap-3 mt-6">
        <Button variant="outline" onClick={onBack}>
          ← Back
        </Button>
        <Button 
          onClick={handleContinue}
          className="neo-button-primary flex-1"
          disabled={selectedFields.length === 0 || !artifactTypeName.trim()}
        >
          Continue to Review →
        </Button>
      </div>
    </div>
  );
};

export default MetadataSchemaBuilder;