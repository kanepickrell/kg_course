import { useState, useEffect, useCallback } from "react";
import {
  Search, Loader2, Package, FileCode, Server,
  Users, User, RefreshCw, Database, Layers, Tag, GitBranch,
  Download, ChevronRight, AlertTriangle,
  Crosshair, Sparkles, Target, Brain, BarChart2, TrendingUp,
  CheckCircle, Clock, Zap, Play, ArrowRight,
} from "lucide-react";

// =====================================================
// TYPES
// =====================================================

interface ProspectorProps {
  selectedNodes: string[];
  onNodeSelect: (nodes: string[]) => void;
  onNodeInspect: (nodeData: any) => void;
}

interface GraphNode {
  id: string;
  label: string;
  type: string;
  cluster: string;
  description?: string;
  tags?: string[];
  importance?: number;
  _artifact_type?: string;
  owner?: string;
  status?: string;
  tactic?: string;
  category?: string;
  riskLevel?: string;
  mitre_id?: string;
  [key: string]: any;
}

interface GraphEdge {
  id: string;
  source: string;
  target: string;
  type: string;
  relationship_type: string;
}

// Model type taxonomy — determines export format, readiness criteria, and Operator capability
type ModelType =
  | "llm_finetune"    // JSONL instruction format → Training Lab LoRA
  | "sequence_model"  // Ordered transition pairs → Markov / small transformer
  | "classifier"      // Tabular rows + categorical label → gradient boost
  | "regressor";      // Tabular rows + numeric target → gradient boost

type ExportFormat = "jsonl_instruct" | "transition_pairs" | "csv_tabular";

type TrainingStatus = "idle" | "training" | "trained" | "failed";

interface TrainingResult {
  status: TrainingStatus;
  trainedAt?: string;
  metric?: string;      // e.g. "87% accuracy", "RMSE: 12.4 mins"
  metricLabel?: string; // e.g. "Accuracy", "RMSE"
  modelPath?: string;
}

interface DatasetDefinition {
  id: string;
  name: string;
  description: string;
  sourceType: string;
  targetType: string;
  edgeType: string;
  modelType: ModelType;
  exportFormat: ExportFormat;
  targetField?: string;
  featureFields: string[];
  operatorCapability: string;
  examples: DatasetExample[];
  classDistribution: Record<string, number>;
  totalPossible: number;
  createdAt: string;
  training: TrainingResult;
}

interface DatasetExample {
  sourceId: string;
  sourceLabel: string;
  targetId: string;
  targetLabel: string;
  edgeId: string;
  features: Record<string, any>;
  sequenceContext?: string[];
  numericTarget?: number;
  outcome?: string;
}

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

// =====================================================
// CONSTANTS
// =====================================================

const TEAM_COLORS: Record<string, string> = {
  "Automation": "#6EBE46",
  "OPFOR": "#E6AA32",
  "Content Development": "#B4A082",
  "Range Operations": "#4A9ECC",
  "Unassigned": "#555555",
};

const TYPE_COLORS: Record<string, string> = {
  "LibraryModule": "#6EBE46",
  "Library Module": "#6EBE46",
  "ExecutionPlan": "#E6AA32",
  "Execution Plan": "#E6AA32",
  "RangeEnvironment": "#4A9ECC",
  "Range Environment": "#4A9ECC",
  "Scenario": "#9B59B6",
  "TTP": "#E74C3C",
  "Team": "#3498DB",
  "Person": "#1ABC9C",
};

// Model type visual config
const MODEL_TYPE_CONFIG: Record<ModelType, {
  badge: string;
  color: string;
  icon: React.ReactNode;
  label: string;
}> = {
  llm_finetune: {
    badge: "LLM",
    color: "#E6AA32",
    icon: <Brain className="w-3 h-3" />,
    label: "LLM Fine-tune",
  },
  sequence_model: {
    badge: "SEQ",
    color: "#4A9ECC",
    icon: <ArrowRight className="w-3 h-3" />,
    label: "Sequence Model",
  },
  classifier: {
    badge: "CLF",
    color: "#9B59B6",
    icon: <BarChart2 className="w-3 h-3" />,
    label: "Classifier",
  },
  regressor: {
    badge: "REG",
    color: "#1ABC9C",
    icon: <TrendingUp className="w-3 h-3" />,
    label: "Regressor",
  },
};

// Readiness thresholds per model type
const getReadiness = (dataset: DatasetDefinition): {
  trainable: boolean;
  label: string;
  color: string;
  progress: number; // 0-100 for progress bar
  hint: string;
} => {
  const n = dataset.examples.length;
  const classes = Object.keys(dataset.classDistribution).length;

  switch (dataset.modelType) {
    case "llm_finetune": {
      const target = 50;
      const progress = Math.min((n / target) * 100, 100);
      if (n >= target && classes >= 5)
        return { trainable: true, label: "Trainable", color: "#6EBE46", progress, hint: "" };
      if (n >= 10)
        return { trainable: false, label: "Building", color: "#E6AA32", progress, hint: `Need ${target - n} more examples and ${Math.max(0, 5 - classes)} more classes` };
      return { trainable: false, label: "Needs Data", color: "#E74C3C", progress, hint: `Need ${target} examples across 5+ classes` };
    }
    case "sequence_model": {
      const target = 20;
      const progress = Math.min((n / target) * 100, 100);
      if (n >= target)
        return { trainable: true, label: "Trainable", color: "#6EBE46", progress, hint: "" };
      if (n >= 5)
        return { trainable: false, label: "Building", color: "#E6AA32", progress, hint: `Need ${target - n} more sequences` };
      return { trainable: false, label: "Needs Data", color: "#E74C3C", progress, hint: `Need ${target} complete sequences` };
    }
    case "classifier": {
      const target = 30;
      const minPerClass = Math.min(...Object.values(dataset.classDistribution), 0);
      const balanced = classes >= 2 && minPerClass >= 5;
      const progress = Math.min((n / target) * 100, 100);
      if (n >= target && balanced)
        return { trainable: true, label: "Trainable", color: "#6EBE46", progress, hint: "" };
      if (n >= 10)
        return { trainable: false, label: "Imbalanced", color: "#E6AA32", progress, hint: `Classes uneven — need 5+ examples per class` };
      return { trainable: false, label: "Needs Data", color: "#E74C3C", progress, hint: `Need ${target} examples across balanced classes` };
    }
    case "regressor": {
      const withTarget = dataset.examples.filter(e => e.numericTarget !== undefined).length;
      const target = 20;
      const progress = Math.min((withTarget / target) * 100, 100);
      if (withTarget >= target)
        return { trainable: true, label: "Trainable", color: "#6EBE46", progress, hint: "" };
      if (withTarget >= 5)
        return { trainable: false, label: "Building", color: "#E6AA32", progress, hint: `Need ${target - withTarget} more runs with actual duration recorded` };
      return { trainable: false, label: "Needs Target Data", color: "#E74C3C", progress, hint: `Requires execution_history with actual_duration_mins` };
    }
  }
};

