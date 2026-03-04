import { useState } from "react";
import { CheckCircle2, AlertCircle, Sparkles, HelpCircle, ChevronDown, ChevronUp, Info } from "lucide-react";

interface AIClassification {
  artifactId: string;
  proposedType: string;
  confidence: number;
  reasoning: string;
  keyAttributes: Record<string, any>;
  potentialRelationships: Array<any>;
  alternativeTypes: Array<{ type: string; confidence: number }>;
  probeHighlights: Record<string, any>;
}

interface ClassificationReviewProps {
  classification: AIClassification;
  contentPreview: string;
  sourceInfo: string;
  onFeedback: (decision: 'approve' | 'modify' | 'reject', correctedType?: string, feedback?: string) => void;
  onSkip: () => void;
}

const ClassificationReview = ({ 
  classification, 
  contentPreview, 
  sourceInfo,
  onFeedback,
  onSkip 
}: ClassificationReviewProps) => {
  const [correctedType, setCorrectedType] = useState('');
  const [userFeedback, setUserFeedback] = useState('');
  const [showProbeDetails, setShowProbeDetails] = useState(false);
  const [showAlternatives, setShowAlternatives] = useState(false);
  const [showGuidance, setShowGuidance] = useState(true);

  // Get confidence styling
  const getConfidenceColor = (conf: number) => {
    if (conf >= 0.8) return 'text-white-500';
    if (conf >= 0.6) return 'text-white-500';
    return 'text-orange-500';
  };

  const getConfidenceLabel = (conf: number) => {
    if (conf >= 0.8) return 'High confidence';
    if (conf >= 0.6) return 'Medium confidence';
    return 'Low confidence - needs review';
  };

  const handleApproveClassification = async (classification: AIClassification) => {
      const startTime = Date.now();
      
      // 1. Save feedback
      await submitFeedback('approve', classification);
      
      // 2. Commit to ArangoDB AND get connection suggestions
      const response = await fetch('http://localhost:8000/api/ingest/commit', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
              approved_artifacts: [{
                  id: classification.artifactId,
                  title: classification.keyAttributes.title,
                  artifact_type: classification.proposedType,
                  confidence: classification.confidence,
                  ...classification.keyAttributes
              }]
          })
      });
      
      if (response.ok) {
          const result = await response.json();
          
          toast.success(`Artifact saved! Found ${result.discovery.count} potential connections.`);
          
          // 3. If connections found, open ConnectionReviewModal automatically
          if (result.discovery.count > 0) {
              // Store suggestions in state or localStorage
              localStorage.setItem('pending_connections', JSON.stringify(result.discovery.suggestions));
              
              // Trigger modal open
              setShowConnectionReview(true);
          }
      }
  };

  return (
    <div className="space-y-6">
      {/* Guidance Banner */}
      {showGuidance && (
        <div className="neo-card p-4 bg-accent-teal/10 border-accent-teal">
          <div className="flex items-start gap-3">
            <Info className="w-5 h-5 text-accent-teal flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <div className="font-bold text-sm mb-1">What am I being asked?</div>
              <div className="text-sm text-muted-foreground">
                ProtoGraph needs to know <span className="font-semibold">what type of artifact</span> this is so it can:
                <ul className="list-disc ml-5 mt-1 space-y-0.5">
                  <li>Store it with the right structure and metadata</li>
                  <li>Find connections to other similar artifacts</li>
                  <li>Build accurate relationships in your graph</li>
                </ul>
              </div>
            </div>
            <button 
              onClick={() => setShowGuidance(false)}
              className="text-muted-foreground hover:text-foreground"
            >
              ×
            </button>
          </div>
        </div>
      )}

      {/* Document Preview */}
      <div className="neo-card p-6">
        <div className="font-bold mb-2 flex items-center gap-2">
          <span>Your Document</span>
          <span className="text-xs text-muted-foreground font-normal">({sourceInfo})</span>
        </div>
        <div className="bg-secondary/30 border border-border rounded-lg p-4 font-mono text-sm max-h-40 overflow-y-auto">
          {contentPreview}
        </div>
      </div>

      {/* AI Assessment */}
      <div className="neo-card p-6 bg-gradient-to-br from-accent-teal/5 to-transparent border-accent-teal">
        <div className="flex items-start gap-3 mb-4">
          <div className="w-10 h-10 rounded-full bg-accent-teal/20 border-2 border-accent-teal flex items-center justify-center flex-shrink-0">
            <Sparkles className="w-5 h-5 text-accent-teal" />
          </div>
          <div className="flex-1">
            <div className="text-sm text-muted-foreground mb-1">ProtoGraph AI thinks this is:</div>
            <div className="text-2xl font-extrabold text-accent-teal mb-1">
              {classification.proposedType}
            </div>
            <div className={`text-sm font-semibold ${getConfidenceColor(classification.confidence)}`}>
              {getConfidenceLabel(classification.confidence)} ({Math.round(classification.confidence * 100)}%)
            </div>
          </div>
        </div>

        {/* Reasoning */}
        <div className="space-y-3">
          <div>
            <div className="text-sm font-bold mb-1 flex items-center gap-2">
              <span>Why I think this:</span>
              {classification.confidence < 0.7 && (
                <span className="text-xs text-orange-500 bg-orange-500/10 px-2 py-0.5 rounded">
                  Low confidence - please review carefully
                </span>
              )}
            </div>
            <div className="text-sm text-muted-foreground whitespace-pre-line">
              {classification.reasoning}
            </div>
          </div>

          {/* Key Attributes Extracted */}
          <div>
            <div className="text-sm font-bold mb-2">Key information I extracted:</div>
            <div className="grid grid-cols-2 gap-2">
              {Object.entries(classification.keyAttributes)
                .filter(([key]) => !['themes', 'categories', 'tags'].includes(key))
                .slice(0, 6)
                .map(([key, value]) => (
                  <div key={key} className="bg-secondary/50 border border-border rounded p-2">
                    <div className="text-xs text-muted-foreground capitalize">{key.replace(/_/g, ' ')}</div>
                    <div className="text-sm font-semibold truncate">{String(value)}</div>
                  </div>
                ))}
            </div>
          </div>

          {/* Tags */}
          {classification.keyAttributes.tags && classification.keyAttributes.tags.length > 0 && (
            <div>
              <div className="text-sm font-bold mb-1">Tags I identified:</div>
              <div className="flex flex-wrap gap-2">
                {classification.keyAttributes.tags.map((tag: string, idx: number) => (
                  <span key={idx} className="px-2 py-1 bg-accent-teal/10 border border-accent-teal/30 rounded text-xs">
                    {tag}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Probe Details (Collapsible) */}
        {Object.keys(classification.probeHighlights).length > 0 && (
          <div className="mt-4 pt-4 border-t border-border">
            <button
              onClick={() => setShowProbeDetails(!showProbeDetails)}
              className="flex items-center gap-2 text-sm font-bold text-muted-foreground hover:text-foreground transition-colors"
            >
              {showProbeDetails ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
              See what questions I asked myself
            </button>
            {showProbeDetails && (
              <div className="mt-3 space-y-2">
                {Object.entries(classification.probeHighlights).map(([probeName, data]: [string, any]) => (
                  <div key={probeName} className="text-xs bg-secondary/30 rounded p-2">
                    <div className="font-semibold">
                      ✓ {probeName.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                    </div>
                    <div className="text-muted-foreground mt-0.5">
                      Agreement: {Math.round(data.agreement * 100)}% 
                      {data.votes && ` (${data.votes.filter((v: any) => v).length}/${data.votes.length} votes)`}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Alternative Types */}
        {classification.alternativeTypes && classification.alternativeTypes.length > 0 && (
          <div className="mt-4 pt-4 border-t border-border">
            <button
              onClick={() => setShowAlternatives(!showAlternatives)}
              className="flex items-center gap-2 text-sm font-bold text-muted-foreground hover:text-foreground transition-colors"
            >
              {showAlternatives ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
              Other types I considered
            </button>
            {showAlternatives && (
              <div className="mt-3 space-y-2">
                {classification.alternativeTypes.map((alt, idx) => (
                  <div key={idx} className="flex items-center justify-between text-sm bg-secondary/30 rounded p-2">
                    <span className="font-semibold">{alt.type}</span>
                    <span className="text-muted-foreground">
                      {Math.round(alt.confidence * 100)}% confident
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* User Decision Interface */}
      <div className="neo-card p-6">
        <div className="font-bold mb-4 flex items-center gap-2">
          <HelpCircle className="w-5 h-5 text-muted-foreground" />
          <span>Does this look right to you?</span>
        </div>

        <div className="space-y-4">
          {/* Quick Decision Buttons */}
          <div className="grid grid-cols-3 gap-3">
            <button
              onClick={() => onFeedback('approve', undefined, userFeedback)}
              className="neo-button bg-green-500 hover:bg-green-600 text-white py-4 flex-col"
            >
              <CheckCircle2 className="w-6 h-6 mb-1" />
              <span className="text-sm font-bold">Yes, Perfect</span>
              <span className="text-xs opacity-80">This is correct</span>
            </button>

            <button
              onClick={() => {
                if (correctedType) {
                  onFeedback('modify', correctedType, userFeedback);
                }
              }}
              disabled={!correctedType}
              className="neo-button-secondary py-4 flex-col disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Info className="w-6 h-6 mb-1" />
              <span className="text-sm font-bold">Almost Right</span>
              <span className="text-xs">Needs small change</span>
            </button>

            <button
              onClick={() => onFeedback('reject', undefined, userFeedback)}
              className="neo-button bg-red-500 hover:bg-red-600 text-white py-4 flex-col"
            >
              <AlertCircle className="w-6 h-6 mb-1" />
              <span className="text-sm font-bold">No, Wrong</span>
              <span className="text-xs opacity-80">This isn't it</span>
            </button>
          </div>

          {/* Correction Input */}
          <div>
            <label className="text-sm font-bold mb-2 block">
              If you want to change the type, enter the correct one:
            </label>
            <input
              type="text"
              value={correctedType}
              onChange={(e) => setCorrectedType(e.target.value)}
              placeholder="e.g., OperationalRunbook, TrainingScenario, PolicyDocument"
              className="neo-input w-full"
            />
            <div className="text-xs text-muted-foreground mt-1">
              Tip: Use CamelCase for type names. Examples: TestPlan, IncidentReport, ConfigFile
            </div>
          </div>

          {/* Feedback Text */}
          <div>
            <label className="text-sm font-bold mb-2 block">
              Help me learn - what should I look for next time? (optional)
            </label>
            <textarea
              value={userFeedback}
              onChange={(e) => setUserFeedback(e.target.value)}
              placeholder="Example: 'Look for the MEMORANDUM header - that's always a sign of official documents' or 'The technical jargon and code snippets mean this is a runbook, not a policy'"
              className="neo-input w-full min-h-[100px]"
            />
          </div>

          {/* Skip Option */}
          <div className="flex justify-between items-center pt-4 border-t border-border">
            <div className="text-xs text-muted-foreground">
              Not sure? You can skip and come back to this later
            </div>
            <button
              onClick={onSkip}
              className="neo-button-secondary text-sm"
            >
              Skip for Now →
            </button>
          </div>
        </div>
      </div>

      {/* Helpful Context Box */}
      <div className="neo-card p-4 bg-secondary/20">
        <div className="text-xs text-muted-foreground">
          <span className="font-bold">💡 Why this matters:</span> Getting the type right helps ProtoGraph:
          <ul className="list-disc ml-5 mt-1 space-y-0.5">
            <li>Find similar documents automatically</li>
            <li>Suggest connections based on how your team actually works</li>
            <li>Build better visualizations of your organizational knowledge</li>
          </ul>
        </div>
      </div>
    </div>
  );
};

export default ClassificationReview;