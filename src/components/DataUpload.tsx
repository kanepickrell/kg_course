// components/DataUpload.tsx
// ATLAS Data Upload — post-onboarding artifact ingestion with LLM extraction
// Matches Vellox Reverser aesthetic from DataOnboarding

import { useState, useEffect, useRef, useCallback } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  AlertCircle, ArrowLeft, ArrowRight, Check, CheckCircle2,
  ChevronDown, ChevronRight, Database, Edit3, Eye,
  FileText, Loader2, Plus, Search,
  Sparkles, Trash2, Upload, X, XCircle, Zap, FileSpreadsheet,
  FileJson, File as FileIcon, AlertTriangle, ArrowUpFromLine,
} from "lucide-react";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

// ─────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────

interface ParsedFile {
  filename: string;
  extension: string;
  row_count: number;
  columns: string[];
  is_structured: boolean;
  sample_rows: Record<string, any>[];
}

interface ExtractedRecord {
  _id: string;
  _source_file: string;
  _source_row: number;
  _confidence: number;
  _status: "pending" | "approved" | "rejected" | "edited";
  [field: string]: any;
}

interface SchemaField {
  data_type: string;
  description: string;
  required: boolean;
  example_values?: string[];
  extraction_hint?: string;
}

interface Relationship {
  from_field: string;
  to_field: string;
  relationship_type: string;
  description?: string;
}

type UploadStep = "upload" | "preview" | "extract" | "review" | "commit";

// ─────────────────────────────────────────────────────────────
// Base Components
// ─────────────────────────────────────────────────────────────

const Button: React.FC<
  React.ButtonHTMLAttributes<HTMLButtonElement> & {
    variant?: "primary" | "secondary" | "ghost" | "danger" | "success";
    size?: "sm" | "md" | "lg";
  }
> = ({ variant = "primary", size = "md", children, className = "", ...props }) => {
  const base = "rounded font-medium transition-all disabled:opacity-40 disabled:cursor-not-allowed inline-flex items-center justify-center gap-1.5";
  const sizes = { sm: "px-3 py-1.5 text-xs", md: "px-4 py-2.5 text-sm", lg: "px-6 py-3 text-sm" };
  const variants = {
    primary: "bg-[#6EBE46] text-[#0a0a0a] hover:bg-[#7ECF56]",
    secondary: "bg-transparent border border-[#333] text-[#888] hover:border-[#6EBE46] hover:text-[#6EBE46]",
    ghost: "bg-transparent text-[#666] hover:text-white hover:bg-[#1a1a1a]",
    danger: "bg-red-500/10 border border-red-500/30 text-red-400 hover:bg-red-500/20",
    success: "bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/20",
  };
  return (
    <button {...props} className={`${base} ${sizes[size]} ${variants[variant]} ${className}`}>
      {children}
    </button>
  );
};

const Card: React.FC<{ children: React.ReactNode; className?: string }> = ({ children, className = "" }) => (
  <div className={`bg-[#111] border border-[#222] rounded-lg ${className}`}>{children}</div>
);

const Badge: React.FC<{ children: React.ReactNode; color?: string }> = ({ children, color = "cyan" }) => {
  const colors: Record<string, string> = {
    cyan: "bg-[#6EBE46]/10 text-[#6EBE46] border-[#6EBE46]/20",
    green: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
    amber: "bg-amber-500/10 text-amber-400 border-amber-500/20",
    red: "bg-red-500/10 text-red-400 border-red-500/20",
    gray: "bg-[#1a1a1a] text-[#888] border-[#333]",
  };
  return (
    <span className={`text-[9px] px-1.5 py-0.5 rounded border font-medium ${colors[color] || colors.gray}`}>
      {children}
    </span>
  );
};

// ─────────────────────────────────────────────────────────────
// Step Indicator
// ─────────────────────────────────────────────────────────────

const UPLOAD_STEPS: { key: UploadStep; label: string; icon: React.FC<any> }[] = [
  { key: "upload", label: "Upload", icon: Upload },
  { key: "preview", label: "Preview", icon: Eye },
  { key: "extract", label: "Extract", icon: Sparkles },
  { key: "review", label: "Review", icon: CheckCircle2 },
  { key: "commit", label: "Commit", icon: Database },
];

