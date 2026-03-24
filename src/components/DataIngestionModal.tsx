import { useState, useEffect } from "react";
import {
  X,
  Upload,
  CheckCircle,
  AlertTriangle,
  Loader2,
  ChevronRight,
  RefreshCw,
  GitBranch,
  Database,
  Layers,
  Sparkles,
} from "lucide-react";

import LibraryModuleWizard from "./LibraryModuleWizard";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";
const GRAPHDB_BASE = "http://localhost:8000";

// =====================================================
// TYPES
// =====================================================

interface SchemaProperty {
  name: string;
  label?: string;
  type: string;
  required: boolean;
  description?: string;
  taxonomy?: string;
}

interface ArtifactType {
  label: string;
  uri: string;
  definition: string;
  collection: string;
  properties: SchemaProperty[];
}

interface TaxonomyTerm {
  uri: string;
  label: string;
  aliases?: string[];
}

interface CommitResult {
  success: boolean;
  artifact_type: string;
  collection: string;
  document_id: string;
  document_key: string;
  payload_url?: string;
  payload_saved: boolean;
  shacl_error?: string;
  edges_created: Array<{
    _id: string;
    _from: string;
    _to: string;
    relationship_type: string;
    source: string;
    confidence: number;
  }>;
  edge_count: number;
}

interface DataIngestionModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: (result: any) => void;
}

// =====================================================
// MAIN COMPONENT
// =====================================================

