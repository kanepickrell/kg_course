// frontend/src/components/ingestion/IngestionWorkflow.tsx

import React, { useState } from "react";
import ClassificationReview from "./ClassificationReview";
import MetadataSchemaBuilder from "./MetadataSchemaBuilder";
import AISchemaAssessment from "./AISchemaAssessment";
import FinalReviewAndCommit from "./FinalReviewAndCommit";

type WorkflowPhase = "classify" | "schema" | "assessment" | "review";

interface IngestionWorkflowProps {
  artifacts: any[];
  onComplete: () => void;
}

const IngestionWorkflow: React.FC<IngestionWorkflowProps> = ({
  artifacts,
  onComplete
}) => {
  const [currentPhase, setCurrentPhase] = useState<WorkflowPhase>("classify");
  const [classification, setClassification] = useState<any>(null);
  const [metadataSchema, setMetadataSchema] = useState<any>(null);
  const [finalFields, setFinalFields] = useState<string[]>([]);

  // Phase 1 → 2
  const handleClassificationApproved = (approvedClassification: any) => {
    setClassification(approvedClassification);
    setCurrentPhase("schema");
  };

  // Phase 2 → 3
  const handleSchemaComplete = (schema: any) => {
    setMetadataSchema(schema);
    setCurrentPhase("assessment");
  };

  // Phase 3 → 4
  const handleAssessmentComplete = (fields: string[]) => {
    setFinalFields(fields);
    setCurrentPhase("review");
  };

  // Phase 4 → Complete
  const handleCommitSuccess = () => {
    onComplete();
  };

  return (
    <div className="min-h-screen bg-background p-4">
      {/* Progress Indicator */}
      <div className="max-w-6xl mx-auto mb-6">
        <div className="flex items-center justify-between">
          {[
            { phase: "classify", label: "Classification", icon: "1" },
            { phase: "schema", label: "Schema Builder", icon: "2" },
            { phase: "assessment", label: "AI Assessment", icon: "3" },
            { phase: "review", label: "Final Review", icon: "4" }
          ].map((step, idx) => (
            <React.Fragment key={step.phase}>
              <div className="flex items-center gap-2">
                <div 
                  className={`w-8 h-8 rounded-full flex items-center justify-center font-bold transition-all ${
                    currentPhase === step.phase
                      ? 'bg-accent-teal text-white scale-110'
                      : idx < ['classify', 'schema', 'assessment', 'review'].indexOf(currentPhase)
                      ? 'bg-accent-teal/50 text-white'
                      : 'bg-secondary text-muted'
                  }`}
                >
                  {step.icon}
                </div>
                <span className={`text-sm font-semibold ${
                  currentPhase === step.phase ? 'text-foreground' : 'text-muted'
                }`}>
                  {step.label}
                </span>
              </div>
              {idx < 3 && (
                <div className={`flex-1 h-1 mx-2 rounded ${
                  idx < ['classify', 'schema', 'assessment', 'review'].indexOf(currentPhase)
                    ? 'bg-accent-teal'
                    : 'bg-secondary'
                }`} />
              )}
            </React.Fragment>
          ))}
        </div>
      </div>

      {/* Phase Content */}
      {currentPhase === "classify" && (
        <ClassificationReview
          artifacts={artifacts}
          onApprove={handleClassificationApproved}
        />
      )}

      {currentPhase === "schema" && classification && (
        <MetadataSchemaBuilder
          artifactId={classification.artifactId}
          fullData={classification.fullData}
          suggestedType={classification.proposedType}
          onComplete={handleSchemaComplete}
          onBack={() => setCurrentPhase("classify")}
        />
      )}

      {currentPhase === "assessment" && metadataSchema && (
        <AISchemaAssessment
          artifactId={classification.artifactId}
          fullData={classification.fullData}
          userSchema={metadataSchema}
          onComplete={handleAssessmentComplete}
          onBack={() => setCurrentPhase("schema")}
        />
      )}

      {currentPhase === "review" && finalFields.length > 0 && (
        <FinalReviewAndCommit
          artifactId={classification.artifactId}
          fullData={classification.fullData}
          finalMetadataFields={finalFields}
          dataUrl={metadataSchema.dataUrl}
          storageLocation={metadataSchema.storageLocation}
          suggestedType={classification.proposedType}
          onSuccess={handleCommitSuccess}
          onBack={() => setCurrentPhase("assessment")}
        />
      )}
    </div>
  );
};

export default IngestionWorkflow;