// Dataset templates — one per model type / use case
const DATASET_TEMPLATES: Omit<DatasetDefinition, "id" | "examples" | "classDistribution" | "totalPossible" | "createdAt" | "training">[] = [
  {
    name: "Technique Mapping",
    description: "LibraryModule → TTP classification. Fine-tune a model to auto-tag which MITRE technique a module implements on ingest.",
    sourceType: "LibraryModule",
    targetType: "TTP",
    edgeType: "MAPS_TO_TECHNIQUE",
    modelType: "llm_finetune",
    exportFormat: "jsonl_instruct",
    featureFields: ["description", "category", "tactic", "subcategory"],
    operatorCapability: "Auto-suggests technique tag when a new module is dropped on the canvas",
  },
  {
    name: "Phase Sequences",
    description: "ExecutionPlan tactic ordering. Train a sequence model on observed phase chains to suggest the next phase in a campaign.",
    sourceType: "ExecutionPlan",
    targetType: "ExecutionPlan",
    edgeType: "PHASE_SEQUENCE",
    modelType: "sequence_model",
    exportFormat: "transition_pairs",
    featureFields: ["phases.tactic", "phases.technique", "phases.requires"],
    operatorCapability: "Suggests next phase as OPFOR builds a campaign chain in Operator",
  },
  {
    name: "Phase Outcome Prediction",
    description: "Predicts success / detected / failure per phase from environment and module features. Requires execution_history data on ExecutionPlan.",
    sourceType: "ExecutionPlan",
    targetType: "ExecutionPlan",
    edgeType: "PHASE_OUTCOME",
    modelType: "classifier",
    exportFormat: "csv_tabular",
    targetField: "outcome",
    featureFields: ["tactic", "technique", "detection_risk", "environment.network_topology", "environment.os"],
    operatorCapability: "Warns OPFOR when a phase has high historical detection probability before running",
  },
  {
    name: "Duration Estimation",
    description: "Predicts total operation time from plan structure and environment complexity. Requires actual_duration_mins in execution_history.",
    sourceType: "ExecutionPlan",
    targetType: "ExecutionPlan",
    edgeType: "PHASE_DURATION",
    modelType: "regressor",
    exportFormat: "csv_tabular",
    targetField: "actual_duration_mins",
    featureFields: ["phase_count", "tactic_diversity", "environment.host_count", "detection_risk_avg"],
    operatorCapability: "Estimates total exercise time before OPFOR commits to a plan",
  },
  {
    name: "Environment Support",
    description: "RangeEnvironment → TTP support mapping. Train a model to predict which techniques a new environment can host from its topology.",
    sourceType: "RangeEnvironment",
    targetType: "TTP",
    edgeType: "SUPPORTS_TECHNIQUE",
    modelType: "llm_finetune",
    exportFormat: "jsonl_instruct",
    featureFields: ["description", "platform", "network_topology", "segments"],
    operatorCapability: "Validates whether a selected range environment supports the planned techniques",
  },
];

// =====================================================
// HELPERS
// =====================================================

const getTypeIcon = (type: string) => {
  const t = type?.toLowerCase() || "";
  if (t.includes("module") || t.includes("library")) return <FileCode className="w-4 h-4" />;
  if (t.includes("execution") || t.includes("plan")) return <GitBranch className="w-4 h-4" />;
  if (t.includes("range") || t.includes("environment")) return <Server className="w-4 h-4" />;
  if (t.includes("scenario")) return <Target className="w-4 h-4" />;
  if (t.includes("ttp")) return <Crosshair className="w-4 h-4" />;
  if (t.includes("team")) return <Users className="w-4 h-4" />;
  if (t.includes("person")) return <User className="w-4 h-4" />;
  return <Package className="w-4 h-4" />;
};

const getTeamColor = (team: string): string => {
  if (!team) return TEAM_COLORS.Unassigned;
  const match = Object.entries(TEAM_COLORS).find(
    ([k]) => k.toLowerCase() === team.toLowerCase() || team.toLowerCase().includes(k.toLowerCase())
  );
  return match ? match[1] : TEAM_COLORS.Unassigned;
};

const getTypeColor = (type: string): string => TYPE_COLORS[type] || "#888888";

// =====================================================
// MAIN COMPONENT
// =====================================================

