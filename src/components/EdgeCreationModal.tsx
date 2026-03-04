import React, { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Link2, ArrowRight, AlertCircle } from "lucide-react";

interface EdgeCreationModalProps {
  open: boolean;
  onClose: () => void;
  sourceNode: { id: string; label: string; cluster: string } | null;
  targetNode: { id: string; label: string; cluster: string } | null;
  onCreateEdge: (edgeData: NewEdgeData) => void;
}

export interface NewEdgeData {
  from: string;
  to: string;
  relationshipType: string;
  weight: number;
  bidirectional: boolean;
  description?: string;
  metadata?: Record<string, any>;
}

// Predefined relationship types
const RELATIONSHIP_TYPES = [
  { value: "depends_on", label: "Depends On", icon: "🔗" },
  { value: "uses", label: "Uses", icon: "🔧" },
  { value: "imports", label: "Imports", icon: "📦" },
  { value: "calls", label: "Calls", icon: "📞" },
  { value: "extends", label: "Extends", icon: "⬆️" },
  { value: "implements", label: "Implements", icon: "✅" },
  { value: "contains", label: "Contains", icon: "📁" },
  { value: "references", label: "References", icon: "🔍" },
  { value: "triggers", label: "Triggers", icon: "⚡" },
  { value: "produces", label: "Produces", icon: "🏭" },
  { value: "consumes", label: "Consumes", icon: "🍽️" },
  { value: "similar_to", label: "Similar To", icon: "🔄" },
  { value: "custom", label: "Custom", icon: "✏️" },
];