const UploadStepIndicator: React.FC<{ currentStep: UploadStep }> = ({ currentStep }) => {
  const currentIdx = UPLOAD_STEPS.findIndex((s) => s.key === currentStep);
  return (
    <div className="flex items-center gap-1">
      {UPLOAD_STEPS.map((step, idx) => {
        const Icon = step.icon;
        const isComplete = idx < currentIdx;
        const isCurrent = idx === currentIdx;
        return (
          <div key={step.key} className="flex items-center">
            <div className="flex items-center gap-2">
              <div className={`w-7 h-7 rounded-full flex items-center justify-center border transition-all ${
                isComplete ? "bg-[#6EBE46] border-[#6EBE46]"
                  : isCurrent ? "border-[#6EBE46] bg-[#6EBE46]/10"
                  : "border-[#333] bg-transparent"
              }`}>
                {isComplete ? <Check className="w-3.5 h-3.5 text-[#0a0a0a]" /> : <Icon className={`w-3.5 h-3.5 ${isCurrent ? "text-[#6EBE46]" : "text-[#555]"}`} />}
              </div>
              <span className={`text-[11px] font-medium tracking-wide ${isCurrent ? "text-[#6EBE46]" : isComplete ? "text-[#888]" : "text-[#444]"}`} style={{ fontFamily: "'Rajdhani', sans-serif" }}>
                {step.label}
              </span>
            </div>
            {idx < UPLOAD_STEPS.length - 1 && <div className={`w-8 h-px mx-2 ${isComplete ? "bg-[#6EBE46]" : "bg-[#222]"}`} />}
          </div>
        );
      })}
    </div>
  );
};

// ─────────────────────────────────────────────────────────────
// File type icon helper
// ─────────────────────────────────────────────────────────────

const FileTypeIcon: React.FC<{ ext: string; className?: string }> = ({ ext, className = "w-5 h-5" }) => {
  const iconMap: Record<string, React.FC<any>> = {
    ".csv": FileSpreadsheet, ".tsv": FileSpreadsheet, ".xlsx": FileSpreadsheet, ".xls": FileSpreadsheet,
    ".json": FileJson, ".txt": FileText, ".md": FileText, ".pdf": FileText,
  };
  const Icon = iconMap[ext] || FileIcon;
  return <Icon className={className} />;
};

// ─────────────────────────────────────────────────────────────
// Main Component
// ─────────────────────────────────────────────────────────────