const Prospector = ({ selectedNodes, onNodeSelect, onNodeInspect }: ProspectorProps) => {
  const [activePanel, setActivePanel] = useState<"artifacts" | "datasets">("artifacts");
  const [loading, setLoading] = useState(true);
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [edges, setEdges] = useState<GraphEdge[]>([]);
  const [filteredNodes, setFilteredNodes] = useState<GraphNode[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [filterType, setFilterType] = useState<string | null>(null);
  const [filterTeam, setFilterTeam] = useState<string | null>(null);
  const [datasets, setDatasets] = useState<DatasetDefinition[]>([]);
  const [selectedDataset, setSelectedDataset] = useState<DatasetDefinition | null>(null);
  const [labelingMode, setLabelingMode] = useState(false);
  const [labelingDataset, setLabelingDataset] = useState<DatasetDefinition | null>(null);

  // ── Fetch graph data ──
  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/graph`);
      if (!res.ok) throw new Error("Failed to fetch graph");
      const data = await res.json();

      const normalizedNodes = (data.nodes || []).map((node: any) => ({
        ...node,
        type: node._artifact_type || node.type || "Unknown",
        cluster: node.owner || node.cluster || "Unassigned",
      }));

      setNodes(normalizedNodes);
      setEdges(data.edges || []);
      setFilteredNodes(normalizedNodes);
      buildDatasets(normalizedNodes, data.edges || []);
    } catch (err) {
      console.error("Prospector fetch failed:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  // ── Build datasets from graph edges + fetch coverage counts ──
  const buildDatasets = async (nodes: GraphNode[], edges: GraphEdge[]) => {
    const nodeMap = new Map(nodes.map(n => [n.id, n]));
    const built: DatasetDefinition[] = [];

    for (const template of DATASET_TEMPLATES) {
      const matchingEdges = edges.filter(e => {
        const relType = (e.relationship_type || e.type || "").toUpperCase().replace(/ /g, "_");
        return relType === template.edgeType;
      });

      const examples: DatasetExample[] = [];
      const classDistribution: Record<string, number> = {};

      for (const edge of matchingEdges) {
        const source = nodeMap.get(edge.source);
        const target = nodeMap.get(edge.target);
        if (!source || !target) continue;

        // Build typed features based on model type
        const features: Record<string, any> = {};
        for (const field of template.featureFields) {
          const val = source[field] ?? source[field.split(".")[0]];
          if (val !== undefined) features[field] = val;
        }

        examples.push({
          sourceId: edge.source,
          sourceLabel: source.label || source.id,
          targetId: edge.target,
          targetLabel: target.label || target.id,
          edgeId: edge.id,
          features,
          numericTarget: template.modelType === "regressor" ? source.estimatedDuration : undefined,
          outcome: template.modelType === "classifier" ? source.status : undefined,
        });

        const targetLabel = target.label || target.id;
        classDistribution[targetLabel] = (classDistribution[targetLabel] || 0) + 1;
      }

      // Fetch taxonomy coverage count for LLM datasets
      let totalPossible = 0;
      if (template.modelType === "llm_finetune" && template.targetType === "TTP") {
        try {
          const covRes = await fetch(
            `${API_BASE}/api/datasets/coverage?edgeType=${template.edgeType}&targetType=${template.targetType}`
          );
          if (covRes.ok) {
            const covData = await covRes.json();
            totalPossible = covData.total ?? 0;
          }
        } catch {
          // coverage endpoint optional — fail silently
        }
      }

      built.push({
        id: template.edgeType,
        name: template.name,
        description: template.description,
        sourceType: template.sourceType,
        targetType: template.targetType,
        edgeType: template.edgeType,
        modelType: template.modelType,
        exportFormat: template.exportFormat,
        targetField: template.targetField,
        featureFields: template.featureFields,
        operatorCapability: template.operatorCapability,
        examples,
        classDistribution,
        totalPossible,
        createdAt: new Date().toISOString(),
        training: { status: "idle" },
      });
    }

    setDatasets(built);
  };

  // ── Filter nodes ──
  useEffect(() => {
    let result = [...nodes];
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      result = result.filter(n =>
        n.label?.toLowerCase().includes(q) ||
        n.description?.toLowerCase().includes(q) ||
        n.type?.toLowerCase().includes(q) ||
        n.mitre_id?.toLowerCase().includes(q)
      );
    }
    if (filterType) {
      result = result.filter(n => {
        const nodeType = n._artifact_type || n.type;
        return nodeType === filterType || nodeType?.replace(/\s/g, "") === filterType.replace(/\s/g, "");
      });
    }
    if (filterTeam) {
      result = result.filter(n => {
        const team = n.owner || n.cluster;
        return team?.toLowerCase().includes(filterTeam.toLowerCase());
      });
    }
    setFilteredNodes(result);
  }, [nodes, searchQuery, filterType, filterTeam]);

  const uniqueTypes = [...new Set(nodes.map(n => n._artifact_type || n.type).filter(Boolean))].sort();
  const uniqueTeams = [...new Set(nodes.map(n => n.owner || n.cluster).filter(t => t && t !== "Unassigned" && t !== "Unknown" && t !== ""))].sort();

  // ── Export dataset ──
  const exportDataset = async (dataset: DatasetDefinition) => {
    try {
      // Try backend export first (richer formatting)
      const res = await fetch(
        `${API_BASE}/api/datasets/export?edgeType=${dataset.edgeType}&sourceType=${dataset.sourceType}&targetType=${dataset.targetType}&exportFormat=${dataset.exportFormat}`
      );
      if (res.ok) {
        const blob = await res.blob();
        const ext = dataset.exportFormat === "csv_tabular" ? "csv" : dataset.exportFormat === "transition_pairs" ? "json" : "jsonl";
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `${dataset.id.toLowerCase()}_dataset.${ext}`;
        a.click();
        URL.revokeObjectURL(url);
        return;
      }
    } catch { /* fall through to local export */ }

    // Fallback: client-side export from in-memory examples
    let content = "";
    const ext = dataset.exportFormat === "csv_tabular" ? "csv"
      : dataset.exportFormat === "transition_pairs" ? "json" : "jsonl";

    if (dataset.exportFormat === "jsonl_instruct") {
      content = dataset.examples.map(ex => JSON.stringify({
        instruction: `Given this ${dataset.sourceType}, classify the ${dataset.targetType} it maps to.`,
        input: [
          ex.features.description || ex.sourceLabel,
          ex.features.category ? `Category: ${ex.features.category}` : "",
          ex.features.tactic ? `Tactic: ${ex.features.tactic}` : "",
        ].filter(Boolean).join(". "),
        output: ex.features.targetMitreId || ex.targetLabel,
      })).join("\n");
    } else if (dataset.exportFormat === "transition_pairs") {
      content = JSON.stringify(
        dataset.examples.map(ex => ({
          sequence: ex.sequenceContext || [],
          next: ex.targetLabel,
          features: ex.features,
        })),
        null, 2
      );
    } else if (dataset.exportFormat === "csv_tabular") {
      const fields = [...dataset.featureFields, dataset.targetField || "label"];
      content = fields.join(",") + "\n" +
        dataset.examples.map(ex => {
          return fields.map(f => {
            const v = f === dataset.targetField ? (ex.outcome ?? ex.numericTarget ?? ex.targetLabel) : (ex.features[f] ?? "");
            return `"${String(v).replace(/"/g, '""')}"`;
          }).join(",");
        }).join("\n");
    }

    const blob = new Blob([content], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${dataset.id.toLowerCase()}_dataset.${ext}`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // ── Train dataset ──
  const trainDataset = async (dataset: DatasetDefinition) => {
    const readiness = getReadiness(dataset);
    if (!readiness.trainable) return;

    // Optimistic update — show training state
    setDatasets(prev => prev.map(d =>
      d.id === dataset.id ? { ...d, training: { status: "training" } } : d
    ));
    if (selectedDataset?.id === dataset.id) {
      setSelectedDataset(prev => prev ? { ...prev, training: { status: "training" } } : prev);
    }

    try {
      const res = await fetch(`${API_BASE}/api/datasets/train`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          edgeType: dataset.edgeType,
          sourceType: dataset.sourceType,
          targetType: dataset.targetType,
          modelType: dataset.modelType,
          exportFormat: dataset.exportFormat,
          targetField: dataset.targetField,
          featureFields: dataset.featureFields,
        }),
      });

      if (res.ok) {
        const result = await res.json();
        const trainingResult: TrainingResult = {
          status: "trained",
          trainedAt: new Date().toISOString(),
          metric: result.metric,
          metricLabel: result.metricLabel,
          modelPath: result.modelPath,
        };
        setDatasets(prev => prev.map(d =>
          d.id === dataset.id ? { ...d, training: trainingResult } : d
        ));
        if (selectedDataset?.id === dataset.id) {
          setSelectedDataset(prev => prev ? { ...prev, training: trainingResult } : prev);
        }
      } else {
        throw new Error("Training failed");
      }
    } catch {
      const failed: TrainingResult = { status: "failed" };
      setDatasets(prev => prev.map(d =>
        d.id === dataset.id ? { ...d, training: failed } : d
      ));
      if (selectedDataset?.id === dataset.id) {
        setSelectedDataset(prev => prev ? { ...prev, training: failed } : prev);
      }
    }
  };

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center bg-[#0a0a0a]">
        <div className="text-center">
          <Loader2 className="w-6 h-6 animate-spin text-[#6EBE46] mx-auto mb-2" />
          <p className="text-xs text-[#555]" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
            Loading graph data...
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col bg-[#0a0a0a]">
      {/* ── Header ── */}
      <div className="flex-shrink-0 border-b border-[#1a1a1a] bg-[#0c0c0c]">
        <div className="flex items-center justify-between px-3 py-2">
          <div className="flex gap-1">
            <button
              onClick={() => setActivePanel("artifacts")}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded transition-all ${
                activePanel === "artifacts"
                  ? "bg-[#6EBE46]/15 text-[#6EBE46] border border-[#6EBE46]/30"
                  : "text-[#666] hover:text-white border border-transparent"
              }`}
            >
              <Layers className="w-3.5 h-3.5" />
              Artifacts
              <span className={`px-1 py-0.5 text-[10px] rounded ${activePanel === "artifacts" ? "bg-[#6EBE46]/20" : "bg-[#1a1a1a]"}`}>
                {nodes.length}
              </span>
            </button>
            <button
              onClick={() => setActivePanel("datasets")}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded transition-all ${
                activePanel === "datasets"
                  ? "bg-[#E6AA32]/15 text-[#E6AA32] border border-[#E6AA32]/30"
                  : "text-[#666] hover:text-white border border-transparent"
              }`}
            >
              <Database className="w-3.5 h-3.5" />
              Datasets
              <span className={`px-1 py-0.5 text-[10px] rounded ${activePanel === "datasets" ? "bg-[#E6AA32]/20" : "bg-[#1a1a1a]"}`}>
                {datasets.filter(d => d.examples.length > 0).length}
              </span>
            </button>
          </div>
          <button
            onClick={fetchData}
            className="p-1.5 rounded hover:bg-[#1a1a1a] text-[#555] hover:text-[#6EBE46] transition-colors"
            title="Refresh"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </div>

        {/* ── Search + filters (artifacts only) ── */}
        {activePanel === "artifacts" && (
          <div className="px-3 pb-2 space-y-2">
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[#444]" />
              <input
                type="text"
                placeholder="Search artifacts..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-8 pr-3 py-1.5 bg-[#111] border border-[#222] rounded text-xs text-white placeholder:text-[#444] focus:outline-none focus:border-[#6EBE46]/50"
                style={{ fontFamily: "'JetBrains Mono', monospace" }}
              />
            </div>
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="text-[10px] text-[#555] uppercase tracking-wider mr-1">Type</span>
              <button
                onClick={() => setFilterType(null)}
                className={`px-2 py-0.5 text-[10px] rounded border transition-all ${!filterType ? "bg-[#6EBE46]/15 border-[#6EBE46]/30 text-[#6EBE46]" : "border-[#222] text-[#555] hover:border-[#444]"}`}
              >
                All
              </button>
              {uniqueTypes.map(type => (
                <button
                  key={type}
                  onClick={() => setFilterType(filterType === type ? null : type)}
                  className={`px-2 py-0.5 text-[10px] rounded border transition-all flex items-center gap-1 ${filterType === type ? "border-[#6EBE46]/30 text-white" : "border-[#222] text-[#555] hover:border-[#444] hover:text-[#888]"}`}
                  style={filterType === type ? { backgroundColor: getTypeColor(type) + "20", borderColor: getTypeColor(type) + "50" } : {}}
                >
                  {getTypeIcon(type)}
                  {type}
                </button>
              ))}
            </div>
            {uniqueTeams.length > 0 && (
              <div className="flex items-center gap-1.5 flex-wrap">
                <span className="text-[10px] text-[#555] uppercase tracking-wider mr-1">Team</span>
                <button
                  onClick={() => setFilterTeam(null)}
                  className={`px-2 py-0.5 text-[10px] rounded border transition-all ${!filterTeam ? "bg-[#6EBE46]/15 border-[#6EBE46]/30 text-[#6EBE46]" : "border-[#222] text-[#555] hover:border-[#444]"}`}
                >
                  All
                </button>
                {uniqueTeams.map(team => (
                  <button
                    key={team}
                    onClick={() => setFilterTeam(filterTeam === team ? null : team)}
                    className={`px-2 py-0.5 text-[10px] rounded border transition-all ${filterTeam === team ? "text-white" : "border-[#222] text-[#555] hover:border-[#444] hover:text-[#888]"}`}
                    style={filterTeam === team ? { backgroundColor: getTeamColor(team) + "20", borderColor: getTeamColor(team) + "50" } : {}}
                  >
                    {team}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── Count bar ── */}
      <div className="flex-shrink-0 px-3 py-1.5 border-b border-[#151515] bg-[#0b0b0b]">
        <span className="text-[10px] text-[#444]" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
          {activePanel === "artifacts"
            ? `${filteredNodes.length} of ${nodes.length} artifacts • ${edges.length} edges`
            : `${datasets.filter(d => d.examples.length > 0).length} active datasets • ${datasets.reduce((a, d) => a + d.examples.length, 0)} total examples`}
        </span>
      </div>

      {/* ── Main Content ── */}
      <div className="flex-1 min-h-0 overflow-y-auto">
        {activePanel === "artifacts" ? (
          <ArtifactList
            nodes={filteredNodes}
            edges={edges}
            selectedNodes={selectedNodes}
            onNodeSelect={onNodeSelect}
            onNodeInspect={onNodeInspect}
            labelingMode={labelingMode}
            labelingDataset={labelingDataset}
          />
        ) : (
          <DatasetPanel
            datasets={datasets}
            selectedDataset={selectedDataset}
            onSelectDataset={setSelectedDataset}
            onExport={exportDataset}
            onTrain={trainDataset}
            onStartLabeling={(ds) => {
              setLabelingMode(true);
              setLabelingDataset(ds);
              setActivePanel("artifacts");
              setFilterType(ds.sourceType);
            }}
          />
        )}
      </div>

      {/* ── Labeling mode bar ── */}
      {labelingMode && labelingDataset && (
        <div className="flex-shrink-0 px-3 py-2 border-t border-[#E6AA32]/30 bg-[#E6AA32]/5 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Sparkles className="w-3.5 h-3.5 text-[#E6AA32]" />
            <span className="text-xs text-[#E6AA32] font-medium">
              Prospecting: {labelingDataset.name}
            </span>
            <span className="text-[10px] text-[#E6AA32]/60">
              Click artifacts to label for training
            </span>
          </div>
          <button
            onClick={() => { setLabelingMode(false); setLabelingDataset(null); setFilterType(null); }}
            className="px-2 py-1 text-[10px] text-[#E6AA32] border border-[#E6AA32]/30 rounded hover:bg-[#E6AA32]/10 transition-colors"
          >
            Exit Prospecting
          </button>
        </div>
      )}

      {/* ── Bottom status ── */}
      <div className="flex-shrink-0 px-3 py-1.5 border-t border-[#1a1a1a] bg-[#0c0c0c] flex items-center justify-between">
        <span className="text-[10px] text-[#444]" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
          {selectedNodes.length > 0 ? `${selectedNodes.length} selected` : "Click to select • Double-click to inspect"}
        </span>
        <span className="text-[10px] text-[#333]" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
          PROSPECTOR v3
        </span>
      </div>
    </div>
  );
};

// =====================================================
// ARTIFACT LIST
// =====================================================

const ArtifactList: React.FC<{
  nodes: GraphNode[];
  edges: GraphEdge[];
  selectedNodes: string[];
  onNodeSelect: (nodes: string[]) => void;
  onNodeInspect: (nodeData: any) => void;
  labelingMode: boolean;
  labelingDataset: DatasetDefinition | null;
}> = ({ nodes, edges, selectedNodes, onNodeSelect, onNodeInspect, labelingMode, labelingDataset }) => {

  const getEdgeCount = (nodeId: string) =>
    edges.filter(e => e.source === nodeId || e.target === nodeId).length;

  if (nodes.length === 0) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <Search className="w-8 h-8 text-[#333] mx-auto mb-2" />
          <p className="text-xs text-[#555]">No artifacts match your filters</p>
        </div>
      </div>
    );
  }

  return (
    <div className="px-2 py-1.5 space-y-1">
      {nodes.map((node) => {
        const nodeType = node._artifact_type || node.type;
        const nodeTeam = node.owner || node.cluster;
        const edgeCount = getEdgeCount(node.id);
        const isSelected = selectedNodes.includes(node.id);
        const typeColor = getTypeColor(nodeType);
        const teamColor = getTeamColor(nodeTeam);

        return (
          <div
            key={node.id}
            onClick={() => onNodeSelect([node.id])}
            onDoubleClick={() => onNodeInspect(node)}
            className={`px-3 py-2.5 rounded-lg border cursor-pointer transition-all group ${
              isSelected
                ? "border-[#6EBE46]/50 bg-[#6EBE46]/5"
                : "border-[#1a1a1a] hover:border-[#333] bg-[#111] hover:bg-[#141414]"
            }`}
          >
            <div className="flex items-start gap-2.5">
              <div
                className="flex-shrink-0 w-8 h-8 rounded flex items-center justify-center border"
                style={{ backgroundColor: typeColor + "15", borderColor: typeColor + "40", color: typeColor }}
              >
                {getTypeIcon(nodeType)}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-0.5">
                  <span className="text-xs font-medium text-white truncate">{node.label}</span>
                  {edgeCount > 0 && (
                    <span className="text-[10px] text-[#555] flex items-center gap-0.5">
                      <GitBranch className="w-2.5 h-2.5" />{edgeCount}
                    </span>
                  )}
                </div>
                {node.description && (
                  <p className="text-[10px] text-[#555] truncate mb-1.5">{node.description}</p>
                )}
                <div className="flex items-center gap-1.5 flex-wrap">
                  <span
                    className="px-1.5 py-0.5 text-[9px] rounded border"
                    style={{ backgroundColor: typeColor + "10", borderColor: typeColor + "30", color: typeColor }}
                  >
                    {nodeType}
                  </span>
                  {nodeTeam && nodeTeam !== "Unassigned" && nodeTeam !== "Unknown" && nodeTeam !== "" && (
                    <span
                      className="px-1.5 py-0.5 text-[9px] rounded border"
                      style={{ backgroundColor: teamColor + "15", borderColor: teamColor + "30", color: teamColor }}
                    >
                      {nodeTeam}
                    </span>
                  )}
                  {node.status && (
                    <span className="px-1.5 py-0.5 text-[9px] rounded bg-[#1a1a1a] border border-[#222] text-[#888]">
                      {node.status}
                    </span>
                  )}
                  {node.mitre_id && (
                    <span className="px-1.5 py-0.5 text-[9px] rounded bg-red-500/10 border border-red-500/20 text-red-400 font-mono">
                      {node.mitre_id}
                    </span>
                  )}
                </div>
              </div>
              {labelingMode && labelingDataset && (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    // TODO: Open labeling modal for this node + dataset
                    alert(`Label "${node.label}" for ${labelingDataset.name} dataset`);
                  }}
                  className="flex-shrink-0 px-2 py-1 text-[10px] bg-[#E6AA32]/10 border border-[#E6AA32]/30 text-[#E6AA32] rounded hover:bg-[#E6AA32]/20 transition-colors opacity-0 group-hover:opacity-100"
                >
                  <Tag className="w-3 h-3 inline mr-1" />
                  Label
                </button>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
};

// =====================================================
// DATASET PANEL
// =====================================================

const DatasetPanel: React.FC<{
  datasets: DatasetDefinition[];
  selectedDataset: DatasetDefinition | null;
  onSelectDataset: (ds: DatasetDefinition | null) => void;
  onExport: (ds: DatasetDefinition) => void;
  onTrain: (ds: DatasetDefinition) => void;
  onStartLabeling: (ds: DatasetDefinition) => void;
}> = ({ datasets, selectedDataset, onSelectDataset, onExport, onTrain, onStartLabeling }) => {

  if (selectedDataset) {
    return (
      <DatasetDetail
        dataset={selectedDataset}
        onBack={() => onSelectDataset(null)}
        onExport={onExport}
        onTrain={onTrain}
        onStartLabeling={onStartLabeling}
      />
    );
  }

  return (
    <div className="p-3 space-y-2">
      <p className="text-[10px] text-[#555] mb-3">
        Datasets are auto-detected from graph edges. Each entry trains a different model type for use in Operator.
      </p>

      {datasets.map(ds => {
        const hasData = ds.examples.length > 0;
        const readiness = getReadiness(ds);
        const modelCfg = MODEL_TYPE_CONFIG[ds.modelType];

        return (
          <div
            key={ds.id}
            onClick={() => onSelectDataset(ds)}
            className={`p-3 rounded-lg border cursor-pointer transition-all ${
              hasData
                ? "border-[#E6AA32]/20 bg-[#111] hover:border-[#E6AA32]/40"
                : "border-[#1a1a1a] bg-[#0e0e0e] hover:border-[#333]"
            }`}
          >
            {/* Header row */}
            <div className="flex items-start justify-between mb-2">
              <div className="flex items-center gap-2">
                <Database className={`w-4 h-4 ${hasData ? "text-[#E6AA32]" : "text-[#444]"}`} />
                <span className={`text-xs font-medium ${hasData ? "text-white" : "text-[#666]"}`}>
                  {ds.name}
                </span>
              </div>
              <div className="flex items-center gap-1.5">
                {/* Model type badge */}
                <span
                  className="flex items-center gap-1 px-1.5 py-0.5 text-[10px] rounded border font-mono font-bold"
                  style={{ color: modelCfg.color, borderColor: modelCfg.color + "40", backgroundColor: modelCfg.color + "10" }}
                >
                  {modelCfg.icon}
                  {modelCfg.badge}
                </span>
                {/* Training status badge */}
                {ds.training.status === "trained" && (
                  <span className="flex items-center gap-1 px-1.5 py-0.5 text-[10px] rounded bg-[#6EBE46]/10 border border-[#6EBE46]/30 text-[#6EBE46]">
                    <CheckCircle className="w-2.5 h-2.5" />
                    Trained
                  </span>
                )}
                {ds.training.status === "training" && (
                  <span className="flex items-center gap-1 px-1.5 py-0.5 text-[10px] rounded bg-[#4A9ECC]/10 border border-[#4A9ECC]/30 text-[#4A9ECC]">
                    <Loader2 className="w-2.5 h-2.5 animate-spin" />
                    Training
                  </span>
                )}
                {/* Example count */}
                {hasData && ds.training.status === "idle" && (
                  <span className="px-1.5 py-0.5 text-[10px] rounded bg-[#E6AA32]/10 text-[#E6AA32] border border-[#E6AA32]/20">
                    {ds.examples.length} examples
                  </span>
                )}
                {!hasData && (
                  <span className="px-1.5 py-0.5 text-[10px] rounded bg-[#1a1a1a] text-[#555] border border-[#222]">
                    Empty
                  </span>
                )}
              </div>
            </div>

            <p className="text-[10px] text-[#555] mb-2">{ds.description}</p>

            {/* Pattern */}
            <div className="text-[10px] text-[#444] font-mono mb-2">
              {ds.sourceType} → {ds.edgeType} → {ds.targetType}
            </div>

            {/* Readiness progress bar */}
            {hasData && (
              <div className="space-y-1">
                <div className="flex justify-between items-center">
                  <span className="text-[10px]" style={{ color: readiness.color }}>
                    {readiness.label}
                  </span>
                  <span className="text-[10px] text-[#444]">
                    {Math.round(readiness.progress)}%
                  </span>
                </div>
                <div className="h-1 bg-[#1a1a1a] rounded overflow-hidden">
                  <div
                    className="h-full rounded transition-all"
                    style={{ width: `${readiness.progress}%`, backgroundColor: readiness.color }}
                  />
                </div>
              </div>
            )}

            {/* Trained metric */}
            {ds.training.status === "trained" && ds.training.metric && (
              <div className="mt-2 text-[10px] text-[#6EBE46]">
                {ds.training.metricLabel}: {ds.training.metric}
              </div>
            )}

            {/* Operator capability hint */}
            <div className="mt-2 flex items-start gap-1">
              <Zap className="w-2.5 h-2.5 text-[#E6AA32]/40 mt-0.5 flex-shrink-0" />
              <span className="text-[9px] text-[#444] italic">{ds.operatorCapability}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
};

// =====================================================
// DATASET DETAIL
// =====================================================

const DatasetDetail: React.FC<{
  dataset: DatasetDefinition;
  onBack: () => void;
  onExport: (ds: DatasetDefinition) => void;
  onTrain: (ds: DatasetDefinition) => void;
  onStartLabeling: (ds: DatasetDefinition) => void;
}> = ({ dataset, onBack, onExport, onTrain, onStartLabeling }) => {
  const readiness = getReadiness(dataset);
  const modelCfg = MODEL_TYPE_CONFIG[dataset.modelType];
  const classEntries = Object.entries(dataset.classDistribution).sort((a, b) => b[1] - a[1]);
  const maxCount = Math.max(...classEntries.map(([, c]) => c), 1);
  const coveragePct = dataset.totalPossible > 0
    ? Math.round((Object.keys(dataset.classDistribution).length / dataset.totalPossible) * 100)
    : null;

  // Stats vary by model type
  const renderStats = () => {
    switch (dataset.modelType) {
      case "llm_finetune":
        return (
          <div className="grid grid-cols-3 gap-2">
            <StatCard value={dataset.examples.length} label="Examples" color="#E6AA32" />
            <StatCard value={classEntries.length} label="Classes" color="white" />
            <StatCard
              value={coveragePct !== null ? `${coveragePct}%` : `${classEntries.length}`}
              label={coveragePct !== null ? "Coverage" : "Classes"}
              color={coveragePct !== null && coveragePct >= 20 ? "#6EBE46" : "#E6AA32"}
            />
          </div>
        );
      case "sequence_model":
        return (
          <div className="grid grid-cols-3 gap-2">
            <StatCard value={dataset.examples.length} label="Sequences" color="#4A9ECC" />
            <StatCard value={classEntries.length} label="Transitions" color="white" />
            <StatCard value={dataset.examples.length > 0 ? "Ready" : "Empty"} label="Markov" color={dataset.examples.length >= 5 ? "#6EBE46" : "#E74C3C"} />
          </div>
        );
      case "classifier": {
        const minClass = classEntries.length > 0 ? Math.min(...classEntries.map(([, c]) => c)) : 0;
        return (
          <div className="grid grid-cols-3 gap-2">
            <StatCard value={dataset.examples.length} label="Examples" color="#9B59B6" />
            <StatCard value={classEntries.length} label="Classes" color="white" />
            <StatCard
              value={minClass >= 5 ? "Balanced" : "Skewed"}
              label={`Min: ${minClass}`}
              color={minClass >= 5 ? "#6EBE46" : "#E6AA32"}
            />
          </div>
        );
      }
      case "regressor": {
        const withTarget = dataset.examples.filter(e => e.numericTarget !== undefined);
        const targets = withTarget.map(e => e.numericTarget as number);
        const minT = targets.length > 0 ? Math.min(...targets) : 0;
        const maxT = targets.length > 0 ? Math.max(...targets) : 0;
        return (
          <div className="grid grid-cols-3 gap-2">
            <StatCard value={withTarget.length} label="With Target" color="#1ABC9C" />
            <StatCard value={`${minT}m`} label="Min Duration" color="white" />
            <StatCard value={`${maxT}m`} label="Max Duration" color="white" />
          </div>
        );
      }
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-3 py-2.5 border-b border-[#1a1a1a] bg-[#0c0c0c]">
        <div className="flex items-center justify-between mb-1">
          <div className="flex items-center gap-2">
            <button onClick={onBack} className="text-[#555] hover:text-white transition-colors">
              <ChevronRight className="w-3.5 h-3.5 rotate-180" />
            </button>
            <Database className="w-4 h-4 text-[#E6AA32]" />
            <span className="text-xs font-medium text-white">{dataset.name}</span>
            <span
              className="flex items-center gap-1 px-1.5 py-0.5 text-[10px] rounded border font-mono font-bold"
              style={{ color: modelCfg.color, borderColor: modelCfg.color + "40", backgroundColor: modelCfg.color + "10" }}
            >
              {modelCfg.icon}
              {modelCfg.badge}
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <button
              onClick={() => onStartLabeling(dataset)}
              className="px-2 py-1 text-[10px] bg-[#E6AA32]/10 border border-[#E6AA32]/30 text-[#E6AA32] rounded hover:bg-[#E6AA32]/20 transition-colors flex items-center gap-1"
            >
              <Sparkles className="w-3 h-3" />
              Prospect
            </button>
            <button
              onClick={() => onExport(dataset)}
              disabled={dataset.examples.length === 0}
              className="px-2 py-1 text-[10px] bg-[#4A9ECC]/10 border border-[#4A9ECC]/30 text-[#4A9ECC] rounded hover:bg-[#4A9ECC]/20 transition-colors disabled:opacity-30 flex items-center gap-1"
            >
              <Download className="w-3 h-3" />
              Export
            </button>
            <button
              onClick={() => onTrain(dataset)}
              disabled={!readiness.trainable || dataset.training.status === "training"}
              className="px-2 py-1 text-[10px] bg-[#6EBE46]/10 border border-[#6EBE46]/30 text-[#6EBE46] rounded hover:bg-[#6EBE46]/20 transition-colors disabled:opacity-30 flex items-center gap-1"
            >
              {dataset.training.status === "training"
                ? <Loader2 className="w-3 h-3 animate-spin" />
                : <Play className="w-3 h-3" />}
              {dataset.training.status === "training" ? "Training..." : "Train"}
            </button>
          </div>
        </div>
        <p className="text-[10px] text-[#555] pl-6">{dataset.description}</p>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {/* Stats */}
        {renderStats()}

        {/* Readiness */}
        <div className="p-2.5 rounded bg-[#111] border border-[#1a1a1a]">
          <div className="flex justify-between items-center mb-1.5">
            <span className="text-[10px] text-[#555] uppercase tracking-wider">Readiness</span>
            <span className="text-[10px] font-medium" style={{ color: readiness.color }}>
              {readiness.label}
            </span>
          </div>
          <div className="h-1.5 bg-[#1a1a1a] rounded overflow-hidden mb-1.5">
            <div
              className="h-full rounded transition-all"
              style={{ width: `${readiness.progress}%`, backgroundColor: readiness.color }}
            />
          </div>
          {readiness.hint && (
            <p className="text-[10px] text-[#555] flex items-center gap-1">
              <AlertTriangle className="w-2.5 h-2.5" />
              {readiness.hint}
            </p>
          )}
        </div>

        {/* Training result */}
        {dataset.training.status === "trained" && (
          <div className="p-2.5 rounded bg-[#6EBE46]/5 border border-[#6EBE46]/20">
            <div className="flex items-center gap-2 mb-1">
              <CheckCircle className="w-3.5 h-3.5 text-[#6EBE46]" />
              <span className="text-[10px] text-[#6EBE46] font-medium">Model Trained</span>
              {dataset.training.trainedAt && (
                <span className="text-[10px] text-[#444] flex items-center gap-1">
                  <Clock className="w-2.5 h-2.5" />
                  {new Date(dataset.training.trainedAt).toLocaleDateString()}
                </span>
              )}
            </div>
            {dataset.training.metric && (
              <p className="text-[10px] text-[#888]">
                {dataset.training.metricLabel}: <span className="text-[#6EBE46] font-mono">{dataset.training.metric}</span>
              </p>
            )}
            {dataset.training.modelPath && (
              <p className="text-[10px] text-[#444] font-mono mt-1">{dataset.training.modelPath}</p>
            )}
          </div>
        )}

        {dataset.training.status === "failed" && (
          <div className="p-2.5 rounded bg-red-500/5 border border-red-500/20">
            <div className="flex items-center gap-2">
              <AlertTriangle className="w-3.5 h-3.5 text-red-400" />
              <span className="text-[10px] text-red-400">Training failed — check server logs</span>
            </div>
          </div>
        )}

        {/* Operator capability */}
        <div className="p-2.5 rounded bg-[#0e0e0e] border border-[#151515]">
          <div className="text-[10px] text-[#555] uppercase tracking-wider mb-1.5 flex items-center gap-1">
            <Zap className="w-2.5 h-2.5 text-[#E6AA32]" />
            Operator Capability
          </div>
          <p className="text-[10px] text-[#888]">{dataset.operatorCapability}</p>
        </div>

        {/* Class distribution */}
        {classEntries.length > 0 && (
          <div className="p-3 rounded-lg bg-[#111] border border-[#1a1a1a]">
            <div className="text-[10px] text-[#555] uppercase tracking-wider mb-2">
              {dataset.modelType === "regressor" ? "Target Distribution" : "Class Distribution"}
            </div>
            <div className="space-y-1.5">
              {classEntries.slice(0, 12).map(([cls, count]) => (
                <div key={cls} className="flex items-center gap-2">
                  <span className="text-[10px] text-[#888] w-28 truncate" title={cls}>{cls}</span>
                  <div className="flex-1 h-2 bg-[#1a1a1a] rounded overflow-hidden">
                    <div
                      className="h-full rounded"
                      style={{ width: `${(count / maxCount) * 100}%`, backgroundColor: modelCfg.color }}
                    />
                  </div>
                  <span className="text-[10px] text-[#555] w-6 text-right font-mono">{count}</span>
                </div>
              ))}
              {classEntries.length > 12 && (
                <p className="text-[10px] text-[#444]">+{classEntries.length - 12} more classes</p>
              )}
            </div>
          </div>
        )}

        {/* Examples */}
        <div className="p-3 rounded-lg bg-[#111] border border-[#1a1a1a]">
          <div className="text-[10px] text-[#555] uppercase tracking-wider mb-2">
            Examples ({dataset.examples.length})
          </div>
          {dataset.examples.length === 0 ? (
            <div className="text-center py-4">
              <AlertTriangle className="w-5 h-5 text-[#555] mx-auto mb-1.5" />
              <p className="text-[10px] text-[#555]">No examples yet. Click "Prospect" to start labeling.</p>
            </div>
          ) : (
            <div className="space-y-1.5 max-h-48 overflow-y-auto">
              {dataset.examples.map((ex, i) => (
                <div key={i} className="flex items-center gap-2 p-2 rounded bg-[#0c0c0c] border border-[#151515]">
                  <span className="text-[10px] text-[#6EBE46] truncate flex-1">{ex.sourceLabel}</span>
                  <ChevronRight className="w-3 h-3 text-[#333] flex-shrink-0" />
                  <span className="text-[10px] truncate flex-1" style={{ color: modelCfg.color }}>{ex.targetLabel}</span>
                  {ex.outcome && (
                    <span className={`text-[9px] px-1 rounded ${ex.outcome === "success" ? "text-[#6EBE46]" : ex.outcome === "detected" ? "text-[#E6AA32]" : "text-red-400"}`}>
                      {ex.outcome}
                    </span>
                  )}
                  {ex.numericTarget !== undefined && (
                    <span className="text-[9px] text-[#1ABC9C] font-mono">{ex.numericTarget}m</span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* SPARQL pattern */}
        <div className="p-3 rounded-lg bg-[#0e0e0e] border border-[#151515]">
          <div className="text-[10px] text-[#555] uppercase tracking-wider mb-1.5">Pattern</div>
          <code className="text-[10px] text-[#888] block font-mono">
            (?source a proto:{dataset.sourceType}){"\n"}
            {"  → rel:"}{dataset.edgeType}{"\n"}
            {"    → (?target a proto:"}{dataset.targetType}{")"}
          </code>
          <div className="mt-2 text-[10px] text-[#444]">
            Export: <span className="text-[#666] font-mono">{dataset.exportFormat}</span>
            {dataset.targetField && (
              <> · Target field: <span className="text-[#666] font-mono">{dataset.targetField}</span></>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

// =====================================================
// STAT CARD (small helper)
// =====================================================

const StatCard: React.FC<{ value: string | number; label: string; color: string }> = ({ value, label, color }) => (
  <div className="p-2.5 rounded bg-[#111] border border-[#1a1a1a] text-center">
    <div className="text-sm font-medium" style={{ color }}>{value}</div>
    <div className="text-[10px] text-[#555]">{label}</div>
  </div>
);

export default Prospector;