export default function DataIngestionModal({
  isOpen,
  onClose,
  onSuccess,
}: DataIngestionModalProps) {
  const [step, setStep] = useState<"select" | "fill" | "review" | "success">("select");
  const [isCommitting, setIsCommitting] = useState(false);
  const [isValidating, setIsValidating] = useState(false);
  const [isExtracting, setIsExtracting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Type selection
  const [availableTypes, setAvailableTypes] = useState<ArtifactType[]>([]);
  const [selectedType, setSelectedType] = useState<ArtifactType | null>(null);

  // Form data
  const [attributes, setAttributes] = useState<Record<string, any>>({});
  const [validationErrors, setValidationErrors] = useState<Array<{ field: string; message: string }>>([]);
  const [normalizations, setNormalizations] = useState<Array<{ field: string; original: string; normalized: string }>>([]);

  // Taxonomy caches
  const [taxonomyTerms, setTaxonomyTerms] = useState<Record<string, TaxonomyTerm[]>>({});

  // Commit result
  const [commitResult, setCommitResult] = useState<CommitResult | null>(null);

  // AI autofill
  const [showAiFill, setShowAiFill] = useState(false);
  const [rawData, setRawData] = useState("");
  const [extractionModel, setExtractionModel] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      fetchAvailableTypes();
    }
  }, [isOpen]);

  // Load taxonomy terms when a type is selected
  useEffect(() => {
    if (selectedType) {
      const taxonomyFields = selectedType.properties.filter((p) => p.taxonomy);
      taxonomyFields.forEach((p) => {
        if (p.taxonomy && !taxonomyTerms[p.taxonomy]) {
          fetchTaxonomyTerms(p.taxonomy);
        }
      });
    }
  }, [selectedType]);

  const fetchAvailableTypes = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/ingest/types`);
      if (res.ok) {
        const data = await res.json();
        setAvailableTypes(data.types || []);
      }
    } catch (err) {
      console.error("Failed to fetch types:", err);
    }
  };

  const fetchTaxonomyTerms = async (schemeId: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/ingest/taxonomies/${schemeId}`);
      if (res.ok) {
        const data = await res.json();
        setTaxonomyTerms((prev) => ({
          ...prev,
          [schemeId]: data.terms || [],
        }));
      }
    } catch (err) {
      console.error(`Failed to fetch taxonomy ${schemeId}:`, err);
    }
  };

  const handleSelectType = (type: ArtifactType) => {
    setSelectedType(type);
    // Pre-fill empty attributes for all properties
    const initial: Record<string, any> = {};
    type.properties.forEach((p) => {
      initial[p.name] = "";
    });
    setAttributes(initial);
    setValidationErrors([]);
    setNormalizations([]);
    setError(null);
    setRawData("");
    setShowAiFill(false);
    setExtractionModel(null);
    setStep("fill");
  };

  const handleValidate = async () => {
    if (!selectedType) return;

    setIsValidating(true);
    setError(null);

    try {
      const res = await fetch(`${API_BASE}/api/ingest/validate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          type: selectedType.label,
          attributes: cleanAttributes(),
        }),
      });

      const result = await res.json();

      if (res.ok) {
        setValidationErrors(result.errors || []);
        setNormalizations(result.normalizations || []);
        if (result.normalized_attributes) {
          setAttributes(result.normalized_attributes);
        }
        if (result.valid) {
          setStep("review");
        }
      } else {
        // 422 validation error
        const errors = result.detail?.errors || [];
        setValidationErrors(errors);
        if (errors.length > 0) {
          setError("Please fix the validation errors below.");
        }
      }
    } catch (err: any) {
      setError(err.message || "Validation failed");
    } finally {
      setIsValidating(false);
    }
  };

  const handleCommit = async () => {
    if (!selectedType) return;

    setIsCommitting(true);
    setError(null);

    try {
      const res = await fetch(`${API_BASE}/api/ingest/commit`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          type: selectedType.label,
          attributes: cleanAttributes(),
        }),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        const msg = errData.detail?.message || errData.detail || `Commit failed: ${res.status}`;
        throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
      }

      const result: CommitResult = await res.json();
      setCommitResult(result);
      setStep("success");
      onSuccess?.(result);
    } catch (err: any) {
      setError(err.message || "Commit failed");
    } finally {
      setIsCommitting(false);
    }
  };

  const cleanAttributes = (): Record<string, any> => {
    // Remove empty strings and convert numeric strings
    const cleaned: Record<string, any> = {};
    for (const [key, value] of Object.entries(attributes)) {
      if (value === "" || value === null || value === undefined) continue;
      cleaned[key] = value;
    }
    return cleaned;
  };

  const handleAttributeChange = (key: string, value: any) => {
    setAttributes((prev) => ({ ...prev, [key]: value }));
    setValidationErrors((prev) => prev.filter((e) => e.field !== key));
  };

  const handleAiExtract = async () => {
    if (!selectedType || !rawData.trim()) return;

    setIsExtracting(true);
    setError(null);

    try {
      // Try the new /api/ingest/extract endpoint first
      const res = await fetch(`${API_BASE}/api/ingest/extract`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          type: selectedType.label,
          raw_data: rawData,
        }),
      });

      if (res.ok) {
        const result = await res.json();
        const extracted = result.attributes || result.extracted_attributes || {};
        // Merge extracted into current attributes (don't overwrite user edits)
        setAttributes((prev) => {
          const merged = { ...prev };
          for (const [key, value] of Object.entries(extracted)) {
            if (value && (!merged[key] || merged[key] === "")) {
              merged[key] = value;
            }
          }
          return merged;
        });
        setShowAiFill(false);
      } else {
        // Fallback: try the old /api/ingest/analyze endpoint
        const fallbackRes = await fetch(`${API_BASE}/api/ingest/analyze`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ raw_data: rawData }),
        });

        if (fallbackRes.ok) {
          const result = await fallbackRes.json();
          const extracted = result.extracted_attributes || {};
          setAttributes((prev) => {
            const merged = { ...prev };
            for (const [key, value] of Object.entries(extracted)) {
              if (value && (!merged[key] || merged[key] === "")) {
                merged[key] = value;
              }
            }
            return merged;
          });
          setShowAiFill(false);
        } else {
          throw new Error("AI extraction not available");
        }
      }
    } catch (err: any) {
      setError(err.message || "AI extraction failed. Fill fields manually.");
    } finally {
      setIsExtracting(false);
    }
  };

  const handleClose = () => {
    setStep("select");
    setSelectedType(null);
    setAttributes({});
    setValidationErrors([]);
    setNormalizations([]);
    setError(null);
    setCommitResult(null);
    setShowAiFill(false);
    setRawData("");
    onClose();
  };

  // Check which required fields are missing
  const getMissingRequired = (): string[] => {
    if (!selectedType) return [];
    return selectedType.properties
      .filter((p) => p.required && !attributes[p.name])
      .map((p) => p.name);
  };

  const isCommitDisabled = (): boolean => {
    return getMissingRequired().length > 0 || validationErrors.length > 0;
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 backdrop-blur-sm">
      <div className="bg-[#111] border border-[#2d2d2d] rounded-lg w-full max-w-2xl max-h-[90vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-[#2d2d2d]">
          <div className="flex items-center gap-3">
            <Database className="w-5 h-5 text-[#6EBE46]" />
            <h2
              className="text-lg font-bold text-white tracking-wide"
              style={{ fontFamily: "'Rajdhani', sans-serif" }}
            >
              Ingest Artifact
            </h2>
            {selectedType && step !== "select" && (
              <span className="px-2 py-0.5 bg-[#4B5A2D]/50 rounded text-xs text-[#A0C060]">
                {selectedType.label}
              </span>
            )}
          </div>
          <button onClick={handleClose} className="text-gray-500 hover:text-white">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Progress Steps */}
        <div className="flex items-center gap-2 px-4 py-3 bg-[#0c0c0c] border-b border-[#2d2d2d]">
          <StepIndicator number={1} label="Type" active={step === "select"} completed={step !== "select"} />
          <ChevronRight className="w-4 h-4 text-[#333]" />
          <StepIndicator number={2} label="Fill" active={step === "fill"} completed={step === "review" || step === "success"} />
          <ChevronRight className="w-4 h-4 text-[#333]" />
          <StepIndicator number={3} label="Review" active={step === "review"} completed={step === "success"} />
          <ChevronRight className="w-4 h-4 text-[#333]" />
          <StepIndicator number={4} label="Commit" active={step === "success"} completed={false} />
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4">
          {error && (
            <div className="mb-4 p-3 bg-red-900/20 border border-red-700/50 rounded-lg flex items-start gap-2">
              <AlertTriangle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
              <span className="text-red-300 text-sm">{error}</span>
            </div>
          )}

          {/* Step 1: Select Type */}
          {step === "select" && (
            <div className="space-y-3">
              <p className="text-sm text-gray-400 mb-4">
                Choose the artifact type to ingest. The form will adapt to the ontology schema.
              </p>
              <div className="grid grid-cols-2 gap-2">
                {availableTypes.map((type) => (
                  <button
                    key={type.label}
                    onClick={() => handleSelectType(type)}
                    className="p-3 text-left bg-[#1a1a1a] border border-[#2d2d2d] rounded-lg hover:border-[#6EBE46]/50 hover:bg-[#1a1a1a]/80 transition-all group"
                  >
                    <div className="flex items-center gap-2">
                      <Layers className="w-4 h-4 text-[#6EBE46] opacity-60 group-hover:opacity-100" />
                      <span className="font-medium text-white text-sm">{type.label}</span>
                    </div>
                    <p className="text-xs text-gray-500 mt-1 line-clamp-2">{type.definition}</p>
                    <div className="text-[10px] text-gray-600 mt-2">
                      {type.properties.filter((p) => p.required).length} required • {type.properties.length} fields
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Step 2: Fill Form — LibraryModule uses dedicated wizard */}
          {step === "fill" && selectedType && selectedType.label === "Library Module" && (
            <LibraryModuleWizard
              onCommit={async (payload, ttl) => {
                // 1. Write triples to GraphDB
                const graphRes = await fetch(
                  `${API_BASE}/api/ingest/ttl`,
                  { method: "POST", headers: { "Content-Type": "text/turtle" }, body: ttl }
                );
                if (!graphRes.ok) throw new Error(`GraphDB error: ${graphRes.status}`);

                // 2. Save payload file via ProtoGraph backend
                const key = payload._key as string;
                const payloadRes = await fetch(
                  `${API_BASE}/api/ingest/payloads/${key}.json`,
                  { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }
                );
                if (!payloadRes.ok) throw new Error(`Payload save error: ${payloadRes.status}`);

                // 3. Advance modal to success
                setCommitResult({
                  success: true,
                  artifact_type: "Library Module",
                  collection: "LibraryModule",
                  document_id: `LibraryModule/${key}`,
                  document_key: key,
                  payload_url: `/api/ingest/payloads/${key}.json`,
                  payload_saved: true,
                  edges_created: [],
                  edge_count: 0,
                });
                setStep("success");
                onSuccess?.({ document_key: key, artifact_type: "Library Module" });
              }}
              onCancel={() => setStep("select")}
            />
          )}

          {/* Step 2: Fill Form — generic form for all other types */}
          {step === "fill" && selectedType && selectedType.label !== "Library Module" && (
            <div className="space-y-4">
              {/* Type info */}
              <div className="p-3 bg-[#1a1a1a] rounded-lg border border-[#2d2d2d] flex items-start justify-between">
                <p className="text-xs text-gray-400">{selectedType.definition}</p>
                <button
                  onClick={() => setShowAiFill(!showAiFill)}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-all flex-shrink-0 ml-3 ${
                    showAiFill
                      ? "bg-purple-600/20 text-purple-300 border border-purple-500/50"
                      : "bg-[#2d2d2d] text-gray-400 hover:text-purple-300 hover:bg-purple-600/10 border border-[#2d2d2d] hover:border-purple-500/30"
                  }`}
                >
                  <Sparkles className="w-3.5 h-3.5" />
                  AI Auto-fill
                </button>
              </div>

              {/* AI Autofill Panel */}
              {showAiFill && (
                <div className="p-3 bg-purple-900/10 border border-purple-500/30 rounded-lg space-y-3">
                  <div className="flex items-center gap-2">
                    <Sparkles className="w-4 h-4 text-purple-400" />
                    <h4 className="text-sm font-medium text-purple-200">
                      Paste raw data for AI extraction
                    </h4>
                  </div>
                  <p className="text-[10px] text-purple-300/60">
                    Paste JSON, text, logs, or any structured data. The AI will extract attributes
                    into the {selectedType.label} schema fields. You can review and edit after.
                  </p>
                  <textarea
                    value={rawData}
                    onChange={(e) => setRawData(e.target.value)}
                    placeholder={'{"name": "...", "description": "...", ...}\nor paste any text / logs / notes'}
                    className="w-full h-32 px-3 py-2 bg-[#111] border border-purple-500/20 rounded text-sm text-white placeholder-gray-600 font-mono focus:outline-none focus:ring-1 focus:ring-purple-500/50 resize-none"
                  />
                  <div className="flex items-center justify-between">
                    <button
                      onClick={() => {
                        setShowAiFill(false);
                        setRawData("");
                      }}
                      className="text-xs text-gray-500 hover:text-gray-300"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={handleAiExtract}
                      disabled={isExtracting || !rawData.trim()}
                      className="flex items-center gap-2 px-3 py-1.5 bg-purple-600 hover:bg-purple-500 text-white rounded text-xs font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {isExtracting ? (
                        <>
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          Extracting...
                        </>
                      ) : (
                        <>
                          <Sparkles className="w-3.5 h-3.5" />
                          Extract Fields
                        </>
                      )}
                    </button>
                  </div>
                </div>
              )}

              {/* Validation errors */}
              {validationErrors.length > 0 && (
                <div className="p-3 bg-red-900/20 border border-red-700/50 rounded-lg">
                  <h4 className="text-sm font-medium text-red-300 mb-1">Validation Errors</h4>
                  <ul className="text-xs text-red-200 space-y-1">
                    {validationErrors.map((e, i) => (
                      <li key={i}>• <span className="text-red-400">{e.field}</span>: {e.message}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Required fields first, then optional */}
              <div>
                <h4 className="text-xs font-bold uppercase text-gray-500 mb-3 tracking-wider">
                  Required Fields
                </h4>
                <div className="space-y-3">
                  {selectedType.properties
                    .filter((p) => p.required)
                    .map((prop) => (
                      <AttributeField
                        key={prop.name}
                        property={prop}
                        value={attributes[prop.name]}
                        onChange={(v) => handleAttributeChange(prop.name, v)}
                        hasError={validationErrors.some((e) => e.field === prop.name)}
                        taxonomyTerms={prop.taxonomy ? taxonomyTerms[prop.taxonomy] : undefined}
                      />
                    ))}
                </div>
              </div>

              <div>
                <h4 className="text-xs font-bold uppercase text-gray-500 mb-3 tracking-wider">
                  Optional Fields
                </h4>
                <div className="space-y-3">
                  {selectedType.properties
                    .filter((p) => !p.required)
                    .map((prop) => (
                      <AttributeField
                        key={prop.name}
                        property={prop}
                        value={attributes[prop.name]}
                        onChange={(v) => handleAttributeChange(prop.name, v)}
                        hasError={validationErrors.some((e) => e.field === prop.name)}
                        taxonomyTerms={prop.taxonomy ? taxonomyTerms[prop.taxonomy] : undefined}
                      />
                    ))}
                </div>
              </div>
            </div>
          )} {/* end generic fill form */}

          {/* Step 3: Review */}
          {step === "review" && selectedType && (
            <div className="space-y-4">
              <div className="p-3 bg-[#4B5A2D]/20 rounded-lg border border-[#6EBE46]/30">
                <div className="flex items-center gap-2">
                  <CheckCircle className="w-5 h-5 text-[#6EBE46]" />
                  <span className="text-white font-medium">Validation Passed</span>
                </div>
                <p className="text-xs text-gray-400 mt-1">
                  All required fields are present and valid. SHACL validation will run on commit.
                </p>
              </div>

              {/* Normalizations */}
              {normalizations.length > 0 && (
                <div className="p-3 bg-blue-900/20 border border-blue-700/50 rounded-lg">
                  <h4 className="text-sm font-medium text-blue-300 mb-2">Normalizations Applied</h4>
                  <ul className="text-xs text-blue-200 space-y-1">
                    {normalizations.map((n, i) => (
                      <li key={i}>
                        • <span className="text-blue-400">{n.field}</span>: '{n.original}' → '{n.normalized}'
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Summary table */}
              <div className="space-y-1">
                <h4 className="text-xs font-bold uppercase text-gray-500 mb-2 tracking-wider">
                  Artifact Summary
                </h4>
                {Object.entries(cleanAttributes()).map(([key, value]) => (
                  <div key={key} className="flex items-start py-1.5 border-b border-[#2d2d2d]/50">
                    <span className="text-xs text-gray-500 w-36 flex-shrink-0">
                      {key}
                      {selectedType.properties.find((p) => p.name === key)?.required && (
                        <span className="text-[#6EBE46] ml-1">*</span>
                      )}
                    </span>
                    <span className="text-sm text-white">
                      {typeof value === "object" ? JSON.stringify(value) : String(value)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Step 4: Success */}
          {step === "success" && commitResult && (
            <div className="space-y-4">
              <div className="text-center py-6">
                <CheckCircle className="w-16 h-16 text-[#6EBE46] mx-auto mb-4" />
                <h3 className="text-xl font-bold text-white mb-1">Artifact Committed!</h3>
                <p className="text-gray-400 text-sm">
                  {commitResult.artifact_type} saved as{" "}
                  <span className="text-[#A0C060] font-mono">{commitResult.document_id}</span>
                </p>
              </div>

              {/* Edges created */}
              {commitResult.edge_count > 0 && (
                <div className="p-3 bg-[#1a1a1a] rounded-lg border border-[#2d2d2d]">
                  <div className="flex items-center gap-2 mb-2">
                    <GitBranch className="w-4 h-4 text-[#6EBE46]" />
                    <h4 className="text-sm font-medium text-white">
                      {commitResult.edge_count} Relationships Auto-Created
                    </h4>
                  </div>
                  <div className="space-y-1.5">
                    {commitResult.edges_created.map((edge, i) => (
                      <div key={i} className="flex items-center gap-2 text-xs">
                        <span className="text-gray-400 font-mono">{edge._from}</span>
                        <span className="text-[#6EBE46]">→</span>
                        <span className="px-1.5 py-0.5 bg-[#4B5A2D]/30 text-[#A0C060] rounded text-[10px]">
                          {edge.relationship_type}
                        </span>
                        <span className="text-[#6EBE46]">→</span>
                        <span className="text-gray-400 font-mono">{edge._to}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Payload link */}
              {commitResult.payload_saved && commitResult.payload_url && (
                <div className="text-xs text-gray-500">
                  Payload: <span className="font-mono text-gray-400">{commitResult.payload_url}</span>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between p-4 border-t border-[#2d2d2d] bg-[#0c0c0c]">
          {step === "select" && (
            <button onClick={handleClose} className="px-4 py-2 text-gray-500 hover:text-white text-sm">
              Cancel
            </button>
          )}

          {step === "fill" && selectedType?.label !== "Library Module" && (
            <>
              <button
                onClick={() => setStep("select")}
                className="px-4 py-2 text-gray-500 hover:text-white text-sm"
              >
                ← Back
              </button>
              <button
                onClick={handleValidate}
                disabled={isValidating || getMissingRequired().length > 0}
                title={getMissingRequired().length > 0 ? `Missing: ${getMissingRequired().join(", ")}` : ""}
                className="flex items-center gap-2 px-4 py-2 bg-[#6EBE46] hover:bg-[#5EA836] text-black font-medium rounded-lg disabled:opacity-50 disabled:cursor-not-allowed text-sm"
              >
                {isValidating ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Validating...
                  </>
                ) : (
                  <>
                    <RefreshCw className="w-4 h-4" />
                    Validate & Review
                  </>
                )}
              </button>
            </>
          )}

          {step === "review" && (
            <>
              <button
                onClick={() => setStep("fill")}
                className="px-4 py-2 text-gray-500 hover:text-white text-sm"
              >
                ← Edit
              </button>
              <button
                onClick={handleCommit}
                disabled={isCommitting}
                className="flex items-center gap-2 px-4 py-2 bg-[#6EBE46] hover:bg-[#5EA836] text-black font-medium rounded-lg disabled:opacity-50 disabled:cursor-not-allowed text-sm"
              >
                {isCommitting ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Committing...
                  </>
                ) : (
                  <>
                    <CheckCircle className="w-4 h-4" />
                    Commit to Graph
                  </>
                )}
              </button>
            </>
          )}

          {step === "success" && (
            <button
              onClick={handleClose}
              className="ml-auto px-4 py-2 bg-[#1a1a1a] hover:bg-[#2d2d2d] text-white rounded-lg text-sm"
            >
              Close
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// =====================================================
// STEP INDICATOR
// =====================================================

function StepIndicator({
  number,
  label,
  active,
  completed,
}: {
  number: number;
  label: string;
  active: boolean;
  completed: boolean;
}) {
  return (
    <div className="flex items-center gap-1.5">
      <div
        className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold ${
          completed
            ? "bg-[#6EBE46] text-black"
            : active
            ? "bg-[#6EBE46]/20 text-[#6EBE46] border border-[#6EBE46]"
            : "bg-[#1a1a1a] text-gray-600 border border-[#333]"
        }`}
      >
        {completed ? "✓" : number}
      </div>
      <span
        className={`text-xs ${active ? "text-white" : completed ? "text-[#6EBE46]" : "text-gray-600"}`}
        style={{ fontFamily: "'JetBrains Mono', monospace" }}
      >
        {label}
      </span>
    </div>
  );
}

// =====================================================
// ATTRIBUTE FIELD (with taxonomy dropdown support)
// =====================================================

function AttributeField({
  property,
  value,
  onChange,
  hasError,
  taxonomyTerms,
}: {
  property: SchemaProperty;
  value: any;
  onChange: (v: any) => void;
  hasError: boolean;
  taxonomyTerms?: TaxonomyTerm[];
}) {
  const inputClass = `w-full px-3 py-2 bg-[#1a1a1a] border rounded text-sm text-white placeholder-gray-600 focus:outline-none focus:ring-1 ${
    hasError
      ? "border-red-500 focus:ring-red-500"
      : "border-[#2d2d2d] focus:ring-[#6EBE46]/50 focus:border-[#6EBE46]/50"
  }`;

  const isTextarea =
    property.name === "description" ||
    property.name === "requirements" ||
    property.name === "notes" ||
    property.type === "text";

  return (
    <div>
      <label className="block text-xs font-medium text-gray-400 mb-1">
        {property.label || property.name}
        {property.required && <span className="ml-1 text-[#6EBE46]">*</span>}
        {property.taxonomy && (
          <span className="ml-2 text-gray-600 text-[10px]">
            [{property.taxonomy}]
          </span>
        )}
      </label>

      {/* Taxonomy dropdown */}
      {taxonomyTerms && taxonomyTerms.length > 0 ? (
        <select
          value={String(value || "")}
          onChange={(e) => onChange(e.target.value)}
          className={inputClass}
        >
          <option value="">Select {property.label || property.name}...</option>
          {taxonomyTerms.map((term) => (
            <option key={term.uri} value={term.label}>
              {term.label}
            </option>
          ))}
        </select>
      ) : isTextarea ? (
        <textarea
          value={String(value || "")}
          onChange={(e) => onChange(e.target.value)}
          rows={3}
          placeholder={property.description || ""}
          className={`${inputClass} resize-none`}
        />
      ) : property.type === "boolean" ? (
        <div className="flex items-center gap-2 py-2">
          <input
            type="checkbox"
            checked={Boolean(value)}
            onChange={(e) => onChange(e.target.checked)}
            className="w-4 h-4 accent-[#6EBE46]"
          />
          <span className="text-xs text-gray-400">{property.description || ""}</span>
        </div>
      ) : property.type === "integer" || property.type === "number" ? (
        <input
          type="number"
          value={value || ""}
          onChange={(e) => onChange(e.target.value ? Number(e.target.value) : "")}
          placeholder={property.description || ""}
          className={inputClass}
        />
      ) : (
        <input
          type="text"
          value={String(value || "")}
          onChange={(e) => onChange(e.target.value)}
          placeholder={property.description || ""}
          className={inputClass}
        />
      )}
    </div>
  );
}