const EdgeCreationModal: React.FC<EdgeCreationModalProps> = ({
  open,
  onClose,
  sourceNode,
  targetNode,
  onCreateEdge,
}) => {
  const [relationshipType, setRelationshipType] = useState("");
  const [customRelationship, setCustomRelationship] = useState("");
  const [weight, setWeight] = useState(1.0);
  const [bidirectional, setBidirectional] = useState(false);
  const [description, setDescription] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});

  // Reset form when modal closes
  React.useEffect(() => {
    if (!open) {
      setRelationshipType("");
      setCustomRelationship("");
      setWeight(1.0);
      setBidirectional(false);
      setDescription("");
      setErrors({});
    }
  }, [open]);

  const validate = (): boolean => {
    const newErrors: Record<string, string> = {};

    if (!relationshipType) {
      newErrors.relationshipType = "Relationship type is required";
    }

    if (relationshipType === "custom" && !customRelationship.trim()) {
      newErrors.customRelationship = "Custom relationship name is required";
    }

    if (weight < 0 || weight > 1) {
      newErrors.weight = "Weight must be between 0 and 1";
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleCreate = () => {
    if (!validate() || !sourceNode || !targetNode) return;

    const finalRelationship =
      relationshipType === "custom" ? customRelationship : relationshipType;

    const edgeData: NewEdgeData = {
      from: sourceNode.id,
      to: targetNode.id,
      relationshipType: finalRelationship,
      weight,
      bidirectional,
      description: description.trim(),
      metadata: {
        created_by: "prospector",
        created_at: new Date().toISOString(),
      },
    };

    onCreateEdge(edgeData);
    onClose();
  };

  if (!sourceNode || !targetNode) return null;

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="neo-card max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Link2 className="w-5 h-5 text-accent-teal" />
            Create Edge Connection
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {/* Node Preview */}
          <div className="neo-card p-3 bg-secondary/30">
            <div className="flex items-center justify-between gap-2">
              {/* Source Node */}
              <div className="flex-1 min-w-0">
                <div className="text-xs font-bold text-muted-foreground mb-1">
                  FROM
                </div>
                <div className="flex items-center gap-2">
                  <div
                    className="w-2 h-2 rounded-full flex-shrink-0"
                    style={{
                      backgroundColor:
                        sourceNode.cluster === "automation"
                          ? "#d12727ff"
                          : sourceNode.cluster === "range"
                          ? "#1943b4ff"
                          : sourceNode.cluster === "opfor"
                          ? "#33ee42ff"
                          : "#ed50d3ff",
                    }}
                  />
                  <span className="text-xs font-semibold truncate">
                    {sourceNode.label}
                  </span>
                </div>
              </div>

              {/* Arrow */}
              <div className="flex-shrink-0">
                {bidirectional ? (
                  <div className="flex items-center">
                    <ArrowRight className="w-4 h-4 text-accent-teal" />
                    <ArrowRight className="w-4 h-4 text-accent-teal -ml-2 rotate-180" />
                  </div>
                ) : (
                  <ArrowRight className="w-5 h-5 text-accent-teal" />
                )}
              </div>

              {/* Target Node */}
              <div className="flex-1 min-w-0">
                <div className="text-xs font-bold text-muted-foreground mb-1">
                  TO
                </div>
                <div className="flex items-center gap-2">
                  <div
                    className="w-2 h-2 rounded-full flex-shrink-0"
                    style={{
                      backgroundColor:
                        targetNode.cluster === "automation"
                          ? "#d12727ff"
                          : targetNode.cluster === "range"
                          ? "#1943b4ff"
                          : targetNode.cluster === "opfor"
                          ? "#33ee42ff"
                          : "#ed50d3ff",
                    }}
                  />
                  <span className="text-xs font-semibold truncate">
                    {targetNode.label}
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Relationship Type */}
          <div>
            <label className="text-xs font-bold mb-1 block">
              Relationship Type *
            </label>
            <Select
              value={relationshipType}
              onValueChange={setRelationshipType}
            >
              <SelectTrigger
                className={errors.relationshipType ? "border-red-500" : ""}
              >
                <SelectValue placeholder="Select relationship..." />
              </SelectTrigger>
              <SelectContent>
                {RELATIONSHIP_TYPES.map((rel) => (
                  <SelectItem key={rel.value} value={rel.value}>
                    {rel.icon} {rel.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {errors.relationshipType && (
              <p className="text-xs text-red-500 mt-1 flex items-center gap-1">
                <AlertCircle className="w-3 h-3" />
                {errors.relationshipType}
              </p>
            )}
          </div>

          {/* Custom Relationship Name */}
          {relationshipType === "custom" && (
            <div>
              <label className="text-xs font-bold mb-1 block">
                Custom Relationship Name *
              </label>
              <Input
                value={customRelationship}
                onChange={(e) => setCustomRelationship(e.target.value)}
                placeholder="e.g., configures, deploys_to, monitors"
                className={
                  errors.customRelationship ? "border-red-500" : ""
                }
              />
              {errors.customRelationship && (
                <p className="text-xs text-red-500 mt-1 flex items-center gap-1">
                  <AlertCircle className="w-3 h-3" />
                  {errors.customRelationship}
                </p>
              )}
            </div>
          )}

          {/* Weight */}
          <div>
            <label className="text-xs font-bold mb-1 block">
              Connection Weight (0-1)
            </label>
            <div className="flex items-center gap-3">
              <Input
                type="number"
                min="0"
                max="1"
                step="0.1"
                value={weight}
                onChange={(e) => setWeight(parseFloat(e.target.value))}
                className={`flex-1 ${errors.weight ? "border-red-500" : ""}`}
              />
              <div className="text-xs text-muted-foreground">
                {weight === 1
                  ? "Strong"
                  : weight >= 0.7
                  ? "Medium"
                  : "Weak"}
              </div>
            </div>
            {errors.weight && (
              <p className="text-xs text-red-500 mt-1 flex items-center gap-1">
                <AlertCircle className="w-3 h-3" />
                {errors.weight}
              </p>
            )}
          </div>

          {/* Bidirectional */}
          <div className="flex items-center justify-between py-2 px-3 bg-secondary/30 rounded-lg">
            <div>
              <div className="text-xs font-bold">Bidirectional</div>
              <div className="text-[10px] text-muted-foreground">
                Connection works in both directions
              </div>
            </div>
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                checked={bidirectional}
                onChange={(e) => setBidirectional(e.target.checked)}
                className="sr-only peer"
              />
              <div className="w-11 h-6 bg-secondary peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-accent-teal rounded-full peer peer-checked:after:translate-x-full rtl:peer-checked:after:-translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:start-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-accent-teal"></div>
            </label>
          </div>

          {/* Description */}
          <div>
            <label className="text-xs font-bold mb-1 block">
              Description (Optional)
            </label>
            <Textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Describe this connection..."
              className="min-h-[60px] resize-none text-sm"
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={handleCreate} className="neo-button">
            <Link2 className="w-4 h-4 mr-2" />
            Create Edge
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default EdgeCreationModal;