const DataUpload: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const inputRef = useRef<HTMLInputElement>(null);

  // Schema from onboarding
  const [schemaFields, setSchemaFields] = useState<Record<string, SchemaField>>({});
  const [relationships, setRelationships] = useState<Relationship[]>([]);
  const [collectionName, setCollectionName] = useState("artifacts");
  const [domainName, setDomainName] = useState<string>("");

  const [step, setStep] = useState<UploadStep>("upload");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Upload state
  const [uploadSessionId, setUploadSessionId] = useState<string | null>(null);
  const [parsedFiles, setParsedFiles] = useState<ParsedFile[]>([]);
  const [parseWarnings, setParseWarnings] = useState<string[]>([]);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [isDragging, setIsDragging] = useState(false);

  // Extraction state
  const [extractedRecords, setExtractedRecords] = useState<ExtractedRecord[]>([]);
  const [extractionMethod, setExtractionMethod] = useState("");
  const [extractionWarnings, setExtractionWarnings] = useState<string[]>([]);

  // Review state
  const [filter, setFilter] = useState<"all" | "pending" | "approved" | "rejected">("all");
  const [expandedRecord, setExpandedRecord] = useState<string | null>(null);
  const [editingField, setEditingField] = useState<{ recordId: string; field: string } | null>(null);
  const [editValue, setEditValue] = useState("");

  // Commit state
  const [commitResult, setCommitResult] = useState<{
    nodes_created: number; edges_created: number; collection: string; errors: string[];
  } | null>(null);

  // Load schema from sessionStorage, fallback to ArangoDB latest
  useEffect(() => {
    const stored = sessionStorage.getItem("atlas_schema");
    if (stored) {
      try {
        const parsed = JSON.parse(stored);
        if (parsed.fields) setSchemaFields(parsed.fields);
        if (parsed.relationships) setRelationships(parsed.relationships);
        if (parsed.collection) setCollectionName(parsed.collection);
        if (parsed.domain_name) {
          setDomainName(parsed.domain_name);
          // Default collection name to sanitized domain name
          if (!parsed.collection) {
            setCollectionName(parsed.domain_name.toLowerCase().replace(/[^a-z0-9]/g, '_').replace(/_+/g, '_').replace(/^_|_$/g, '') || "artifacts");
          }
        }
        return; // Got it from sessionStorage
      } catch {}
    }

    // Fallback: load latest schema from ArangoDB
    loadLatestSchema();
  }, []);

  const loadLatestSchema = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/onboarding/schemas-latest`);
      if (res.ok) {
        const data = await res.json();
        if (data.fields) setSchemaFields(data.fields);
        if (data.relationships) setRelationships(data.relationships);
        if (data.domain_name) setDomainName(data.domain_name);
        // Also save to sessionStorage for this session
        sessionStorage.setItem("atlas_schema", JSON.stringify({
          fields: data.fields,
          default_fields: data.default_fields || {},
          relationships: data.relationships || [],
          session_id: data.session_id,
          domain_name: data.domain_name,
        }));
      }
    } catch {
      // No schema available — user will see warning
    }
  };

  // ── Handlers ──────────────────────────────────────────────

  const handleFilesUploaded = async () => {
    if (selectedFiles.length === 0) return;
    setIsLoading(true);
    setError(null);
    try {
      const formData = new FormData();
      for (const file of selectedFiles) formData.append("files", file);

      const res = await fetch(`${API_BASE}/api/upload/files`, { method: "POST", body: formData });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Upload failed");

      setUploadSessionId(data.upload_session_id);
      setParsedFiles(data.files);
      setParseWarnings(data.warnings || []);
      setSelectedFiles([]);
      setStep("preview");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setIsLoading(false);
    }
  };

  const handleExtract = async () => {
    if (!uploadSessionId) return;
    setStep("extract");
    setIsLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/upload/extract`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          upload_session_id: uploadSessionId,
          schema_fields: schemaFields,
          relationships,
          collection_name: collectionName,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Extraction failed");

      setExtractedRecords(data.records || []);
      setExtractionMethod(data.extraction_method || "unknown");
      setExtractionWarnings(data.warnings || []);
      setStep("review");
    } catch (e: any) {
      setError(e.message);
      setStep("preview");
    } finally {
      setIsLoading(false);
    }
  };

  const handleUpdateRecord = (id: string, updates: Record<string, any>) => {
    setExtractedRecords((prev) => prev.map((r) => (r._id === id ? { ...r, ...updates } : r)));
  };

  const handleApproveAll = () => {
    setExtractedRecords((prev) => prev.map((r) => r._status === "pending" ? { ...r, _status: "approved" as const } : r));
  };

  const handleCommit = async () => {
    if (!uploadSessionId) return;
    setIsLoading(true);
    setError(null);
    try {
      const approved = extractedRecords.filter((r) => r._status === "approved" || r._status === "edited");
      const res = await fetch(`${API_BASE}/api/upload/commit`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          upload_session_id: uploadSessionId,
          records: approved,
          collection_name: collectionName,
          domain_name: domainName || undefined,
          create_edges: true,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Commit failed");
      setCommitResult(data);
      setStep("commit");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setIsLoading(false);
    }
  };

  const handleReset = () => {
    setParsedFiles([]);
    setParseWarnings([]);
    setExtractedRecords([]);
    setExtractionWarnings([]);
    setCommitResult(null);
    setUploadSessionId(null);
    setSelectedFiles([]);
    setStep("upload");
  };

  const startEdit = (recordId: string, field: string, currentValue: any) => {
    setEditingField({ recordId, field });
    setEditValue(String(currentValue ?? ""));
  };

  const saveEdit = () => {
    if (editingField) {
      handleUpdateRecord(editingField.recordId, { [editingField.field]: editValue, _status: "edited" });
      setEditingField(null);
    }
  };

  // ── Computed values ───────────────────────────────────────

  const fieldNames = Object.keys(schemaFields);
  const totalRows = parsedFiles.reduce((sum, f) => sum + f.row_count, 0);
  const filteredRecords = filter === "all" ? extractedRecords : extractedRecords.filter((r) => r._status === filter);
  const counts = {
    total: extractedRecords.length,
    pending: extractedRecords.filter((r) => r._status === "pending").length,
    approved: extractedRecords.filter((r) => r._status === "approved" || r._status === "edited").length,
    rejected: extractedRecords.filter((r) => r._status === "rejected").length,
  };

  // ── Render ────────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-[#0a0a0a] text-white flex flex-col">
      <link href="https://fonts.googleapis.com/css2?family=Rajdhani:wght@300;400;500;600;700&family=JetBrains+Mono:wght@300;400;500&display=swap" rel="stylesheet" />

      {/* ProtoGraph Tool Header */}
      <header className="border-b border-[#2d2d2d] bg-[#0c0c0c]/90 backdrop-blur-sm flex-shrink-0 sticky top-0 z-50">
        <div className="max-w-5xl mx-auto px-5 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button
              onClick={() => navigate("/home")}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded border border-[#2d2d2d] text-[#888] hover:border-[#6EBE46] hover:text-[#6EBE46] transition-colors"
              style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, letterSpacing: 1 }}
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              DASHBOARD
            </button>

            <div className="w-px h-5 bg-[#2d2d2d]" />

            <Upload className="w-4 h-4 text-[#6EBE46]" />
            <span
              className="text-sm font-bold text-white tracking-wider"
              style={{ fontFamily: "'Rajdhani', sans-serif" }}
            >
              Data Upload
            </span>
          </div>

          <div className="flex items-center gap-4">
            {domainName && (
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-[#555]" style={{ fontFamily: "'JetBrains Mono', monospace" }}>Domain:</span>
                <span className="text-xs font-mono text-[#6EBE46]">{domainName}</span>
              </div>
            )}
            <div className="flex items-center gap-2">
              <Database className="w-3.5 h-3.5 text-[#555]" />
              <input
                value={collectionName}
                onChange={(e) => setCollectionName(e.target.value.replace(/[^a-zA-Z0-9_]/g, "_"))}
                className="px-2 py-1 bg-[#0c0c0c] border border-[#222] rounded text-xs text-white font-mono w-32 focus:outline-none focus:border-[#6EBE46]"
                title="Target ArangoDB collection"
              />
            </div>
            <UploadStepIndicator currentStep={step} />
            <span
              className="text-[10px] text-[#555] tracking-widest"
              style={{ fontFamily: "'JetBrains Mono', monospace" }}
            >
              PROTOGRAPH • UPLOAD
            </span>
          </div>
        </div>
      </header>

      {/* Schema bar */}
      {fieldNames.length > 0 && (
        <div className="border-b border-[#111] bg-[#0a0a0a]">
          <div className="max-w-5xl mx-auto px-6 py-2 flex items-center gap-4">
            <span className="text-[10px] text-[#555]">Schema:</span>
            <div className="flex flex-wrap gap-1">
              {fieldNames.slice(0, 10).map((f) => (
                <span key={f} className="text-[9px] px-1.5 py-0.5 bg-[#111] text-[#888] rounded font-mono border border-[#1a1a1a]">{f}</span>
              ))}
              {fieldNames.length > 10 && <span className="text-[9px] text-[#555]">+{fieldNames.length - 10} more</span>}
            </div>
            <span className="text-[10px] text-[#555] ml-auto">{relationships.length} relationships</span>
          </div>
        </div>
      )}

      {/* No schema warning */}
      {fieldNames.length === 0 && step === "upload" && (
        <div className="border-b border-amber-500/20 bg-amber-500/5">
          <div className="max-w-5xl mx-auto px-6 py-3 flex items-center gap-3">
            <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0" />
            <span className="text-xs text-amber-400">No schema loaded. Complete onboarding first, or data will be uploaded with raw column names.</span>
            <Button variant="ghost" size="sm" onClick={() => navigate("/onboarding")}>
              Go to Onboarding <ArrowRight className="w-3 h-3" />
            </Button>
          </div>
        </div>
      )}

      {/* Error banner */}
      {error && (
        <div className="bg-red-500/10 border-b border-red-500/30 px-6 py-3">
          <div className="max-w-5xl mx-auto flex items-center gap-3">
            <AlertCircle className="w-4 h-4 text-red-400 flex-shrink-0" />
            <span className="text-xs text-red-400 flex-1">{error}</span>
            <button onClick={() => setError(null)} className="text-red-400 hover:text-red-300"><X className="w-3.5 h-3.5" /></button>
          </div>
        </div>
      )}

      {/* Main content */}
      <main className="flex-1 max-w-5xl mx-auto w-full px-6 py-8 overflow-hidden flex flex-col">

        {/* ── STEP 1: Upload ───────────────────────────────── */}
        {step === "upload" && (
          <div className="flex flex-col h-full">
            <div
              onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={(e) => { e.preventDefault(); setIsDragging(false); setSelectedFiles((prev) => [...prev, ...Array.from(e.dataTransfer.files)]); }}
              onClick={() => inputRef.current?.click()}
              className={`border-2 border-dashed rounded-xl p-12 text-center cursor-pointer transition-all mb-6 ${isDragging ? "border-[#6EBE46] bg-[#6EBE46]/5" : "border-[#222] hover:border-[#444] bg-[#0a0a0a]"}`}
            >
              <input ref={inputRef} type="file" multiple accept=".csv,.tsv,.json,.xlsx,.xls,.txt,.md,.pdf" onChange={(e) => { if (e.target.files) setSelectedFiles((prev) => [...prev, ...Array.from(e.target.files!)]); }} className="hidden" />
              <div className={`w-16 h-16 rounded-full mx-auto mb-4 flex items-center justify-center transition-all ${isDragging ? "bg-[#6EBE46]/20" : "bg-[#111]"}`}>
                <ArrowUpFromLine className={`w-7 h-7 ${isDragging ? "text-[#6EBE46]" : "text-[#555]"}`} />
              </div>
              <p className="text-sm text-[#ccc] mb-1">{isDragging ? "Drop files here" : "Drag & drop files or click to browse"}</p>
              <p className="text-[10px] text-[#555]">Supports CSV, JSON, XLSX, TXT, MD, PDF</p>
            </div>

            {selectedFiles.length > 0 && (
              <div className="mb-6">
                <h4 className="text-[10px] font-semibold text-[#6EBE46] uppercase tracking-wider mb-3" style={{ fontFamily: "'Rajdhani', sans-serif" }}>
                  Selected Files ({selectedFiles.length})
                </h4>
                <div className="space-y-1.5">
                  {selectedFiles.map((file, idx) => {
                    const ext = file.name.substring(file.name.lastIndexOf(".")).toLowerCase();
                    return (
                      <div key={`${file.name}-${idx}`} className="flex items-center gap-3 px-3 py-2 bg-[#111] rounded border border-[#1a1a1a] group">
                        <FileTypeIcon ext={ext} className="w-4 h-4 text-[#6EBE46]" />
                        <span className="text-xs font-mono text-white flex-1 truncate">{file.name}</span>
                        <span className="text-[10px] text-[#555]">{(file.size / 1024).toFixed(1)} KB</span>
                        <Badge color="gray">{ext}</Badge>
                        <button onClick={(e) => { e.stopPropagation(); setSelectedFiles((prev) => prev.filter((_, i) => i !== idx)); }} className="opacity-0 group-hover:opacity-100 text-red-400 hover:text-red-300 transition-all">
                          <X className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            <div className="mt-auto pt-4 border-t border-[#1a1a1a] flex items-center justify-between">
              <span className="text-[10px] text-[#555] font-mono">{selectedFiles.length} file{selectedFiles.length !== 1 ? "s" : ""} selected</span>
              <Button onClick={handleFilesUploaded} disabled={selectedFiles.length === 0 || isLoading}>
                {isLoading ? <><Loader2 className="w-3.5 h-3.5 animate-spin" /> Parsing...</> : <><Upload className="w-3.5 h-3.5" /> Upload & Parse</>}
              </Button>
            </div>
          </div>
        )}

        {/* ── STEP 2: Preview ──────────────────────────────── */}
        {step === "preview" && (
          <div className="flex flex-col h-full">
            {parsedFiles.map((file, fIdx) => (
              <div key={file.filename} className="mb-6">
                <div className="mb-3 p-4 bg-[#6EBE46]/5 border border-[#6EBE46]/20 rounded-lg">
                  <div className="flex items-center gap-3 mb-2">
                    <FileTypeIcon ext={file.extension} className="w-5 h-5 text-[#6EBE46]" />
                    <span className="text-sm font-medium text-white">{file.filename}</span>
                    <Badge color="cyan">{file.row_count} rows</Badge>
                    <Badge color={file.is_structured ? "green" : "amber"}>{file.is_structured ? "structured" : "unstructured"}</Badge>
                  </div>
                  {file.columns.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-2">
                      {file.columns.map((col) => (
                        <span key={col} className="text-[10px] px-2 py-0.5 bg-[#1a1a1a] text-[#aaa] rounded font-mono">{col}</span>
                      ))}
                    </div>
                  )}
                </div>

                {file.is_structured && file.sample_rows.length > 0 && (
                  <div className="overflow-x-auto mb-4">
                    <table className="w-full text-xs border-collapse">
                      <thead>
                        <tr className="border-b border-[#222]">
                          <th className="px-3 py-2 text-left text-[10px] text-[#555] font-medium uppercase tracking-wider">#</th>
                          {file.columns.slice(0, 8).map((col) => (
                            <th key={col} className="px-3 py-2 text-left text-[10px] text-[#555] font-medium uppercase tracking-wider font-mono">{col}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {file.sample_rows.map((row, i) => (
                          <tr key={i} className="border-b border-[#1a1a1a] hover:bg-[#111]">
                            <td className="px-3 py-2 text-[#555] font-mono">{row._source_row || i + 1}</td>
                            {file.columns.slice(0, 8).map((col) => (
                              <td key={col} className="px-3 py-2 text-[#ccc] max-w-[200px] truncate">{String(row[col] ?? "—")}</td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {file.row_count > 5 && <p className="text-[10px] text-[#555] mt-2 text-center italic">Showing 5 of {file.row_count} rows</p>}
                  </div>
                )}

                {!file.is_structured && file.sample_rows[0]?._full_text && (
                  <pre className="text-[11px] text-[#999] bg-[#0a0a0a] p-4 rounded border border-[#1a1a1a] whitespace-pre-wrap font-mono leading-relaxed max-h-[300px] overflow-y-auto mb-4">
                    {String(file.sample_rows[0]._full_text).slice(0, 2000)}{String(file.sample_rows[0]._full_text).length > 2000 && "\n\n... (truncated)"}
                  </pre>
                )}
              </div>
            ))}

            {parseWarnings.length > 0 && (
              <div className="mb-4 space-y-1">
                {parseWarnings.map((w, i) => (
                  <div key={i} className="flex items-start gap-2 px-3 py-2 bg-amber-500/5 rounded border border-amber-500/10">
                    <AlertTriangle className="w-3.5 h-3.5 text-amber-400 mt-0.5 flex-shrink-0" />
                    <span className="text-[11px] text-amber-400">{w}</span>
                  </div>
                ))}
              </div>
            )}

            <div className="mt-auto pt-4 border-t border-[#1a1a1a] flex items-center justify-between">
              <Button variant="ghost" onClick={handleReset}><ArrowLeft className="w-3.5 h-3.5" /> Upload More</Button>
              <Button onClick={handleExtract}><Sparkles className="w-3.5 h-3.5" /> Extract Fields</Button>
            </div>
          </div>
        )}

        {/* ── STEP 3: Extracting (loading) ─────────────────── */}
        {step === "extract" && (
          <div className="flex flex-col items-center justify-center h-full text-center py-16">
            <div className="w-20 h-20 rounded-full bg-[#6EBE46]/10 border-2 border-[#6EBE46]/30 flex items-center justify-center mb-8">
              <Sparkles className="w-8 h-8 text-[#6EBE46] animate-pulse" />
            </div>
            <h2 className="text-lg font-semibold text-white mb-2" style={{ fontFamily: "'Rajdhani', sans-serif", letterSpacing: "0.5px" }}>Extracting Fields</h2>
            <p className="text-sm text-[#888] mb-6 max-w-md">
              ATLAS is mapping {totalRows} rows from {parsedFiles.length} file{parsedFiles.length !== 1 ? "s" : ""} to your schema fields.
            </p>
            <div className="flex items-center gap-3 text-xs text-[#555]">
              <Loader2 className="w-4 h-4 animate-spin text-[#6EBE46]" />
              <span>Mapping columns to schema fields...</span>
            </div>
          </div>
        )}

        {/* ── STEP 4: Review ───────────────────────────────── */}
        {step === "review" && (
          <div className="flex flex-col h-full">
            <div className="mb-4 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <h3 className="text-sm font-semibold text-white" style={{ fontFamily: "'Rajdhani', sans-serif", letterSpacing: "0.5px" }}>Review Records</h3>
                <Badge color="cyan">{extractionMethod}</Badge>
              </div>
              <Button variant="success" size="sm" onClick={handleApproveAll}>
                <Check className="w-3 h-3" /> Approve All ({counts.pending})
              </Button>
            </div>

            {/* Filter tabs */}
            <div className="flex gap-1 mb-4 p-1 bg-[#0c0c0c] rounded border border-[#1a1a1a]">
              {(["all", "pending", "approved", "rejected"] as const).map((f) => {
                const count = f === "all" ? counts.total : counts[f];
                return (
                  <button key={f} onClick={() => setFilter(f)} className={`flex-1 py-2 px-3 rounded text-xs font-medium transition-all ${filter === f ? "bg-[#6EBE46]/10 text-[#6EBE46] border border-[#6EBE46]/30" : "text-[#666] hover:text-white border border-transparent"}`}>
                    <span className="capitalize">{f}</span>
                    <span className={`ml-1.5 text-[9px] px-1.5 py-0.5 rounded-full ${filter === f ? "bg-[#6EBE46]/20" : "bg-[#1a1a1a]"}`}>{count}</span>
                  </button>
                );
              })}
            </div>

            {/* Extraction warnings */}
            {extractionWarnings.length > 0 && (
              <div className="mb-4 space-y-1">
                {extractionWarnings.slice(0, 3).map((w, i) => (
                  <div key={i} className="flex items-start gap-2 px-3 py-1.5 bg-[#0c0c0c] rounded border border-[#1a1a1a]">
                    <AlertTriangle className="w-3 h-3 text-amber-400 mt-0.5 flex-shrink-0" />
                    <span className="text-[10px] text-[#888]">{w}</span>
                  </div>
                ))}
              </div>
            )}

            {/* Records list */}
            <div className="flex-1 overflow-y-auto space-y-2 pr-1">
              {filteredRecords.map((record) => {
                const isExpanded = expandedRecord === record._id;
                const conf = record._confidence || 0;
                const confColor = conf >= 0.8 ? "green" : conf >= 0.5 ? "amber" : "red";
                const statusColors: Record<string, string> = { pending: "text-[#888] bg-[#1a1a1a]", approved: "text-emerald-400 bg-emerald-500/10", rejected: "text-red-400 bg-red-500/10", edited: "text-amber-400 bg-amber-500/10" };

                return (
                  <div key={record._id} className={`border rounded-lg transition-all ${isExpanded ? "border-[#6EBE46]/30 bg-[#0c0c0c]" : "border-[#1a1a1a] bg-[#111] hover:border-[#333]"}`}>
                    <div className="flex items-center gap-3 px-4 py-3 cursor-pointer" onClick={() => setExpandedRecord(isExpanded ? null : record._id)}>
                      <ChevronRight className={`w-3.5 h-3.5 text-[#555] transition-transform ${isExpanded ? "rotate-90" : ""}`} />
                      <div className="flex-1 flex items-center gap-3 min-w-0">
                        {fieldNames.slice(0, 3).map((f) => (
                          <span key={f} className="text-xs text-[#ccc] truncate max-w-[150px]" title={`${f}: ${record[f]}`}>
                            <span className="text-[#555]">{f}:</span> {String(record[f] ?? "—")}
                          </span>
                        ))}
                      </div>
                      <Badge color={confColor}>{Math.round(conf * 100)}%</Badge>
                      <span className={`text-[9px] px-1.5 py-0.5 rounded capitalize ${statusColors[record._status] || ""}`}>{record._status}</span>
                      <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                        <button onClick={() => handleUpdateRecord(record._id, { _status: "approved" })} className={`p-1 rounded transition-colors ${record._status === "approved" ? "text-emerald-400 bg-emerald-500/10" : "text-[#555] hover:text-emerald-400 hover:bg-emerald-500/10"}`} title="Approve">
                          <Check className="w-3.5 h-3.5" />
                        </button>
                        <button onClick={() => handleUpdateRecord(record._id, { _status: "rejected" })} className={`p-1 rounded transition-colors ${record._status === "rejected" ? "text-red-400 bg-red-500/10" : "text-[#555] hover:text-red-400 hover:bg-red-500/10"}`} title="Reject">
                          <XCircle className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>

                    {isExpanded && (
                      <div className="px-4 pb-4 border-t border-[#1a1a1a] pt-3">
                        <div className="grid grid-cols-2 gap-2">
                          {fieldNames.map((field) => {
                            const val = record[field];
                            const isEditing = editingField?.recordId === record._id && editingField.field === field;
                            return (
                              <div key={field} className="flex items-start gap-2 p-2 bg-[#111] rounded border border-[#1a1a1a]">
                                <div className="flex-1 min-w-0">
                                  <div className="flex items-center gap-1.5 mb-1">
                                    <span className="text-[9px] text-[#6EBE46] font-mono">{field}</span>
                                    <span className="text-[8px] text-[#444]">{schemaFields[field]?.data_type}</span>
                                  </div>
                                  {isEditing ? (
                                    <div className="flex gap-1">
                                      <input value={editValue} onChange={(e) => setEditValue(e.target.value)} className="flex-1 px-2 py-1 bg-[#0a0a0a] border border-[#6EBE46]/30 rounded text-xs text-white" autoFocus onKeyDown={(e) => e.key === "Enter" && saveEdit()} />
                                      <button onClick={saveEdit} className="text-emerald-400 hover:text-emerald-300"><Check className="w-3 h-3" /></button>
                                      <button onClick={() => setEditingField(null)} className="text-red-400 hover:text-red-300"><X className="w-3 h-3" /></button>
                                    </div>
                                  ) : (
                                    <div className="text-xs text-[#ccc] cursor-pointer hover:text-white group flex items-center gap-1" onClick={() => startEdit(record._id, field, val)}>
                                      <span className="truncate">{val != null ? String(val) : <span className="text-[#444] italic">null</span>}</span>
                                      <Edit3 className="w-2.5 h-2.5 text-[#555] opacity-0 group-hover:opacity-100 flex-shrink-0" />
                                    </div>
                                  )}
                                </div>
                              </div>
                            );
                          })}
                        </div>
                        <div className="flex items-center gap-4 mt-3 text-[10px] text-[#555]">
                          <span>Source: {record._source_file}</span>
                          <span>Row: {record._source_row}</span>
                          <span>Confidence: {Math.round((record._confidence || 0) * 100)}%</span>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
              {filteredRecords.length === 0 && <div className="text-center py-12 text-[#555] text-sm">No {filter !== "all" ? filter : ""} records to show.</div>}
            </div>

            <div className="mt-4 pt-4 border-t border-[#1a1a1a] flex items-center justify-between">
              <span className="text-[10px] text-[#555] font-mono">{counts.approved} approved / {counts.total} total</span>
              <Button onClick={handleCommit} disabled={counts.approved === 0 || isLoading}>
                {isLoading ? <><Loader2 className="w-3.5 h-3.5 animate-spin" /> Committing...</> : <><Database className="w-3.5 h-3.5" /> Commit {counts.approved} Records</>}
              </Button>
            </div>
          </div>
        )}

        {/* ── STEP 5: Commit Result ────────────────────────── */}
        {step === "commit" && commitResult && (
          <div className="flex flex-col items-center justify-center h-full text-center py-12">
            <div className="w-16 h-16 rounded-full bg-emerald-500/10 border-2 border-emerald-500/30 flex items-center justify-center mb-6" style={{ animation: "scaleIn 0.5s cubic-bezier(0.175, 0.885, 0.32, 1.275) both" }}>
              <Database className="w-8 h-8 text-emerald-400" />
            </div>
            <h2 className="text-xl font-semibold text-white mb-2" style={{ fontFamily: "'Rajdhani', sans-serif", letterSpacing: "0.5px" }}>Data Committed</h2>
            <p className="text-sm text-[#888] mb-8 max-w-md">Your data is now live in the ATLAS graph. Explore it in Graph Explorer or upload more artifacts.</p>

            <Card className="p-5 mb-6 max-w-md w-full text-left">
              <div className="grid grid-cols-3 gap-4">
                <div>
                  <div className="text-[10px] text-[#666] uppercase tracking-wider mb-1" style={{ fontFamily: "'Rajdhani', sans-serif" }}>Nodes</div>
                  <div className="text-2xl font-bold font-mono text-[#6EBE46]">{commitResult.nodes_created}</div>
                </div>
                <div>
                  <div className="text-[10px] text-[#666] uppercase tracking-wider mb-1" style={{ fontFamily: "'Rajdhani', sans-serif" }}>Edges</div>
                  <div className="text-2xl font-bold font-mono text-[#6EBE46]">{commitResult.edges_created}</div>
                </div>
                <div>
                  <div className="text-[10px] text-[#666] uppercase tracking-wider mb-1" style={{ fontFamily: "'Rajdhani', sans-serif" }}>Collection</div>
                  <div className="text-sm font-mono text-[#ccc] mt-1">{commitResult.collection}</div>
                </div>
              </div>
            </Card>

            {commitResult.errors.length > 0 && (
              <Card className="p-4 mb-6 max-w-md w-full text-left border-amber-500/20">
                <h4 className="text-[10px] font-semibold text-amber-400 uppercase tracking-wider mb-2" style={{ fontFamily: "'Rajdhani', sans-serif" }}>Warnings ({commitResult.errors.length})</h4>
                <div className="space-y-1 max-h-[120px] overflow-y-auto">
                  {commitResult.errors.map((err, i) => (
                    <div key={i} className="flex items-start gap-2">
                      <AlertTriangle className="w-3 h-3 text-amber-400 mt-0.5 flex-shrink-0" />
                      <span className="text-[10px] text-[#888]">{err}</span>
                    </div>
                  ))}
                </div>
              </Card>
            )}

            <div className="flex gap-3">
              <Button variant="secondary" onClick={handleReset}><Upload className="w-3.5 h-3.5" /> Upload More</Button>
              <Button onClick={() => navigate("/graph")}><Zap className="w-3.5 h-3.5" /> View in Graph Explorer</Button>
            </div>
          </div>
        )}
      </main>

      <style>{`
        @keyframes scaleIn {
          0% { opacity: 0; transform: scale(0.5); }
          100% { opacity: 1; transform: scale(1); }
        }
      `}</style>
    </div>
  );
};

export default DataUpload;