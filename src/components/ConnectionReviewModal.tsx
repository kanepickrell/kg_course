import { useState, useEffect } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  CheckCircle2,
  XCircle,
  AlertCircle,
  SkipForward,
  ArrowRight,
  Loader2,
  ChevronLeft,
  ChevronRight,
  Sparkles,
  GitBranch,
  Zap,
  FileText,
  Brain,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

interface ConnectionReviewModalProps {
  open: boolean;
  onClose: () => void;
  onReviewComplete?: () => void;
}

export interface PendingConnection {
  id: string;
  sourceNode: {
    id: string;
    label: string;
    type: string;
    cluster: string;
    description?: string;
    importance?: number;
    metadata?: Record<string, any>;
  };
  targetNode: {
    id: string;
    label: string;
    type: string;
    cluster: string;
    description?: string;
    importance?: number;
    metadata?: Record<string, any>;
  };
  proposedRelationship: string;
  confidence: number;
  reasoning?: string;
  llmModel?: string;
  matchType?: string; // "attribute_match", "text_reference", "llm_semantic"
  matchDetails?: Record<string, any>;
  createdAt: string;
}

export interface ReviewDecision {
  connectionId: string;
  decision: "approve" | "reject" | "modify";
  correctedRelationship?: string;
  feedback?: string;
  reviewedAt: string;
  reviewedBy: string;
}

const RELATIONSHIP_TYPES = [
  { value: "TESTED_BY", label: "Tested By", icon: "🧪" },
  { value: "TESTS", label: "Tests", icon: "🔬" },
  { value: "LEADS_TO", label: "Leads To", icon: "➡️" },
  { value: "REFERENCES", label: "References", icon: "🔖" },
  { value: "PRODUCES", label: "Produces", icon: "🏭" },
  { value: "CONTAINS", label: "Contains", icon: "📁" },
  { value: "COLLABORATION_WITH", label: "Collaboration With", icon: "🤝" },
  { value: "MEMBER_OF", label: "Member Of", icon: "👥" },
  { value: "ASSIGNED_TO", label: "Assigned To", icon: "📋" },
  { value: "RELATED_TO", label: "Related To", icon: "🔀" },
  { value: "depends_on", label: "Depends On", icon: "🔗" },
  { value: "uses", label: "Uses", icon: "🔧" },
  { value: "imports", label: "Imports", icon: "📦" },
  { value: "calls", label: "Calls", icon: "📞" },
  { value: "triggers", label: "Triggers", icon: "⚡" },
  { value: "similar_to", label: "Similar To", icon: "📄" },
];

const ConnectionReviewModal: React.FC<ConnectionReviewModalProps> = ({
  open,
  onClose,
  onReviewComplete,
}) => {
  const [pendingConnections, setPendingConnections] = useState<PendingConnection[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showModifyForm, setShowModifyForm] = useState(false);
  const [correctedRelationship, setCorrectedRelationship] = useState("");
  const [feedback, setFeedback] = useState("");

  const currentConnection = pendingConnections[currentIndex];
  const totalCount = pendingConnections.length;

  useEffect(() => {
    if (open) {
      fetchPendingConnections();
    }
  }, [open]);

  const fetchPendingConnections = async () => {
    setIsLoading(true);
    try {
      const response = await fetch("http://127.0.0.1:8000/connections/pending");
      const data = await response.json();
      setPendingConnections(data.connections || []);
      setCurrentIndex(0);
    } catch (error) {
      console.error("Error fetching pending connections:", error);
      setPendingConnections([]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleDecision = async (decision: "approve" | "reject" | "modify") => {
    if (!currentConnection) return;

    setIsSubmitting(true);

    const reviewDecision: ReviewDecision = {
      connectionId: currentConnection.id,
      decision,
      correctedRelationship: decision === "modify" ? correctedRelationship : undefined,
      feedback: feedback.trim() || undefined,
      reviewedAt: new Date().toISOString(),
      reviewedBy: "user",
    };

    try {
      await fetch("http://127.0.0.1:8000/connections/review", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(reviewDecision),
      });

      if (currentIndex < pendingConnections.length - 1) {
        setCurrentIndex(currentIndex + 1);
        resetForm();
      } else {
        onReviewComplete?.();
        onClose();
      }
    } catch (error) {
      console.error("Error submitting review:", error);
    } finally {
      setIsSubmitting(false);
    }
  };

  const resetForm = () => {
    setShowModifyForm(false);
    setCorrectedRelationship("");
    setFeedback("");
  };

  const goToPrevious = () => {
    if (currentIndex > 0) {
      setCurrentIndex(currentIndex - 1);
      resetForm();
    }
  };

  const goToNext = () => {
    if (currentIndex < totalCount - 1) {
      setCurrentIndex(currentIndex + 1);
      resetForm();
    }
  };

  const getClusterBadge = (cluster: string) => {
    const colors: Record<string, string> = {
      automation: "bg-amber-900 text-amber-200",
      range: "bg-stone-700 text-stone-200",
      content: "bg-emerald-900 text-emerald-200",
      contentdev: "bg-emerald-900 text-emerald-200",
      opfor: "bg-red-900 text-red-200",
      planning: "bg-blue-900 text-blue-200",
    };
    return colors[cluster?.toLowerCase()] || "bg-gray-700 text-gray-200";
  };

  const getConfidenceBadge = (confidence: number) => {
    if (confidence >= 0.9) return "bg-green-900 text-green-200";
    if (confidence >= 0.7) return "bg-emerald-900 text-emerald-200";
    if (confidence >= 0.6) return "bg-yellow-900 text-yellow-200";
    return "bg-red-900 text-red-200";
  };

  const getMatchTypeDisplay = (matchType?: string) => {
    switch (matchType) {
      case "attribute_match":
        return {
          icon: <Zap className="w-4 h-4" />,
          label: "Attribute Match",
          color: "bg-green-900/50 text-green-300 border-green-700",
          description: "Exact attribute value match (fastest, most reliable)"
        };
      case "text_reference":
        return {
          icon: <FileText className="w-4 h-4" />,
          label: "Text Reference",
          color: "bg-blue-900/50 text-blue-300 border-blue-700",
          description: "Name/ID found in description"
        };
      case "llm_semantic":
        return {
          icon: <Brain className="w-4 h-4" />,
          label: "AI Semantic",
          color: "bg-purple-900/50 text-purple-300 border-purple-700",
          description: "LLM-detected semantic relationship"
        };
      default:
        return {
          icon: <Sparkles className="w-4 h-4" />,
          label: "AI Detected",
          color: "bg-gray-700 text-gray-300 border-gray-600",
          description: "AI-suggested connection"
        };
    }
  };

  // Loading state
  if (isLoading) {
    return (
      <Dialog open={open} onOpenChange={onClose}>
        <DialogContent className="max-w-2xl">
          <div className="flex flex-col items-center justify-center py-12">
            <Loader2 className="w-10 h-10 animate-spin text-pink-500 mb-4" />
            <p className="text-sm text-gray-400">Loading pending connections...</p>
          </div>
        </DialogContent>
      </Dialog>
    );
  }

  // Empty state
  if (totalCount === 0) {
    return (
      <Dialog open={open} onOpenChange={onClose}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <CheckCircle2 className="w-5 h-5 text-green-500" />
              All Caught Up!
            </DialogTitle>
          </DialogHeader>
          <div className="py-8 text-center">
            <Sparkles className="w-12 h-12 text-pink-500 mx-auto mb-4" />
            <p className="text-sm text-gray-400 mb-6">
              No pending connection reviews at the moment.
            </p>
            <Button onClick={onClose} variant="outline">
              Close
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    );
  }

  const matchTypeInfo = getMatchTypeDisplay(currentConnection?.matchType);

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-4xl max-h-[85vh] overflow-y-auto">
        {/* Header */}
        <DialogHeader className="pb-4 border-b border-gray-700">
          <div className="flex items-center justify-between">
            <DialogTitle className="flex items-center gap-2">
              <GitBranch className="w-5 h-5 text-pink-500" />
              Connection Review
            </DialogTitle>
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-400">
                {currentIndex + 1} of {totalCount}
              </span>
              <div className="flex gap-1">
                <button
                  onClick={goToPrevious}
                  disabled={currentIndex === 0}
                  className="p-1 rounded hover:bg-gray-700 disabled:opacity-30 disabled:cursor-not-allowed"
                >
                  <ChevronLeft className="w-5 h-5" />
                </button>
                <button
                  onClick={goToNext}
                  disabled={currentIndex === totalCount - 1}
                  className="p-1 rounded hover:bg-gray-700 disabled:opacity-30 disabled:cursor-not-allowed"
                >
                  <ChevronRight className="w-5 h-5" />
                </button>
              </div>
            </div>
          </div>
          {/* Progress bar */}
          <div className="mt-3 h-1.5 bg-gray-700 rounded-full overflow-hidden">
            <div
              className="h-full bg-pink-500"
              style={{ width: `${((currentIndex + 1) / totalCount) * 100}%` }}
            />
          </div>
        </DialogHeader>

        {currentConnection && (
          <div className="space-y-6 pt-4">
            {/* Match Type Badge + Concise Reasoning */}
            <div className="p-4 bg-gray-800 rounded-lg border-l-4 border-teal-500">
              <div className="flex items-start gap-3">
                {/* Match Type Badge */}
                <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full border ${matchTypeInfo.color}`}>
                  {matchTypeInfo.icon}
                  <span className="text-xs font-semibold">{matchTypeInfo.label}</span>
                </div>
                
                {/* Concise Explanation */}
                <div className="flex-1">
                  <p className="text-lg font-semibold text-white">
                    {currentConnection.reasoning}
                  </p>
                  {currentConnection.matchDetails && (
                    <p className="text-xs text-gray-400 mt-1">
                      {currentConnection.matchType === "attribute_match" && 
                        `Matched on: ${currentConnection.matchDetails.attribute} = "${currentConnection.matchDetails.value}"`}
                      {currentConnection.matchType === "text_reference" && 
                        `Found: "${currentConnection.matchDetails.reference}" in description`}
                    </p>
                  )}
                </div>
              </div>
              
              {/* Model info for LLM matches */}
              {currentConnection.matchType === "llm_semantic" && currentConnection.llmModel && (
                <div className="mt-2 text-xs text-gray-500">
                  Model: {currentConnection.llmModel}
                </div>
              )}
            </div>

            {/* Connection Visual */}
            <div className="flex items-center gap-4">
              {/* Source Node */}
              <div className="flex-1 p-4 bg-gray-800 rounded-lg">
                <div className="text-xs text-gray-500 uppercase tracking-wide mb-2">Source</div>
                <div className="font-bold text-lg mb-2">{currentConnection.sourceNode.label}</div>
                <div className="flex flex-wrap gap-2">
                  <span className="px-2 py-1 bg-gray-700 rounded text-xs font-mono">
                    {currentConnection.sourceNode.type}
                  </span>
                  <span className={`px-2 py-1 rounded text-xs ${getClusterBadge(currentConnection.sourceNode.cluster)}`}>
                    {currentConnection.sourceNode.cluster}
                  </span>
                </div>
                {currentConnection.sourceNode.description && (
                  <p className="mt-3 text-sm text-gray-400 line-clamp-2">
                    {currentConnection.sourceNode.description}
                  </p>
                )}
              </div>

              {/* Arrow with Relationship */}
              <div className="flex flex-col items-center gap-1 px-2">
                <ArrowRight className="w-8 h-8 text-pink-500" />
                <span className="text-xs font-bold text-pink-400 text-center max-w-[100px]">
                  {currentConnection.proposedRelationship}
                </span>
              </div>

              {/* Target Node */}
              <div className="flex-1 p-4 bg-gray-800 rounded-lg">
                <div className="text-xs text-gray-500 uppercase tracking-wide mb-2">Target</div>
                <div className="font-bold text-lg mb-2">{currentConnection.targetNode.label}</div>
                <div className="flex flex-wrap gap-2">
                  <span className="px-2 py-1 bg-gray-700 rounded text-xs font-mono">
                    {currentConnection.targetNode.type}
                  </span>
                  <span className={`px-2 py-1 rounded text-xs ${getClusterBadge(currentConnection.targetNode.cluster)}`}>
                    {currentConnection.targetNode.cluster}
                  </span>
                </div>
                {currentConnection.targetNode.description && (
                  <p className="mt-3 text-sm text-gray-400 line-clamp-2">
                    {currentConnection.targetNode.description}
                  </p>
                )}
              </div>
            </div>

            {/* Confidence */}
            <div className="flex items-center justify-center gap-3">
              <span className="text-sm text-gray-400">Confidence:</span>
              <span className={`px-3 py-1 rounded-full text-sm font-bold ${getConfidenceBadge(currentConnection.confidence)}`}>
                {Math.round(currentConnection.confidence * 100)}%
              </span>
              {currentConnection.confidence >= 0.9 && (
                <span className="text-xs text-green-400">✓ High confidence</span>
              )}
            </div>

            {/* Decision Buttons */}
            {!showModifyForm ? (
              <div className="grid grid-cols-3 gap-3">
                <button
                  onClick={() => handleDecision("approve")}
                  disabled={isSubmitting}
                  className="flex flex-col items-center gap-2 p-4 rounded-lg border-2 border-green-600 bg-green-950/30 hover:bg-green-900/40 disabled:opacity-50 transition-colors"
                >
                  {isSubmitting ? (
                    <Loader2 className="w-6 h-6 animate-spin text-green-400" />
                  ) : (
                    <CheckCircle2 className="w-6 h-6 text-green-400" />
                  )}
                  <span className="font-semibold text-green-400">Approve</span>
                  <span className="text-xs text-gray-400">Connection is correct</span>
                </button>

                <button
                  onClick={() => setShowModifyForm(true)}
                  disabled={isSubmitting}
                  className="flex flex-col items-center gap-2 p-4 rounded-lg border-2 border-yellow-600 bg-yellow-950/30 hover:bg-yellow-900/40 disabled:opacity-50 transition-colors"
                >
                  <AlertCircle className="w-6 h-6 text-yellow-400" />
                  <span className="font-semibold text-yellow-400">Modify</span>
                  <span className="text-xs text-gray-400">Change relationship</span>
                </button>

                <button
                  onClick={() => handleDecision("reject")}
                  disabled={isSubmitting}
                  className="flex flex-col items-center gap-2 p-4 rounded-lg border-2 border-red-600 bg-red-950/30 hover:bg-red-900/40 disabled:opacity-50 transition-colors"
                >
                  {isSubmitting ? (
                    <Loader2 className="w-6 h-6 animate-spin text-red-400" />
                  ) : (
                    <XCircle className="w-6 h-6 text-red-400" />
                  )}
                  <span className="font-semibold text-red-400">Reject</span>
                  <span className="text-xs text-gray-400">Not related</span>
                </button>
              </div>
            ) : (
              /* Modify Form */
              <div className="p-4 bg-gray-800 rounded-lg space-y-4">
                <div className="flex items-center justify-between">
                  <h4 className="font-semibold">Modify Relationship</h4>
                  <button
                    onClick={() => setShowModifyForm(false)}
                    className="text-sm text-gray-400 hover:text-white"
                  >
                    Cancel
                  </button>
                </div>

                <div>
                  <label className="block text-sm font-medium mb-2">
                    Correct Relationship Type *
                  </label>
                  <Select
                    value={correctedRelationship}
                    onValueChange={setCorrectedRelationship}
                  >
                    <SelectTrigger className="w-full">
                      <SelectValue placeholder="Select relationship type..." />
                    </SelectTrigger>
                    <SelectContent>
                      {RELATIONSHIP_TYPES.map((rel) => (
                        <SelectItem key={rel.value} value={rel.value}>
                          {rel.icon} {rel.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div>
                  <label className="block text-sm font-medium mb-2">
                    Feedback (Optional)
                  </label>
                  <Textarea
                    value={feedback}
                    onChange={(e) => setFeedback(e.target.value)}
                    placeholder="Why did you change the relationship type?"
                    className="resize-none"
                    rows={3}
                  />
                </div>

                <Button
                  onClick={() => handleDecision("modify")}
                  disabled={!correctedRelationship || isSubmitting}
                  className="w-full"
                >
                  {isSubmitting ? (
                    <>
                      <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                      Submitting...
                    </>
                  ) : (
                    <>
                      <CheckCircle2 className="w-4 h-4 mr-2" />
                      Submit Modification
                    </>
                  )}
                </Button>
              </div>
            )}

            {/* Skip */}
            <div className="flex justify-center pt-2">
              <button
                onClick={goToNext}
                disabled={isSubmitting || currentIndex === totalCount - 1}
                className="flex items-center gap-2 text-sm text-gray-400 hover:text-white disabled:opacity-30"
              >
                <SkipForward className="w-4 h-4" />
                Skip for now
              </button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
};

export default ConnectionReviewModal;