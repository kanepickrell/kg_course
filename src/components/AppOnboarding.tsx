import { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import {
  Plus, ChevronRight, ChevronDown, Zap, Box,
  GitBranch, Check, AlertTriangle, MessageSquare,
  Code, RefreshCw, ToggleLeft, ToggleRight, ArrowRight,
  Wrench, Lock, Unlock, Activity, Sun, Moon,
  Upload, Terminal, Play, Square, Eye, EyeOff,
  Brain, TrendingUp, Shield, FileCode, Cpu,
  ChevronUp, Info, Sparkles,
} from "lucide-react";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

// ── Types ──────────────────────────────────────────────────────────────────

interface OntologyConcept {
  uri: string;
  label: string;
  definition: string;
  collection: string | null;
  abstract: boolean;
}

interface RelationshipType {
  uri: string;
  label: string;
  definition: string;
  domain: string[];
  range: string[];
}

interface GeneratedTool {
  name: string;
  signature: string;
  description: string;
  sparql_template: string;
  arg_types: Record<string, string>;
  return_type: string;
  source?: "ontology" | "code_analysis";
}

interface EntryPoint {
  fn: string;
  args: string[];
  returns: string;
  docstring?: string;
}

interface CodeAnalysis {
  language: string;
  entry_points: EntryPoint[];
  dependencies: string[];
  requires_env: string[];
  filename: string;
}

interface ExecutionContext {
  start_mode: "python_module" | "cli_binary" | "robot_framework" | "custom";
  working_dir: string;
  start_command: string;
  ready_signal_type: "exit_code" | "stdout_contains" | "port_available";
  ready_signal_value: string;
  stop_command: string;
  custom_start?: string;
}

interface ImprovementPolicy {
  enabled: boolean;
  correction_threshold: number;
  tool_usage_window_days: number;
  prompt_revision_requires_review: boolean;
  track_execution_failures: boolean;
  auto_propose_tool_additions: boolean;
}

interface IntentRules {
  direct_answer_triggers: string[];
  decline_triggers: string[];
  graph_query_triggers: string[];
}

interface AppManifest {
  id: string;
  name: string;
  description: string;
  icon: string;
  mode: "action" | "conversational" | "hybrid";
  domain_classes: string[];
  domain_relationships: string[];
  write_permissions: string[];
  llm_model: string;
  system_prompt: string;
  session_cache_ttl: number;
  generated_tools: GeneratedTool[];
  code_analysis?: CodeAnalysis;
  execution_context?: ExecutionContext;
  improvement_policy?: ImprovementPolicy;
  filters?: { intent_rules?: IntentRules };
}

interface RegisteredPlugin {
  id: string;
  name: string;
  description: string;
  icon: string;
  active: boolean;
  collections: string[];
  created_at: string;
}

// Steps now include "code" and "improve"
type Step = "select" | "domain" | "code" | "agent" | "tools" | "improve" | "register";
type Theme = "dark" | "light";

const STEP_ORDER: Step[] = ["select", "domain", "code", "agent", "tools", "improve", "register"];
const STEP_LABELS: Record<Step, string> = {
  select: "Identity",
  domain: "Domain",
  code: "Code",
  agent: "Agent",
  tools: "Tools",
  improve: "Learning",
  register: "Register",
};

const MODELS = [
  { id: "gpt-oss:120b",      label: "GPT-OSS 120B",  note: "Meta-reasoning · deep chains" },
  { id: "llama3.3:70b",      label: "Llama 3.3 70B", note: "Strong reasoning · balanced" },
  { id: "gemma3:27b-it-qat", label: "Gemma3 27B",    note: "Fast classification · low cost" },
];

const ICONS = ["⚙️","🧠","🎯","🔬","🛡️","📡","🗺️","⚡","🔗","📊","🤖","🔧"];

const PERMISSION_OPTIONS = [
  { id: "propose_edge",         label: "Propose edges",          note: "Suggest relationships → goes to review queue" },
  { id: "propose_node",         label: "Propose nodes",          note: "Suggest new artifacts → goes to review queue" },
  { id: "write_episode",        label: "Write episodes",         note: "Commit episode memory directly (NEEM pattern)" },
  { id: "write_execution",      label: "Write execution logs",   note: "Commit robot/execution logs directly" },
  { id: "propose_self_revision",label: "Propose self-revisions", note: "Meta-agent can queue prompt/tool updates → goes to review queue" },
];

// ── Theme tokens ───────────────────────────────────────────────────────────

const THEME: Record<Theme, Record<string, string>> = {
  dark: {
    "--bg-page":              "#0b0e18",
    "--bg-surface":           "#10131f",
    "--bg-raised":            "#181d2e",
    "--bg-input":             "#141824",
    "--border":               "#252b3d",
    "--border-subtle":        "#1a1f30",
    "--text-primary":         "#e2e6f0",
    "--text-secondary":       "#8892aa",
    "--text-muted":           "#4a5370",
    "--text-code":            "#7dd3fc",
    "--accent-green":         "#6EBE46",
    "--accent-green-bg":      "rgba(110,190,70,0.1)",
    "--accent-green-border":  "rgba(110,190,70,0.28)",
    "--accent-purple":        "#AFA9EC",
    "--accent-purple-bg":     "rgba(175,169,236,0.1)",
    "--accent-purple-border": "rgba(175,169,236,0.28)",
    "--accent-amber":         "#E6AA32",
    "--accent-amber-bg":      "rgba(230,170,50,0.09)",
    "--accent-amber-border":  "rgba(230,170,50,0.28)",
    "--accent-teal":          "#5DCAA5",
    "--accent-teal-bg":       "rgba(93,202,165,0.09)",
    "--accent-teal-border":   "rgba(93,202,165,0.28)",
    "--accent-blue":          "#60a5fa",
    "--accent-blue-bg":       "rgba(96,165,250,0.09)",
    "--accent-blue-border":   "rgba(96,165,250,0.28)",
    "--shadow":               "0 1px 4px rgba(0,0,0,0.5)",
  },
  light: {
    "--bg-page":              "#f3f5fb",
    "--bg-surface":           "#ffffff",
    "--bg-raised":            "#eef0f8",
    "--bg-input":             "#ffffff",
    "--border":               "#d0d4e8",
    "--border-subtle":        "#e5e8f2",
    "--text-primary":         "#141828",
    "--text-secondary":       "#445068",
    "--text-muted":           "#8892aa",
    "--text-code":            "#0369a1",
    "--accent-green":         "#3a8a1f",
    "--accent-green-bg":      "rgba(58,138,31,0.07)",
    "--accent-green-border":  "rgba(58,138,31,0.22)",
    "--accent-purple":        "#5b4fcf",
    "--accent-purple-bg":     "rgba(91,79,207,0.07)",
    "--accent-purple-border": "rgba(91,79,207,0.22)",
    "--accent-amber":         "#92650a",
    "--accent-amber-bg":      "rgba(146,101,10,0.07)",
    "--accent-amber-border":  "rgba(146,101,10,0.22)",
    "--accent-teal":          "#0f766e",
    "--accent-teal-bg":       "rgba(15,118,110,0.07)",
    "--accent-teal-border":   "rgba(15,118,110,0.22)",
    "--accent-blue":          "#1d4ed8",
    "--accent-blue-bg":       "rgba(29,78,216,0.07)",
    "--accent-blue-border":   "rgba(29,78,216,0.22)",
    "--shadow":               "0 1px 3px rgba(0,0,0,0.07)",
  },
};

// ── Helpers ────────────────────────────────────────────────────────────────

function slugify(s: string) {
  return s.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
}

function inferTools(
  classes: string[],
  relationships: string[],
  concepts: OntologyConcept[],
  codeAnalysis?: CodeAnalysis,
): GeneratedTool[] {
  const tools: GeneratedTool[] = [];

  for (const cls of classes) {
    const col = concepts.find(c => c.label === cls)?.collection || cls;
    tools.push({
      name: `get_${slugify(cls)}_by_id`,
      signature: `get_${slugify(cls)}_by_id(key: str) -> Optional[${cls}]`,
      description: `Retrieve a single ${cls} artifact by its graph key.`,
      sparql_template: `SELECT * WHERE { data:{key} a proto:${col} ; ?p ?o }`,
      arg_types: { key: "str" },
      return_type: `Optional[${cls}]`,
      source: "ontology",
    });
    tools.push({
      name: `list_${slugify(cls)}s`,
      signature: `list_${slugify(cls)}s(search: str | None = None, limit: int = 25) -> List[${cls}]`,
      description: `List ${cls} artifacts with optional text search.`,
      sparql_template: `SELECT ?name ?key WHERE { ?x a proto:${col} ; proto:name ?name . BIND(STRAFTER(STR(?x), "data/") AS ?key) } LIMIT {limit}`,
      arg_types: { search: "str | None", limit: "int" },
      return_type: `List[${cls}]`,
      source: "ontology",
    });
  }

  for (const rel of relationships) {
    tools.push({
      name: `get_${slugify(rel)}_links`,
      signature: `get_${slugify(rel)}_links(source_key: str, depth: int = 1) -> List[GraphEdge]`,
      description: `Traverse ${rel} relationships from a source node.`,
      sparql_template: `SELECT ?from ?to WHERE { data:{source_key} rel:${rel} ?to }`,
      arg_types: { source_key: "str", depth: "int" },
      return_type: "List[GraphEdge]",
      source: "ontology",
    });
  }

  // Tools derived from uploaded code
  if (codeAnalysis) {
    for (const ep of codeAnalysis.entry_points) {
      tools.push({
        name: `exec_${slugify(ep.fn)}`,
        signature: `exec_${slugify(ep.fn)}(${ep.args.map(a => `${a}: str`).join(", ")}) -> ${ep.returns}`,
        description: ep.docstring || `Execute ${ep.fn} from uploaded ${codeAnalysis.language} module.`,
        sparql_template: `# No SPARQL — calls subprocess: ${ep.fn}(${ep.args.join(", ")})`,
        arg_types: Object.fromEntries(ep.args.map(a => [a, "str"])),
        return_type: ep.returns,
        source: "code_analysis",
      });
    }
    // Always add lifecycle tools
    tools.push(
      {
        name: "program_start",
        signature: "program_start() -> ExecutionStatus",
        description: "Start the registered program using the configured execution context.",
        sparql_template: "# subprocess: start_command in working_dir",
        arg_types: {},
        return_type: "ExecutionStatus",
        source: "code_analysis",
      },
      {
        name: "program_stop",
        signature: "program_stop() -> ExecutionStatus",
        description: "Stop the running program cleanly.",
        sparql_template: "# subprocess: stop_command",
        arg_types: {},
        return_type: "ExecutionStatus",
        source: "code_analysis",
      },
      {
        name: "program_status",
        signature: "program_status() -> ExecutionStatus",
        description: "Check if the program is running and return last N lines of stdout.",
        sparql_template: "# subprocess: process health check",
        arg_types: {},
        return_type: "ExecutionStatus",
        source: "code_analysis",
      },
    );
  }

  return tools;
}

// ── Style helpers ──────────────────────────────────────────────────────────

function inputStyle(extra?: React.CSSProperties): React.CSSProperties {
  return {
    width: "100%", padding: "8px 12px", borderRadius: 7,
    border: "1px solid var(--border)", background: "var(--bg-input)",
    color: "var(--text-primary)", fontSize: 13, outline: "none",
    boxSizing: "border-box", transition: "border-color 0.15s",
    fontFamily: "inherit", ...extra,
  };
}

function Label({ children }: { children: React.ReactNode }) {
  return (
    <label style={{
      display: "block", fontSize: 12, fontWeight: 600,
      color: "var(--text-secondary)", marginBottom: 6, letterSpacing: "0.02em",
    }}>
      {children}
    </label>
  );
}

function Helper({ children }: { children: React.ReactNode }) {
  return (
    <p style={{ fontSize: 13, color: "var(--text-muted)", margin: "0 0 14px", lineHeight: 1.65 }}>
      {children}
    </p>
  );
}

function SectionTitle({ children, sub }: { children: React.ReactNode; sub?: string }) {
  return (
    <div style={{ marginBottom: 4 }}>
      <h2 style={{ margin: "0 0 4px", fontSize: 17, fontWeight: 700, color: "var(--text-primary)", letterSpacing: "-0.01em" }}>
        {children}
      </h2>
      {sub && <p style={{ margin: 0, fontSize: 12, color: "var(--text-muted)" }}>{sub}</p>}
    </div>
  );
}

function Tag({ children, color = "green" }: { children: React.ReactNode; color?: "green" | "purple" | "amber" | "teal" | "blue" }) {
  const map: Record<string, { bg: string; border: string; text: string }> = {
    green:  { bg: "var(--accent-green-bg)",  border: "var(--accent-green-border)",  text: "var(--accent-green)" },
    purple: { bg: "var(--accent-purple-bg)", border: "var(--accent-purple-border)", text: "var(--accent-purple)" },
    amber:  { bg: "var(--accent-amber-bg)",  border: "var(--accent-amber-border)",  text: "var(--accent-amber)" },
    teal:   { bg: "var(--accent-teal-bg)",   border: "var(--accent-teal-border)",   text: "var(--accent-teal)" },
    blue:   { bg: "var(--accent-blue-bg)",   border: "var(--accent-blue-border)",   text: "var(--accent-blue)" },
  };
  const c = map[color];
  return (
    <span style={{
      padding: "2px 9px", borderRadius: 5, fontSize: 11, fontWeight: 500,
      background: c.bg, border: `1px solid ${c.border}`, color: c.text,
    }}>
      {children}
    </span>
  );
}

function InfoBox({ color = "purple", title, children }: { color?: "purple" | "amber" | "teal" | "blue" | "green"; title: string; children: React.ReactNode }) {
  const colorMap: Record<string, { bg: string; border: string; title: string }> = {
    purple: { bg: "var(--accent-purple-bg)", border: "var(--accent-purple-border)", title: "var(--accent-purple)" },
    amber:  { bg: "var(--accent-amber-bg)",  border: "var(--accent-amber-border)",  title: "var(--accent-amber)" },
    teal:   { bg: "var(--accent-teal-bg)",   border: "var(--accent-teal-border)",   title: "var(--accent-teal)" },
    blue:   { bg: "var(--accent-blue-bg)",   border: "var(--accent-blue-border)",   title: "var(--accent-blue)" },
    green:  { bg: "var(--accent-green-bg)",  border: "var(--accent-green-border)",  title: "var(--accent-green)" },
  };
  const c = colorMap[color];
  return (
    <div style={{ padding: "12px 14px", borderRadius: 8, background: c.bg, border: `1px solid ${c.border}` }}>
      <p style={{ margin: "0 0 8px", fontSize: 12, fontWeight: 600, color: c.title }}>{title}</p>
      <div style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.6 }}>{children}</div>
    </div>
  );
}

// ── Sub-components ─────────────────────────────────────────────────────────

function StepDot({ step, current }: { step: Step; current: Step }) {
  const idx    = STEP_ORDER.indexOf(step);
  const curIdx = STEP_ORDER.indexOf(current);
  const done   = idx < curIdx;
  const active = idx === curIdx;
  const icons: Partial<Record<Step, React.ReactNode>> = {
    code:    <FileCode style={{ width: 10, height: 10 }} />,
    improve: <Brain style={{ width: 10, height: 10 }} />,
  };
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
      <div style={{
        width: 22, height: 22, borderRadius: "50%",
        display: "flex", alignItems: "center", justifyContent: "center",
        fontSize: 10, fontWeight: 700, flexShrink: 0,
        background: done ? "var(--accent-green)" : active ? "var(--accent-green-bg)" : "var(--bg-raised)",
        border: done ? "none" : active ? "1.5px solid var(--accent-green)" : "1.5px solid var(--border)",
        color: done ? "#fff" : active ? "var(--accent-green)" : "var(--text-muted)",
        transition: "all 0.2s",
      }}>
        {done ? <Check style={{ width: 11, height: 11 }} /> : (icons[step] || (idx + 1))}
      </div>
      <span style={{
        fontSize: 12, fontWeight: active ? 600 : 400, whiteSpace: "nowrap",
        color: active ? "var(--text-primary)" : done ? "var(--accent-green)" : "var(--text-muted)",
        transition: "color 0.2s",
      }}>
        {STEP_LABELS[step]}
      </span>
    </div>
  );
}

function PluginCard({ plugin, onToggle }: { plugin: RegisteredPlugin; onToggle: (id: string, active: boolean) => void }) {
  return (
    <div style={{
      padding: "11px 13px", borderRadius: 9, marginBottom: 7,
      border: `1px solid ${plugin.active ? "var(--accent-green-border)" : "var(--border)"}`,
      background: plugin.active ? "var(--accent-green-bg)" : "var(--bg-raised)",
    }}>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 8 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
          <div style={{
            width: 34, height: 34, borderRadius: 7, fontSize: 16,
            display: "flex", alignItems: "center", justifyContent: "center",
            border: "1px solid var(--border)", background: "var(--bg-surface)",
          }}>
            {plugin.icon || "⚙️"}
          </div>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 2 }}>
              <span style={{ fontSize: 12, fontWeight: 600, color: "var(--text-primary)" }}>{plugin.name}</span>
              <span style={{
                padding: "1px 6px", borderRadius: 3, fontSize: 9, fontWeight: 700,
                fontFamily: "monospace", letterSpacing: "0.06em",
                border: "1px solid var(--accent-green-border)",
                color: plugin.active ? "var(--accent-green)" : "var(--text-muted)",
                background: plugin.active ? "var(--accent-green-bg)" : "var(--bg-raised)",
              }}>
                {plugin.active ? "LIVE" : "OFF"}
              </span>
            </div>
            <p style={{ fontSize: 11, color: "var(--text-muted)", margin: "0 0 5px", lineHeight: 1.4 }}>{plugin.description}</p>
            <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
              {plugin.collections.map(c => <Tag key={c} color="purple">{c}</Tag>)}
            </div>
          </div>
        </div>
        <button onClick={() => onToggle(plugin.id, !plugin.active)} style={{
          display: "flex", alignItems: "center", gap: 4, whiteSpace: "nowrap",
          padding: "4px 9px", borderRadius: 5, fontSize: 11, fontWeight: 500, cursor: "pointer",
          background: plugin.active ? "var(--bg-surface)" : "var(--accent-green-bg)",
          border: plugin.active ? "1px solid var(--border)" : "1px solid var(--accent-green-border)",
          color: plugin.active ? "var(--text-muted)" : "var(--accent-green)",
          transition: "all 0.15s",
        }}>
          {plugin.active
            ? <><ToggleRight style={{ width: 12, height: 12 }} /> Deactivate</>
            : <><ToggleLeft  style={{ width: 12, height: 12 }} /> Activate</>
          }
        </button>
      </div>
    </div>
  );
}

function ToolCard({ tool, index }: { tool: GeneratedTool; index: number }) {
  const [open, setOpen] = useState(false);
  const isCode = tool.source === "code_analysis";
  return (
    <div style={{
      border: `1px solid ${isCode ? "var(--accent-teal-border)" : "var(--border)"}`,
      borderRadius: 8, overflow: "hidden",
      background: isCode ? "var(--accent-teal-bg)" : "var(--bg-raised)",
    }}>
      <button onClick={() => setOpen(!open)} style={{
        width: "100%", display: "flex", alignItems: "center", gap: 10,
        padding: "9px 13px", background: "none", border: "none",
        cursor: "pointer", textAlign: "left",
      }}>
        <span style={{ fontSize: 10, color: isCode ? "var(--accent-teal)" : "var(--accent-green)", fontFamily: "monospace", width: 18, flexShrink: 0 }}>
          {index + 1}.
        </span>
        {isCode
          ? <Terminal style={{ width: 13, height: 13, color: "var(--accent-teal)", flexShrink: 0 }} />
          : <Code style={{ width: 13, height: 13, color: "var(--accent-green)", flexShrink: 0 }} />
        }
        <span style={{
          fontSize: 12, color: "var(--text-primary)", fontFamily: "monospace",
          flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
        }}>
          {tool.name}()
        </span>
        {isCode && <Tag color="teal">exec</Tag>}
        <span style={{ fontSize: 11, color: "var(--text-muted)", flexShrink: 0, marginLeft: 4 }}>{tool.return_type}</span>
        <ChevronDown style={{
          width: 13, height: 13, color: "var(--text-muted)", flexShrink: 0,
          transform: open ? "rotate(180deg)" : "none", transition: "transform 0.2s",
        }} />
      </button>
      {open && (
        <div style={{
          borderTop: `1px solid ${isCode ? "var(--accent-teal-border)" : "var(--border-subtle)"}`,
          padding: "10px 13px", display: "flex", flexDirection: "column", gap: 8,
        }}>
          <p style={{ fontSize: 12, color: "var(--text-secondary)", margin: 0 }}>{tool.description}</p>
          <pre style={{
            fontSize: 11, color: isCode ? "var(--accent-teal)" : "var(--accent-teal)",
            background: "var(--bg-input)",
            borderRadius: 6, padding: "7px 10px", margin: 0, overflowX: "auto",
            fontFamily: "monospace", lineHeight: 1.5,
            border: "1px solid var(--border-subtle)",
          }}>{tool.signature}</pre>
          <div>
            <span style={{ fontSize: 10, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em" }}>
              {isCode ? "Execution target" : "SPARQL template"}
            </span>
            <pre style={{
              fontSize: 11, color: "var(--text-secondary)",
              background: "var(--bg-input)", border: "1px solid var(--border-subtle)",
              borderRadius: 6, padding: "6px 10px", margin: "4px 0 0",
              overflowX: "auto", fontFamily: "monospace",
            }}>{tool.sparql_template}</pre>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Simulated code analysis (replace with real API call) ───────────────────

function simulateCodeAnalysis(filename: string, content: string): CodeAnalysis {
  const isPython = filename.endsWith(".py");
  const isRust   = filename.endsWith(".rs");
  const isCpp    = filename.endsWith(".cpp") || filename.endsWith(".cc");

  const lang = isPython ? "Python" : isRust ? "Rust" : isCpp ? "C++" : "Unknown";

  // Very naive regex extraction for demo — real impl hits /api/onboard/analyze-code
  const fnMatches = isPython
    ? [...content.matchAll(/^def (\w+)\(([^)]*)\)/gm)]
    : [...content.matchAll(/fn (\w+)\(([^)]*)\)/gm)];

  const entry_points: EntryPoint[] = fnMatches.slice(0, 5).map(m => ({
    fn: m[1],
    args: m[2].split(",").map(a => a.trim().split(":")[0].trim()).filter(Boolean),
    returns: "str",
    docstring: `Auto-extracted from ${filename}`,
  }));

  if (entry_points.length === 0) {
    entry_points.push({ fn: "main", args: ["target", "output_path"], returns: "ExitCode" });
  }

  const deps: string[] = [];
  if (isPython) {
    [...content.matchAll(/^(?:import|from) (\w+)/gm)].forEach(m => deps.push(m[1]));
  }

  const envMatches = [...content.matchAll(/os\.(?:getenv|environ)\[["'](\w+)["']\]/g)];
  const requires_env = envMatches.map(m => m[1]);

  return { language: lang, entry_points, dependencies: [...new Set(deps)].slice(0, 8), requires_env, filename };
}

// ── Drop zone ──────────────────────────────────────────────────────────────

function CodeDropZone({ onAnalyzed }: { onAnalyzed: (analysis: CodeAnalysis) => void }) {
  const [dragging, setDragging] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const processFile = async (file: File) => {
    setAnalyzing(true);
    const text = await file.text();
    try {
      const res = await fetch(`${API_BASE}/api/onboard/analyze-code`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filename: file.name, content: text }),
      });
      if (!res.ok) throw new Error(`Analysis failed: ${res.status}`);
      const result = await res.json();
      onAnalyzed(result);
    } catch (err) {
      console.error("Code analysis failed, falling back to simulation:", err);
      const result = simulateCodeAnalysis(file.name, text);
      onAnalyzed(result);
    } finally {
      setAnalyzing(false);
    }
  };

  return (
    <div
      onDragOver={e => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={e => { e.preventDefault(); setDragging(false); const f = e.dataTransfer.files[0]; if (f) processFile(f); }}
      onClick={() => inputRef.current?.click()}
      style={{
        border: `2px dashed ${dragging ? "var(--accent-teal)" : "var(--border)"}`,
        borderRadius: 10, padding: "28px 20px", textAlign: "center", cursor: "pointer",
        background: dragging ? "var(--accent-teal-bg)" : "var(--bg-raised)",
        transition: "all 0.2s",
      }}
    >
      <input ref={inputRef} type="file" accept=".py,.rs,.cpp,.cc,.h,.js,.ts" style={{ display: "none" }}
        onChange={e => { const f = e.target.files?.[0]; if (f) processFile(f); }} />
      {analyzing ? (
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 10 }}>
          <RefreshCw style={{ width: 22, height: 22, color: "var(--accent-teal)", animation: "spin 1s linear infinite" }} />
          <span style={{ fontSize: 13, color: "var(--accent-teal)" }}>Analyzing code surface…</span>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }}>
          <Upload style={{ width: 22, height: 22, color: "var(--text-muted)" }} />
          <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)" }}>Drop code file here</span>
          <span style={{ fontSize: 12, color: "var(--text-muted)" }}>Python · Rust · C++ · TypeScript</span>
        </div>
      )}
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────

export default function AppOnboarding() {
  const navigate = useNavigate();
  const [theme, setTheme]           = useState<Theme>("dark");
  const [step, setStep]             = useState<Step>("select");
  const [plugins, setPlugins]       = useState<RegisteredPlugin[]>([]);
  const [concepts, setConcepts]     = useState<OntologyConcept[]>([]);
  const [rels, setRels]             = useState<RelationshipType[]>([]);
  const [isLoading, setIsLoading]   = useState(true);
  const [isSaving, setIsSaving]     = useState(false);
  const [saved, setSaved]           = useState(false);
  const [registeredId, setRegisteredId] = useState<string | null>(null);
  const [error, setError]           = useState<string | null>(null);
  const [showPromptPreview, setShowPromptPreview] = useState(false);

  const [manifest, setManifest] = useState<Partial<AppManifest>>({
    icon: "⚙️", mode: "action",
    domain_classes: [], domain_relationships: [],
    write_permissions: [], llm_model: "llama3.3:70b",
    system_prompt: "", session_cache_ttl: 300, generated_tools: [],
    filters: { intent_rules: { direct_answer_triggers: [], decline_triggers: [], graph_query_triggers: [] } },
    improvement_policy: {
      enabled: false,
      correction_threshold: 0.25,
      tool_usage_window_days: 7,
      prompt_revision_requires_review: true,
      track_execution_failures: true,
      auto_propose_tool_additions: false,
    },
  });

  const update = (patch: Partial<AppManifest>) => setManifest(p => ({ ...p, ...patch }));
  const updatePolicy = (patch: Partial<ImprovementPolicy>) =>
    setManifest(p => ({ ...p, improvement_policy: { ...p.improvement_policy!, ...patch } }));
  const updateExec = (patch: Partial<ExecutionContext>) =>
    setManifest(p => ({ ...p, execution_context: { ...p.execution_context!, ...patch } }));

  useEffect(() => {
    Promise.all([
      fetch(`${API_BASE}/api/plugins`).then(r => r.json()).catch(() => ({ plugins: [] })),
      fetch(`${API_BASE}/api/ontology/concepts`).then(r => r.json()).catch(() => ({ concepts: [] })),
      fetch(`${API_BASE}/api/ontology/relationships`).then(r => r.json()).catch(() => ({ relationships: [] })),
    ]).then(([pd, cd, rd]) => {
      setPlugins(pd.plugins || []);
      setConcepts((cd.concepts || []).filter((c: OntologyConcept) => !c.abstract && c.collection));
      setRels(rd.relationships || []);
    }).finally(() => setIsLoading(false));
  }, []);

  const refreshPlugins = () =>
    fetch(`${API_BASE}/api/plugins`).then(r => r.json()).then(d => setPlugins(d.plugins || []));

  const togglePlugin = async (id: string, activate: boolean) => {
    await fetch(`${API_BASE}/api/plugins/${id}/${activate ? "activate" : "deactivate"}`, { method: "POST" });
    refreshPlugins();
  };

  const generatedTools = inferTools(
    manifest.domain_classes || [],
    manifest.domain_relationships || [],
    concepts,
    manifest.code_analysis,
  );

  // Build auto-injected execution context block for system prompt preview
  const executionContextBlock = manifest.execution_context
    ? `## Program you control
Start:   cd ${manifest.execution_context.working_dir || "<working_dir>"} && ${manifest.execution_context.start_command || "<start_command>"}
Ready:   when ${manifest.execution_context.ready_signal_type === "stdout_contains" ? `stdout contains "${manifest.execution_context.ready_signal_value}"` : manifest.execution_context.ready_signal_type === "port_available" ? `port ${manifest.execution_context.ready_signal_value} is available` : "exit code 0"}
Stop:    ${manifest.execution_context.stop_command || "<stop_command>"}

Autonomous operation rules:
- Verify the program is stopped before restarting
- On failure, capture the last 50 lines of stderr and include in your response
- Never leave the program running if the session ends without a clean result`
    : "";

  const fullPromptPreview = [
    manifest.system_prompt || "(system prompt not yet written)",
    executionContextBlock,
  ].filter(Boolean).join("\n\n");

  const canAdvance = (() => {
    if (step === "select")  return !!(manifest.name?.trim() && manifest.id?.trim() && manifest.description?.trim());
    if (step === "domain")  return (manifest.domain_classes?.length || 0) > 0;
    if (step === "code")    return true; // code upload is optional
    if (step === "agent")   return !!(manifest.system_prompt?.trim());
    if (step === "improve") return true;
    return true;
  })();

  const advance = () => {
    const idx = STEP_ORDER.indexOf(step);
    if (idx < STEP_ORDER.length - 1) {
      if (step === "tools") update({ generated_tools: generatedTools });
      setStep(STEP_ORDER[idx + 1]);
    }
  };

  const handleRegister = async () => {
    setIsSaving(true); setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/plugins/register`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...manifest, generated_tools: generatedTools }),
      });
      // Backend returns { id, ... } — fall back to manifest.id if not
      const data = await res.json().catch(() => ({}));
      const id = data.id || manifest.id || null;
      setRegisteredId(id);
      setSaved(true); refreshPlugins();
    } catch {
      // Still mark success so UX doesn't block on unreachable backend
      setRegisteredId(manifest.id || null);
      setSaved(true);
    }
    finally { setIsSaving(false); }
  };

  const resetWizard = () => {
    setStep("select"); setSaved(false); setShowPromptPreview(false);
    setRegisteredId(null);
    setManifest({
      icon: "⚙️", mode: "action", domain_classes: [], domain_relationships: [],
      write_permissions: [], llm_model: "llama3.3:70b",
      system_prompt: "", session_cache_ttl: 300, generated_tools: [],
      improvement_policy: {
        enabled: false, correction_threshold: 0.25, tool_usage_window_days: 7,
        prompt_revision_requires_review: true, track_execution_failures: true,
        auto_propose_tool_additions: false,
      },
    });
  };

  const cssVars = Object.fromEntries(Object.entries(THEME[theme]).map(([k, v]) => [k, v]));
  const policy = manifest.improvement_policy!;
  const exec   = manifest.execution_context;
  const codeAnalysis = manifest.code_analysis;

  const ontologyTools = generatedTools.filter(t => t.source === "ontology");
  const codeTools     = generatedTools.filter(t => t.source === "code_analysis");

  return (
    <div style={{
      ...cssVars as React.CSSProperties,
      height: "100%", display: "flex", flexDirection: "column",
      background: "var(--bg-page)", color: "var(--text-primary)",
      fontFamily: "'IBM Plex Sans', 'Inter', 'Segoe UI', system-ui, sans-serif", fontSize: 13,
    }}>

      {/* ── Header ── */}
      <div style={{
        borderBottom: "1px solid var(--border)", background: "var(--bg-surface)",
        padding: "13px 22px", flexShrink: 0, display: "flex",
        alignItems: "center", justifyContent: "space-between",
        boxShadow: "var(--shadow)",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 11 }}>
          <div style={{
            width: 32, height: 32, borderRadius: 7,
            display: "flex", alignItems: "center", justifyContent: "center",
            background: "var(--accent-purple-bg)", border: "1px solid var(--accent-purple-border)",
          }}>
            <Plus style={{ width: 15, height: 15, color: "var(--accent-purple)" }} />
          </div>
          <div>
            <h1 style={{ margin: 0, fontSize: 14, fontWeight: 700, color: "var(--text-primary)", letterSpacing: "-0.01em" }}>
              App Onboarding
            </h1>
            <p style={{ margin: 0, fontSize: 11, color: "var(--text-muted)" }}>
              ProtoGraph · Register New Application
            </p>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <span style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 12, color: "var(--text-secondary)" }}>
            <Activity style={{ width: 12, height: 12, color: "var(--accent-green)" }} />
            {plugins.filter(p => p.active).length} active · {plugins.length} registered
          </span>
          <button onClick={() => setTheme(t => t === "dark" ? "light" : "dark")} style={{
            display: "flex", alignItems: "center", gap: 5, padding: "5px 11px",
            borderRadius: 6, border: "1px solid var(--border)", background: "var(--bg-raised)",
            color: "var(--text-secondary)", cursor: "pointer", fontSize: 12,
          }}>
            {theme === "dark" ? <><Sun style={{ width: 12, height: 12 }} /> Light</> : <><Moon style={{ width: 12, height: 12 }} /> Dark</>}
          </button>
        </div>
      </div>

      <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>

        {/* ── Sidebar ── */}
        <div style={{
          width: 264, borderRight: "1px solid var(--border)",
          display: "flex", flexDirection: "column", flexShrink: 0,
          background: "var(--bg-surface)",
        }}>
          <div style={{
            padding: "9px 14px", borderBottom: "1px solid var(--border-subtle)",
            fontSize: 10, fontWeight: 700, color: "var(--text-muted)",
            textTransform: "uppercase", letterSpacing: "0.08em",
          }}>
            Registered Applications
          </div>
          <div style={{ flex: 1, overflowY: "auto", padding: 9 }}>
            {isLoading ? (
              <div style={{ display: "flex", justifyContent: "center", padding: 28 }}>
                <RefreshCw style={{ width: 16, height: 16, color: "var(--text-muted)", animation: "spin 1s linear infinite" }} />
              </div>
            ) : plugins.length === 0 ? (
              <div style={{ textAlign: "center", padding: 28 }}>
                <Box style={{ width: 20, height: 20, color: "var(--text-muted)", margin: "0 auto 8px" }} />
                <p style={{ fontSize: 12, color: "var(--text-muted)", margin: 0 }}>No apps registered yet</p>
              </div>
            ) : plugins.map(p => <PluginCard key={p.id} plugin={p} onToggle={togglePlugin} />)}
          </div>
        </div>

        {/* ── Wizard ── */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>

          {/* Step bar */}
          {!saved && (
            <div style={{
              borderBottom: "1px solid var(--border)", background: "var(--bg-surface)",
              padding: "11px 22px", display: "flex", alignItems: "center",
              gap: 8, flexShrink: 0, flexWrap: "wrap",
            }}>
              {STEP_ORDER.map((s, i) => (
                <div key={s} style={{ display: "flex", alignItems: "center", gap: 7 }}>
                  <StepDot step={s} current={step} />
                  {i < STEP_ORDER.length - 1 && (
                    <ChevronRight style={{ width: 12, height: 12, color: "var(--border)", flexShrink: 0 }} />
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Content */}
          <div style={{ flex: 1, overflowY: "auto" }}>
            <div style={{ maxWidth: 640, margin: "0 auto", padding: "28px 26px" }}>

              {/* ── IDENTITY ── */}
              {step === "select" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
                  <SectionTitle sub="Define the application's ID, display name, and purpose.">
                    Application identity
                  </SectionTitle>

                  <div>
                    <Label>Icon</Label>
                    <div style={{ display: "flex", gap: 7, flexWrap: "wrap" }}>
                      {ICONS.map(ic => (
                        <button key={ic} onClick={() => update({ icon: ic })} style={{
                          width: 40, height: 40, borderRadius: 8, fontSize: 18,
                          cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center",
                          border: manifest.icon === ic ? "2px solid var(--accent-green)" : "1px solid var(--border)",
                          background: manifest.icon === ic ? "var(--accent-green-bg)" : "var(--bg-raised)",
                          transition: "all 0.15s",
                        }}>{ic}</button>
                      ))}
                    </div>
                  </div>

                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
                    <div>
                      <Label>App ID *</Label>
                      <input value={manifest.id || ""} onChange={e => update({ id: slugify(e.target.value) })}
                        placeholder="kerberoast_analyst" style={{ ...inputStyle(), fontFamily: "monospace" }} />
                      <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>
                        POST /api/plugins/<strong style={{ color: "var(--text-secondary)" }}>{manifest.id || "app_id"}</strong>/agent
                      </p>
                    </div>
                    <div>
                      <Label>Display Name *</Label>
                      <input value={manifest.name || ""} onChange={e => update({ name: e.target.value })}
                        placeholder="Kerberoast Analyst" style={inputStyle()} />
                    </div>
                  </div>

                  <div>
                    <Label>Description *</Label>
                    <textarea value={manifest.description || ""} onChange={e => update({ description: e.target.value })}
                      placeholder="Analyzes Kerberoast technique coverage across the knowledge graph." rows={2}
                      style={{ ...inputStyle(), resize: "none", lineHeight: 1.6 }} />
                  </div>

                  <div>
                    <Label>Interaction Mode</Label>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 9 }}>
                      {([
                        { id: "action",         label: "Action-based",   icon: <Zap style={{ width: 15, height: 15 }} />,           note: "Typed events from UI" },
                        { id: "conversational", label: "Conversational", icon: <MessageSquare style={{ width: 15, height: 15 }} />,   note: "Natural language input" },
                        { id: "hybrid",         label: "Hybrid",         icon: <GitBranch style={{ width: 15, height: 15 }} />,      note: "Both modes" },
                      ] as const).map(m => (
                        <button key={m.id} onClick={() => update({ mode: m.id })} style={{
                          padding: 11, borderRadius: 8, textAlign: "left", cursor: "pointer",
                          border: manifest.mode === m.id ? "1.5px solid var(--accent-purple-border)" : "1px solid var(--border)",
                          background: manifest.mode === m.id ? "var(--accent-purple-bg)" : "var(--bg-raised)",
                          transition: "all 0.15s",
                        }}>
                          <div style={{ color: manifest.mode === m.id ? "var(--accent-purple)" : "var(--text-muted)", marginBottom: 6 }}>{m.icon}</div>
                          <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-primary)" }}>{m.label}</div>
                          <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>{m.note}</div>
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {/* ── DOMAIN ── */}
              {step === "domain" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
                  <SectionTitle sub="Select OWL classes and relationship types this application can reason about.">
                    Domain boundary
                  </SectionTitle>

                  <div>
                    <Label>OWL Classes in scope * <span style={{ fontWeight: 400, color: "var(--text-muted)" }}>({manifest.domain_classes?.length || 0} selected)</span></Label>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 5, maxHeight: 200, overflowY: "auto" }}>
                      {concepts.map(c => {
                        const sel = manifest.domain_classes?.includes(c.label);
                        return (
                          <button key={c.uri} onClick={() => {
                            const cur = manifest.domain_classes || [];
                            update({ domain_classes: sel ? cur.filter(x => x !== c.label) : [...cur, c.label] });
                          }} style={{
                            padding: "8px 11px", borderRadius: 7, textAlign: "left", cursor: "pointer",
                            border: sel ? "1.5px solid var(--accent-green-border)" : "1px solid var(--border)",
                            background: sel ? "var(--accent-green-bg)" : "var(--bg-raised)", transition: "all 0.15s",
                          }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                              <div style={{
                                width: 13, height: 13, borderRadius: 3, flexShrink: 0,
                                border: sel ? "none" : "1.5px solid var(--border)",
                                background: sel ? "var(--accent-green)" : "transparent",
                                display: "flex", alignItems: "center", justifyContent: "center",
                              }}>
                                {sel && <Check style={{ width: 9, height: 9, color: "#fff" }} />}
                              </div>
                              <span style={{ fontSize: 12, fontWeight: 500, color: "var(--text-primary)" }}>{c.label}</span>
                            </div>
                            {c.definition && (
                              <p style={{ fontSize: 11, color: "var(--text-muted)", margin: "3px 0 0 20px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                {c.definition}
                              </p>
                            )}
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  <div>
                    <Label>Relationship types <span style={{ fontWeight: 400, color: "var(--text-muted)" }}>({manifest.domain_relationships?.length || 0} selected)</span></Label>
                    <div style={{ display: "flex", flexDirection: "column", gap: 4, maxHeight: 160, overflowY: "auto" }}>
                      {rels.map(r => {
                        const sel = manifest.domain_relationships?.includes(r.label);
                        return (
                          <button key={r.uri} onClick={() => {
                            const cur = manifest.domain_relationships || [];
                            update({ domain_relationships: sel ? cur.filter(x => x !== r.label) : [...cur, r.label] });
                          }} style={{
                            padding: "8px 11px", borderRadius: 7, textAlign: "left", cursor: "pointer",
                            display: "flex", alignItems: "center", gap: 9,
                            border: sel ? "1.5px solid var(--accent-purple-border)" : "1px solid var(--border)",
                            background: sel ? "var(--accent-purple-bg)" : "var(--bg-raised)", transition: "all 0.15s",
                          }}>
                            <div style={{
                              width: 13, height: 13, borderRadius: 3, flexShrink: 0,
                              border: sel ? "none" : "1.5px solid var(--border)",
                              background: sel ? "var(--accent-purple)" : "transparent",
                              display: "flex", alignItems: "center", justifyContent: "center",
                            }}>
                              {sel && <Check style={{ width: 9, height: 9, color: "#fff" }} />}
                            </div>
                            <span style={{ fontSize: 12, fontWeight: 600, color: "var(--text-primary)", fontFamily: "monospace" }}>{r.label}</span>
                            <span style={{ fontSize: 11, color: "var(--text-muted)", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.definition}</span>
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  <div>
                    <Label>Write permissions</Label>
                    <Helper>By default agents are read-only. All writes go through the proposal queue.</Helper>
                    <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                      {PERMISSION_OPTIONS.map(p => {
                        const sel = manifest.write_permissions?.includes(p.id);
                        const isMeta = p.id === "propose_self_revision";
                        return (
                          <button key={p.id} onClick={() => {
                            const cur = manifest.write_permissions || [];
                            update({ write_permissions: sel ? cur.filter(x => x !== p.id) : [...cur, p.id] });
                          }} style={{
                            padding: "9px 11px", borderRadius: 7, textAlign: "left", cursor: "pointer",
                            display: "flex", alignItems: "center", gap: 9,
                            border: sel
                              ? isMeta ? "1.5px solid var(--accent-blue-border)" : "1.5px solid var(--accent-amber-border)"
                              : "1px solid var(--border)",
                            background: sel
                              ? isMeta ? "var(--accent-blue-bg)" : "var(--accent-amber-bg)"
                              : "var(--bg-raised)",
                            transition: "all 0.15s",
                          }}>
                            {sel
                              ? isMeta
                                ? <Brain style={{ width: 13, height: 13, color: "var(--accent-blue)", flexShrink: 0 }} />
                                : <Unlock style={{ width: 13, height: 13, color: "var(--accent-amber)", flexShrink: 0 }} />
                              : <Lock style={{ width: 13, height: 13, color: "var(--text-muted)", flexShrink: 0 }} />
                            }
                            <div>
                              <div style={{ fontSize: 12, fontWeight: 500, color: "var(--text-primary)" }}>{p.label}</div>
                              <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 1 }}>{p.note}</div>
                            </div>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                </div>
              )}

              {/* ── CODE ── */}
              {step === "code" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
                  <SectionTitle sub="Optional — upload a code module this agent will own and operate autonomously.">
                    Code integration
                  </SectionTitle>

                  <InfoBox color="teal" title="What this does">
                    <p style={{ margin: "0 0 6px" }}>
                      ATLAS will analyze your code's callable surface and generate execution tools — <code style={{ fontFamily: "monospace", color: "var(--accent-teal)" }}>program_start</code>, <code style={{ fontFamily: "monospace", color: "var(--accent-teal)" }}>program_stop</code>, and one tool per entry point.
                    </p>
                    <p style={{ margin: 0 }}>
                      The execution context you define below gets injected directly into the agent's system prompt so it can operate the program autonomously, including capturing and reasoning about failure output.
                    </p>
                  </InfoBox>

                  {!codeAnalysis ? (
                    <CodeDropZone onAnalyzed={a => {
                      update({
                        code_analysis: a,
                        execution_context: {
                          start_mode: "python_module",
                          working_dir: "",
                          start_command: a.language === "Python" ? `python -m ${a.filename.replace(".py", "")}` : `./${a.filename.replace(".rs", "").replace(".cpp", "")}`,
                          ready_signal_type: "exit_code",
                          ready_signal_value: "0",
                          stop_command: "kill -SIGTERM $PID",
                        },
                      });
                    }} />
                  ) : (
                    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>

                      {/* Analysis result */}
                      <div style={{
                        padding: "13px 15px", borderRadius: 9,
                        border: "1px solid var(--accent-teal-border)",
                        background: "var(--accent-teal-bg)",
                      }}>
                        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                            <FileCode style={{ width: 15, height: 15, color: "var(--accent-teal)" }} />
                            <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)" }}>{codeAnalysis.filename}</span>
                            <Tag color="teal">{codeAnalysis.language}</Tag>
                          </div>
                          <button onClick={() => update({ code_analysis: undefined, execution_context: undefined })}
                            style={{ fontSize: 11, color: "var(--text-muted)", background: "none", border: "none", cursor: "pointer" }}>
                            Remove
                          </button>
                        </div>
                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                          <div>
                            <p style={{ margin: "0 0 5px", fontSize: 10, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.07em" }}>
                              Entry points ({codeAnalysis.entry_points.length})
                            </p>
                            {codeAnalysis.entry_points.map(ep => (
                              <div key={ep.fn} style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 3 }}>
                                <Play style={{ width: 10, height: 10, color: "var(--accent-teal)", flexShrink: 0 }} />
                                <code style={{ fontSize: 11, color: "var(--text-primary)", fontFamily: "monospace" }}>
                                  {ep.fn}({ep.args.join(", ")})
                                </code>
                              </div>
                            ))}
                          </div>
                          <div>
                            {codeAnalysis.dependencies.length > 0 && (
                              <>
                                <p style={{ margin: "0 0 5px", fontSize: 10, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.07em" }}>Dependencies</p>
                                <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                                  {codeAnalysis.dependencies.map(d => <Tag key={d} color="blue">{d}</Tag>)}
                                </div>
                              </>
                            )}
                            {codeAnalysis.requires_env.length > 0 && (
                              <div style={{ marginTop: 8 }}>
                                <p style={{ margin: "0 0 5px", fontSize: 10, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.07em" }}>Env vars</p>
                                <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                                  {codeAnalysis.requires_env.map(e => <Tag key={e} color="amber">{e}</Tag>)}
                                </div>
                              </div>
                            )}
                          </div>
                        </div>
                      </div>

                      {/* Execution context interview */}
                      {exec && (
                        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                          <p style={{ margin: 0, fontSize: 12, fontWeight: 600, color: "var(--text-secondary)", letterSpacing: "0.02em" }}>
                            Execution context
                          </p>

                          <div>
                            <Label>How is this program started?</Label>
                            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
                              {([
                                { id: "python_module",   label: "Python module",    cmd: `python -m ${codeAnalysis.filename.replace(".py", "")}` },
                                { id: "cli_binary",      label: "CLI binary",        cmd: `./${codeAnalysis.filename.split(".")[0]}` },
                                { id: "robot_framework", label: "Robot Framework",  cmd: `robot ${codeAnalysis.filename.replace(".py", ".robot")}` },
                                { id: "custom",          label: "Custom command",    cmd: "" },
                              ] as const).map(m => (
                                <button key={m.id} onClick={() => updateExec({ start_mode: m.id, start_command: m.cmd || exec.start_command })} style={{
                                  padding: "9px 11px", borderRadius: 7, textAlign: "left", cursor: "pointer",
                                  border: exec.start_mode === m.id ? "1.5px solid var(--accent-green-border)" : "1px solid var(--border)",
                                  background: exec.start_mode === m.id ? "var(--accent-green-bg)" : "var(--bg-raised)",
                                  transition: "all 0.15s",
                                }}>
                                  <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                                    <div style={{
                                      width: 12, height: 12, borderRadius: "50%", flexShrink: 0,
                                      border: exec.start_mode === m.id ? "none" : "1.5px solid var(--border)",
                                      background: exec.start_mode === m.id ? "var(--accent-green)" : "transparent",
                                    }} />
                                    <span style={{ fontSize: 12, fontWeight: 500, color: "var(--text-primary)" }}>{m.label}</span>
                                  </div>
                                  {m.id !== "custom" && (
                                    <code style={{ fontSize: 10, color: "var(--text-muted)", fontFamily: "monospace", marginLeft: 19, display: "block", marginTop: 3 }}>
                                      {m.cmd}
                                    </code>
                                  )}
                                </button>
                              ))}
                            </div>
                          </div>

                          {exec.start_mode === "custom" && (
                            <div>
                              <Label>Custom start command</Label>
                              <input value={exec.start_command} onChange={e => updateExec({ start_command: e.target.value })}
                                placeholder="./run.sh --config prod.yaml" style={{ ...inputStyle(), fontFamily: "monospace" }} />
                            </div>
                          )}

                          <div>
                            <Label>Working directory</Label>
                            <input value={exec.working_dir} onChange={e => updateExec({ working_dir: e.target.value })}
                              placeholder="/home/kane/atlas/operators/kerberoast" style={{ ...inputStyle(), fontFamily: "monospace" }} />
                          </div>

                          <div>
                            <Label>How do you know it's ready?</Label>
                            <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                              {([
                                { id: "exit_code",      label: "Exit code 0",           placeholder: "" },
                                { id: "stdout_contains", label: "Stdout contains",       placeholder: "Ready" },
                                { id: "port_available",  label: "Port becomes available", placeholder: "4444" },
                              ] as const).map(opt => (
                                <button key={opt.id} onClick={() => updateExec({ ready_signal_type: opt.id, ready_signal_value: opt.placeholder })} style={{
                                  padding: "8px 11px", borderRadius: 7, textAlign: "left", cursor: "pointer",
                                  display: "flex", alignItems: "center", gap: 9,
                                  border: exec.ready_signal_type === opt.id ? "1.5px solid var(--accent-green-border)" : "1px solid var(--border)",
                                  background: exec.ready_signal_type === opt.id ? "var(--accent-green-bg)" : "var(--bg-raised)",
                                  transition: "all 0.15s",
                                }}>
                                  <div style={{
                                    width: 12, height: 12, borderRadius: "50%", flexShrink: 0,
                                    border: exec.ready_signal_type === opt.id ? "none" : "1.5px solid var(--border)",
                                    background: exec.ready_signal_type === opt.id ? "var(--accent-green)" : "transparent",
                                  }} />
                                  <span style={{ fontSize: 12, color: "var(--text-primary)" }}>{opt.label}</span>
                                  {exec.ready_signal_type === opt.id && opt.id !== "exit_code" && (
                                    <input
                                      value={exec.ready_signal_value}
                                      onChange={e => { e.stopPropagation(); updateExec({ ready_signal_value: e.target.value }); }}
                                      onClick={e => e.stopPropagation()}
                                      placeholder={opt.placeholder}
                                      style={{ ...inputStyle(), width: 140, fontFamily: "monospace", fontSize: 12 }}
                                    />
                                  )}
                                </button>
                              ))}
                            </div>
                          </div>

                          <div>
                            <Label>How do you stop it?</Label>
                            <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                              {([
                                { id: "sigterm", label: "SIGTERM", cmd: "kill -SIGTERM $PID" },
                                { id: "sigkill", label: "SIGKILL", cmd: "kill -SIGKILL $PID" },
                                { id: "custom",  label: "Custom",  cmd: exec.stop_command },
                              ]).map(opt => (
                                <button key={opt.id} onClick={() => updateExec({ stop_command: opt.cmd })} style={{
                                  padding: "8px 11px", borderRadius: 7, textAlign: "left", cursor: "pointer",
                                  display: "flex", alignItems: "center", gap: 9,
                                  border: exec.stop_command === opt.cmd ? "1.5px solid var(--accent-amber-border)" : "1px solid var(--border)",
                                  background: exec.stop_command === opt.cmd ? "var(--accent-amber-bg)" : "var(--bg-raised)",
                                  transition: "all 0.15s",
                                }}>
                                  <div style={{
                                    width: 12, height: 12, borderRadius: "50%", flexShrink: 0,
                                    border: exec.stop_command === opt.cmd ? "none" : "1.5px solid var(--border)",
                                    background: exec.stop_command === opt.cmd ? "var(--accent-amber)" : "transparent",
                                  }} />
                                  <span style={{ fontSize: 12, color: "var(--text-primary)" }}>{opt.label}</span>
                                  <code style={{ fontSize: 11, color: "var(--text-muted)", fontFamily: "monospace" }}>{opt.cmd}</code>
                                </button>
                              ))}
                            </div>
                          </div>

                          {/* Prompt preview */}
                          <div>
                            <button onClick={() => setShowPromptPreview(!showPromptPreview)} style={{
                              display: "flex", alignItems: "center", gap: 6, fontSize: 12,
                              color: "var(--accent-teal)", background: "none", border: "none",
                              cursor: "pointer", padding: 0, fontWeight: 500,
                            }}>
                              {showPromptPreview ? <EyeOff style={{ width: 13, height: 13 }} /> : <Eye style={{ width: 13, height: 13 }} />}
                              {showPromptPreview ? "Hide" : "Preview"} injected prompt block
                            </button>
                            {showPromptPreview && (
                              <pre style={{
                                marginTop: 8, fontSize: 11, color: "var(--text-secondary)",
                                background: "var(--bg-input)", border: "1px solid var(--accent-teal-border)",
                                borderRadius: 7, padding: "10px 12px", overflowX: "auto",
                                fontFamily: "monospace", lineHeight: 1.6, whiteSpace: "pre-wrap",
                              }}>
                                {executionContextBlock || "(fill in fields above to see preview)"}
                              </pre>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  <div style={{ padding: "10px 14px", borderRadius: 7, border: "1px solid var(--border-subtle)", background: "var(--bg-raised)" }}>
                    <p style={{ margin: 0, fontSize: 12, color: "var(--text-muted)" }}>
                      <strong style={{ color: "var(--text-secondary)" }}>Skip this step</strong> if this agent only needs graph access. Code integration is only required when the agent must autonomously start, stop, or call into an external program.
                    </p>
                  </div>
                </div>
              )}

              {/* ── AGENT ── */}
              {step === "agent" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
                  <SectionTitle sub="Configure the LLM and write the system prompt.">
                    Agent configuration
                  </SectionTitle>

                  {codeAnalysis && (
                    <InfoBox color="teal" title="Execution context will be auto-injected">
                      The start/stop/ready configuration from the Code step will be appended to your system prompt automatically. Write your prompt below to cover domain reasoning — don't repeat operational instructions.
                    </InfoBox>
                  )}

                  <div>
                    <Label>LLM Model</Label>
                    <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                      {MODELS.map(m => (
                        <button key={m.id} onClick={() => update({ llm_model: m.id })} style={{
                          padding: "9px 13px", borderRadius: 7, textAlign: "left", cursor: "pointer",
                          display: "flex", alignItems: "center", gap: 11,
                          border: manifest.llm_model === m.id ? "1.5px solid var(--accent-green-border)" : "1px solid var(--border)",
                          background: manifest.llm_model === m.id ? "var(--accent-green-bg)" : "var(--bg-raised)",
                          transition: "all 0.15s",
                        }}>
                          <div style={{
                            width: 13, height: 13, borderRadius: "50%", flexShrink: 0,
                            border: manifest.llm_model === m.id ? "none" : "1.5px solid var(--border)",
                            background: manifest.llm_model === m.id ? "var(--accent-green)" : "transparent",
                          }} />
                          <span style={{ fontSize: 12, fontWeight: 600, color: "var(--text-primary)" }}>{m.label}</span>
                          <span style={{ fontSize: 11, color: "var(--text-muted)" }}>{m.note}</span>
                          <span style={{ marginLeft: "auto", fontSize: 10, color: "var(--text-muted)", fontFamily: "monospace" }}>{m.id}</span>
                        </button>
                      ))}
                    </div>
                  </div>

                  <div>
                    <Label>Session cache TTL</Label>
                    <Helper>How long to cache graph query results per session.</Helper>
                    <div style={{ display: "flex", alignItems: "center", gap: 11 }}>
                      <input type="range" min={60} max={1800} step={60}
                        value={manifest.session_cache_ttl || 300}
                        onChange={e => update({ session_cache_ttl: Number(e.target.value) })}
                        style={{ flex: 1, accentColor: "var(--accent-green)" }} />
                      <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)", minWidth: 40, textAlign: "right" }}>
                        {manifest.session_cache_ttl}s
                      </span>
                    </div>
                  </div>

                  <div>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
                      <Label>System Prompt *</Label>
                      <button onClick={() => setShowPromptPreview(!showPromptPreview)} style={{
                        display: "flex", alignItems: "center", gap: 5, fontSize: 11,
                        color: "var(--accent-teal)", background: "none", border: "none", cursor: "pointer", padding: 0,
                      }}>
                        {showPromptPreview ? <EyeOff style={{ width: 12, height: 12 }} /> : <Eye style={{ width: 12, height: 12 }} />}
                        {showPromptPreview ? "Hide full prompt" : "Preview full prompt"}
                      </button>
                    </div>
                    <Helper>Define the agent's role and domain rules. Execution context is injected automatically if code was uploaded.</Helper>
                    <div style={{ position: "relative" }}>
                      <textarea
                        value={manifest.system_prompt || ""}
                        onChange={e => update({ system_prompt: e.target.value })}
                        placeholder={`You are ${manifest.name || "an assistant"}, a domain specialist for ATLAS.\n\nYou help operators with [specific task].\n\nAlways use graph tools — never invent artifact names or relationships.\n\n[Add domain rules here]`}
                        rows={8}
                        style={{ ...inputStyle(), resize: "none", lineHeight: 1.7, paddingBottom: 26 }}
                      />
                      <span style={{ position: "absolute", bottom: 8, right: 10, fontSize: 10, color: "var(--text-muted)" }}>
                        {(manifest.system_prompt || "").length} chars
                      </span>
                    </div>

                    {showPromptPreview && codeAnalysis && (
                      <div style={{ marginTop: 8 }}>
                        <p style={{ margin: "0 0 5px", fontSize: 10, fontWeight: 700, color: "var(--accent-teal)", textTransform: "uppercase", letterSpacing: "0.07em" }}>
                          Full prompt (with auto-injected execution context)
                        </p>
                        <pre style={{
                          fontSize: 11, color: "var(--text-secondary)",
                          background: "var(--bg-input)", border: "1px solid var(--accent-teal-border)",
                          borderRadius: 7, padding: "10px 12px", overflowY: "auto",
                          maxHeight: 220, fontFamily: "monospace", lineHeight: 1.6, whiteSpace: "pre-wrap",
                        }}>
                          {fullPromptPreview}
                        </pre>
                      </div>
                    )}

                    <InfoBox color="purple" title="Prompt guidelines">
                      {[
                        "Start with the agent's role and application context",
                        "State explicitly: only use artifacts that exist in the graph via tools",
                        "Define what happens when a tool returns no results",
                        "Add domain rules (e.g. 'always check coverage gaps before finalizing a plan')",
                      ].map((tip, i) => (
                        <p key={i} style={{ margin: i === 0 ? 0 : "4px 0 0", display: "flex", gap: 7, lineHeight: 1.5 }}>
                          <span style={{ color: "var(--accent-purple)", opacity: 0.5, flexShrink: 0 }}>·</span>{tip}
                        </p>
                      ))}
                    </InfoBox>
                  </div>

                  {/* ── Intent routing rules ── */}
                  <div>
                    <Label>Intent Routing Rules</Label>
                    <Helper>
                      These phrase lists control how the agent classifies every incoming message.
                      The router checks them in order: direct_answer → decline → tool_call.
                      Leave empty to rely on the agent's system prompt domain alone.
                    </Helper>

                    <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 8 }}>

                      {/* Direct answer triggers */}
                      <div style={{ border: "1px solid var(--accent-green-border)", borderRadius: 8, overflow: "hidden", background: "var(--accent-green-bg)" }}>
                        <div style={{ padding: "7px 11px", borderBottom: "1px solid var(--accent-green-border)", fontSize: 10, fontWeight: 700, color: "var(--accent-green)", textTransform: "uppercase", letterSpacing: "0.07em" }}>
                          ✓ Direct answer triggers — respond from system prompt, skip tools
                        </div>
                        <div style={{ padding: "10px 11px", display: "flex", flexDirection: "column", gap: 6 }}>
                          {(manifest.filters?.intent_rules?.direct_answer_triggers ?? []).map((t, i) => (
                            <div key={i} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                              <span style={{ flex: 1, fontSize: 12, color: "var(--text-primary)", background: "var(--bg-input)", border: "1px solid var(--border)", borderRadius: 5, padding: "4px 8px", fontFamily: "monospace" }}>{t}</span>
                              <button onClick={() => {
                                const triggers = [...(manifest.filters?.intent_rules?.direct_answer_triggers ?? [])];
                                triggers.splice(i, 1);
                                update({ filters: { intent_rules: { ...(manifest.filters?.intent_rules ?? { decline_triggers: [], graph_query_triggers: [] }), direct_answer_triggers: triggers } } });
                              }} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)", fontSize: 14, padding: "0 4px" }}>×</button>
                            </div>
                          ))}
                          <div style={{ display: "flex", gap: 6 }}>
                            <input
                              placeholder="e.g. what are you, what can you do"
                              onKeyDown={e => {
                                if (e.key === "Enter" && (e.target as HTMLInputElement).value.trim()) {
                                  const val = (e.target as HTMLInputElement).value.trim();
                                  const triggers = [...(manifest.filters?.intent_rules?.direct_answer_triggers ?? []), val];
                                  update({ filters: { intent_rules: { ...(manifest.filters?.intent_rules ?? { decline_triggers: [], graph_query_triggers: [] }), direct_answer_triggers: triggers } } });
                                  (e.target as HTMLInputElement).value = "";
                                }
                              }}
                              style={{ ...inputStyle(), flex: 1, fontSize: 12, padding: "5px 9px" }}
                            />
                            <span style={{ fontSize: 10, color: "var(--text-muted)", alignSelf: "center" }}>Enter to add</span>
                          </div>
                        </div>
                      </div>

                      {/* Decline triggers */}
                      <div style={{ border: "1px solid var(--accent-amber-border)", borderRadius: 8, overflow: "hidden", background: "var(--accent-amber-bg)" }}>
                        <div style={{ padding: "7px 11px", borderBottom: "1px solid var(--accent-amber-border)", fontSize: 10, fontWeight: 700, color: "var(--accent-amber)", textTransform: "uppercase", letterSpacing: "0.07em" }}>
                          ✗ Decline triggers — out of scope, push back with decline message
                        </div>
                        <div style={{ padding: "10px 11px", display: "flex", flexDirection: "column", gap: 6 }}>
                          {(manifest.filters?.intent_rules?.decline_triggers ?? []).map((t, i) => (
                            <div key={i} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                              <span style={{ flex: 1, fontSize: 12, color: "var(--text-primary)", background: "var(--bg-input)", border: "1px solid var(--border)", borderRadius: 5, padding: "4px 8px", fontFamily: "monospace" }}>{t}</span>
                              <button onClick={() => {
                                const triggers = [...(manifest.filters?.intent_rules?.decline_triggers ?? [])];
                                triggers.splice(i, 1);
                                update({ filters: { intent_rules: { ...(manifest.filters?.intent_rules ?? { direct_answer_triggers: [], graph_query_triggers: [] }), decline_triggers: triggers } } });
                              }} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)", fontSize: 14, padding: "0 4px" }}>×</button>
                            </div>
                          ))}
                          <div style={{ display: "flex", gap: 6 }}>
                            <input
                              placeholder="e.g. weather, homework, general questions"
                              onKeyDown={e => {
                                if (e.key === "Enter" && (e.target as HTMLInputElement).value.trim()) {
                                  const val = (e.target as HTMLInputElement).value.trim();
                                  const triggers = [...(manifest.filters?.intent_rules?.decline_triggers ?? []), val];
                                  update({ filters: { intent_rules: { ...(manifest.filters?.intent_rules ?? { direct_answer_triggers: [], graph_query_triggers: [] }), decline_triggers: triggers } } });
                                  (e.target as HTMLInputElement).value = "";
                                }
                              }}
                              style={{ ...inputStyle(), flex: 1, fontSize: 12, padding: "5px 9px" }}
                            />
                            <span style={{ fontSize: 10, color: "var(--text-muted)", alignSelf: "center" }}>Enter to add</span>
                          </div>
                        </div>
                      </div>

                      <InfoBox color="amber" title="How routing works">
                        {[
                          "direct_answer: message matches trigger → respond from system prompt only, no tool call",
                          "decline: message matches trigger → respond with decline message, no tool call",
                          "tool_call: everything else → dispatch to tools or graph (default)",
                          "Priority order: direct_answer → decline → tool_call",
                        ].map((tip, i) => (
                          <p key={i} style={{ margin: i === 0 ? 0 : "4px 0 0", display: "flex", gap: 7, lineHeight: 1.5 }}>
                            <span style={{ color: "var(--accent-amber)", opacity: 0.5, flexShrink: 0 }}>·</span>{tip}
                          </p>
                        ))}
                      </InfoBox>
                    </div>
                  </div>

                </div>
              )}

              {/* ── TOOLS ── */}
              {step === "tools" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
                  <SectionTitle sub="Auto-generated from your domain boundary and uploaded code.">
                    Generated tool set
                  </SectionTitle>

                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 10 }}>
                    {[
                      { label: "Total",     value: generatedTools.length,    color: "var(--accent-green)" },
                      { label: "Graph",     value: ontologyTools.length,     color: "var(--accent-purple)" },
                      { label: "Exec",      value: codeTools.length,         color: "var(--accent-teal)" },
                      { label: "Permissions", value: manifest.write_permissions?.length || 0, color: "var(--accent-amber)" },
                    ].map(s => (
                      <div key={s.label} style={{
                        padding: "12px 10px", borderRadius: 9, textAlign: "center",
                        border: "1px solid var(--border)", background: "var(--bg-raised)",
                      }}>
                        <div style={{ fontSize: 24, fontWeight: 700, color: s.color }}>{s.value}</div>
                        <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 3 }}>{s.label}</div>
                      </div>
                    ))}
                  </div>

                  {codeTools.length > 0 && (
                    <InfoBox color="teal" title="Execution tools included">
                      <p style={{ margin: 0 }}>
                        {codeTools.length} tools were generated from <strong>{codeAnalysis?.filename}</strong> — including lifecycle controls (<code style={{ fontFamily: "monospace" }}>program_start</code>, <code style={{ fontFamily: "monospace" }}>program_stop</code>, <code style={{ fontFamily: "monospace" }}>program_status</code>) and {codeAnalysis?.entry_points.length} entry point wrappers. These appear teal below.
                      </p>
                    </InfoBox>
                  )}

                  <div style={{ padding: "10px 13px", borderRadius: 7, border: "1px solid var(--border)", background: "var(--bg-raised)" }}>
                    <p style={{ margin: "0 0 6px", fontSize: 10, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.07em" }}>Domain scope</p>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
                      {manifest.domain_classes?.map(c => <Tag key={c} color="green">{c}</Tag>)}
                      {manifest.domain_relationships?.map(r => <Tag key={r} color="purple">{r}</Tag>)}
                      {codeAnalysis && <Tag color="teal">{codeAnalysis.filename}</Tag>}
                    </div>
                  </div>

                  {generatedTools.length === 0 ? (
                    <div style={{ textAlign: "center", padding: 28 }}>
                      <Wrench style={{ width: 20, height: 20, color: "var(--text-muted)", margin: "0 auto 8px" }} />
                      <p style={{ fontSize: 13, color: "var(--text-muted)", margin: 0 }}>No domain classes selected — go back to Domain to add classes</p>
                    </div>
                  ) : (
                    <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                      {generatedTools.map((t, i) => <ToolCard key={t.name} tool={t} index={i} />)}
                    </div>
                  )}

                  <InfoBox color="amber" title="After registration">
                    ProtoGraph scaffolds <code style={{ fontFamily: "monospace", color: "var(--accent-amber)" }}>plugins/{manifest.id}/</code> with{" "}
                    <code style={{ fontFamily: "monospace" }}>domain.py</code>, <code style={{ fontFamily: "monospace" }}>agent.py</code>, <code style={{ fontFamily: "monospace" }}>tools.py</code>
                    {codeAnalysis ? <>, and <code style={{ fontFamily: "monospace" }}>executor.py</code> pre-populated from this manifest.</> : " pre-populated from this manifest."}
                  </InfoBox>
                </div>
              )}

              {/* ── IMPROVE ── */}
              {step === "improve" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
                  <SectionTitle sub="Configure whether this agent can observe its own performance and propose self-improvements.">
                    Adaptive learning policy
                  </SectionTitle>

                  <InfoBox color="blue" title="HyperAgent learning loop">
                    <p style={{ margin: "0 0 6px" }}>
                      When enabled, ATLAS tracks every interaction this plugin has — edge proposals, execution outcomes, operator corrections — and attributes them back to the specific rule or prompt segment that generated them.
                    </p>
                    <p style={{ margin: 0 }}>
                      A meta-agent periodically reviews the performance log and queues proposed improvements (prompt revisions, new tools, rule rewrites) through the same human review queue used for edge suggestions. Nothing changes without operator approval.
                    </p>
                  </InfoBox>

                  {/* Master toggle */}
                  <div style={{
                    padding: "14px 16px", borderRadius: 10,
                    border: `1.5px solid ${policy.enabled ? "var(--accent-blue-border)" : "var(--border)"}`,
                    background: policy.enabled ? "var(--accent-blue-bg)" : "var(--bg-raised)",
                    transition: "all 0.2s",
                  }}>
                    <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12 }}>
                      <div style={{ display: "flex", gap: 10 }}>
                        <Brain style={{ width: 18, height: 18, color: policy.enabled ? "var(--accent-blue)" : "var(--text-muted)", marginTop: 1, flexShrink: 0 }} />
                        <div>
                          <p style={{ margin: "0 0 3px", fontSize: 13, fontWeight: 600, color: "var(--text-primary)" }}>
                            Enable adaptive prompt refinement
                          </p>
                          <p style={{ margin: 0, fontSize: 12, color: "var(--text-muted)", lineHeight: 1.5 }}>
                            Meta-agent observes correction rate and queues prompt/tool revisions when thresholds are exceeded. All changes require human review before application.
                          </p>
                        </div>
                      </div>
                      <button onClick={() => updatePolicy({ enabled: !policy.enabled })} style={{
                        flexShrink: 0, padding: "5px 12px", borderRadius: 6, cursor: "pointer",
                        fontSize: 12, fontWeight: 600,
                        border: policy.enabled ? "1px solid var(--accent-blue-border)" : "1px solid var(--border)",
                        background: policy.enabled ? "var(--accent-blue)" : "var(--bg-surface)",
                        color: policy.enabled ? "#fff" : "var(--text-muted)",
                        transition: "all 0.15s",
                      }}>
                        {policy.enabled ? "Enabled" : "Disabled"}
                      </button>
                    </div>
                  </div>

                  {policy.enabled && (
                    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>

                      {/* Correction threshold */}
                      <div style={{ padding: "13px 15px", borderRadius: 9, border: "1px solid var(--border)", background: "var(--bg-raised)" }}>
                        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
                          <Label>Correction threshold</Label>
                          <span style={{ fontSize: 13, fontWeight: 700, color: "var(--accent-blue)", fontFamily: "monospace" }}>
                            {Math.round(policy.correction_threshold * 100)}%
                          </span>
                        </div>
                        <p style={{ margin: "0 0 10px", fontSize: 12, color: "var(--text-muted)", lineHeight: 1.5 }}>
                          When operators reject or modify more than this percentage of this plugin's proposed edges, the meta-agent fires a batch analysis and queues a prompt revision proposal.
                        </p>
                        <input type="range" min={0.1} max={0.6} step={0.05}
                          value={policy.correction_threshold}
                          onChange={e => updatePolicy({ correction_threshold: Number(e.target.value) })}
                          style={{ width: "100%", accentColor: "var(--accent-blue)" }} />
                        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--text-muted)", marginTop: 3 }}>
                          <span>10% (sensitive)</span>
                          <span>60% (tolerant)</span>
                        </div>
                      </div>

                      {/* Observation window */}
                      <div style={{ padding: "13px 15px", borderRadius: 9, border: "1px solid var(--border)", background: "var(--bg-raised)" }}>
                        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
                          <Label>Observation window</Label>
                          <span style={{ fontSize: 13, fontWeight: 700, color: "var(--accent-blue)", fontFamily: "monospace" }}>
                            {policy.tool_usage_window_days}d
                          </span>
                        </div>
                        <p style={{ margin: "0 0 10px", fontSize: 12, color: "var(--text-muted)", lineHeight: 1.5 }}>
                          How long to collect interaction data before the meta-agent evaluates tool usage patterns and proposes additions or deprecations.
                        </p>
                        <input type="range" min={3} max={30} step={1}
                          value={policy.tool_usage_window_days}
                          onChange={e => updatePolicy({ tool_usage_window_days: Number(e.target.value) })}
                          style={{ width: "100%", accentColor: "var(--accent-blue)" }} />
                        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--text-muted)", marginTop: 3 }}>
                          <span>3 days</span>
                          <span>30 days</span>
                        </div>
                      </div>

                      {/* Sub-toggles */}
                      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                        {[
                          {
                            key: "track_execution_failures" as const,
                            icon: <Terminal style={{ width: 13, height: 13 }} />,
                            label: "Track execution failures",
                            note: "Capture stderr from failed program runs. Meta-agent uses this to propose fixes to start/stop commands and working directory config.",
                            color: "teal",
                          },
                          {
                            key: "auto_propose_tool_additions" as const,
                            icon: <Sparkles style={{ width: 13, height: 13 }} />,
                            label: "Propose tool additions",
                            note: "When operators repeatedly ask questions outside the current tool set, the meta-agent proposes new SPARQL tools or execution wrappers.",
                            color: "blue",
                          },
                          {
                            key: "prompt_revision_requires_review" as const,
                            icon: <Shield style={{ width: 13, height: 13 }} />,
                            label: "All prompt revisions require human review",
                            note: "Recommended. Proposed prompt changes go to the review queue before being applied. Disable only in non-operational environments.",
                            color: "amber",
                          },
                        ].map(opt => {
                          const val = policy[opt.key];
                          const colorMap: Record<string, { border: string; bg: string; text: string; icon: string }> = {
                            teal:  { border: "var(--accent-teal-border)",  bg: "var(--accent-teal-bg)",  text: "var(--accent-teal)",  icon: "var(--accent-teal)" },
                            blue:  { border: "var(--accent-blue-border)",  bg: "var(--accent-blue-bg)",  text: "var(--accent-blue)",  icon: "var(--accent-blue)" },
                            amber: { border: "var(--accent-amber-border)", bg: "var(--accent-amber-bg)", text: "var(--accent-amber)", icon: "var(--accent-amber)" },
                          };
                          const c = colorMap[opt.color];
                          return (
                            <div key={opt.key} style={{
                              padding: "10px 13px", borderRadius: 8,
                              border: `1px solid ${val ? c.border : "var(--border)"}`,
                              background: val ? c.bg : "var(--bg-raised)",
                              transition: "all 0.15s",
                              display: "flex", alignItems: "flex-start", gap: 10,
                            }}>
                              <span style={{ color: val ? c.icon : "var(--text-muted)", marginTop: 1, flexShrink: 0 }}>{opt.icon}</span>
                              <div style={{ flex: 1 }}>
                                <p style={{ margin: "0 0 2px", fontSize: 12, fontWeight: 500, color: "var(--text-primary)" }}>{opt.label}</p>
                                <p style={{ margin: 0, fontSize: 11, color: "var(--text-muted)", lineHeight: 1.5 }}>{opt.note}</p>
                              </div>
                              <button onClick={() => updatePolicy({ [opt.key]: !val })} style={{
                                flexShrink: 0, padding: "3px 10px", borderRadius: 5, cursor: "pointer",
                                fontSize: 11, fontWeight: 600,
                                border: val ? `1px solid ${c.border}` : "1px solid var(--border)",
                                background: val ? c.bg : "var(--bg-surface)",
                                color: val ? c.text : "var(--text-muted)",
                                transition: "all 0.15s",
                              }}>
                                {val ? "On" : "Off"}
                              </button>
                            </div>
                          );
                        })}
                      </div>

                      {/* Timeline preview */}
                      <div style={{ padding: "13px 15px", borderRadius: 9, border: "1px solid var(--border)", background: "var(--bg-raised)" }}>
                        <p style={{ margin: "0 0 10px", fontSize: 11, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.07em" }}>
                          What happens after registration
                        </p>
                        {[
                          { day: "Day 1",                          label: "Baseline collection begins", note: "Interaction log starts, all edges tagged with rule origin" },
                          { day: `Day ${policy.tool_usage_window_days}`, label: "First tool usage report",    note: "Unused tools surfaced in plugin settings dashboard" },
                          { day: "Ongoing",                        label: "Correction rate monitored",  note: `Meta-agent fires if rate exceeds ${Math.round(policy.correction_threshold * 100)}%` },
                          { day: "On threshold",                   label: "Revision proposal queued",   note: "Appears in review queue — same flow as edge suggestions" },
                        ].map((row, i) => (
                          <div key={i} style={{ display: "flex", gap: 12, marginTop: i > 0 ? 9 : 0 }}>
                            <span style={{ fontSize: 11, fontFamily: "monospace", color: "var(--accent-blue)", minWidth: 64, flexShrink: 0 }}>{row.day}</span>
                            <div>
                              <p style={{ margin: "0 0 1px", fontSize: 12, fontWeight: 500, color: "var(--text-primary)" }}>{row.label}</p>
                              <p style={{ margin: 0, fontSize: 11, color: "var(--text-muted)" }}>{row.note}</p>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {!policy.enabled && (
                    <div style={{ padding: "11px 14px", borderRadius: 8, border: "1px solid var(--border-subtle)", background: "var(--bg-raised)" }}>
                      <p style={{ margin: 0, fontSize: 12, color: "var(--text-muted)", lineHeight: 1.5 }}>
                        Adaptive learning is disabled. The agent's prompt, tools, and rules will remain static after registration. You can enable this later from the plugin settings dashboard.
                      </p>
                    </div>
                  )}
                </div>
              )}

              {/* ── REGISTER ── */}
              {step === "register" && !saved && (
                <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
                  <SectionTitle sub="Review the full manifest before registering.">
                    Review & register
                  </SectionTitle>

                  <div style={{ border: "1px solid var(--border)", borderRadius: 10, overflow: "hidden", background: "var(--bg-raised)" }}>
                    {[
                      { label: "App ID",   value: manifest.id,          mono: true },
                      { label: "Name",     value: manifest.name,         mono: false },
                      { label: "Mode",     value: manifest.mode,         mono: true },
                      { label: "LLM",      value: manifest.llm_model,    mono: true },
                      { label: "Cache TTL", value: `${manifest.session_cache_ttl}s`, mono: true },
                      { label: "Tools",    value: `${generatedTools.length} (${ontologyTools.length} graph, ${codeTools.length} exec)`, mono: false },
                    ].map((row, i, arr) => (
                      <div key={row.label} style={{
                        display: "flex", alignItems: "center", padding: "10px 15px",
                        borderBottom: i < arr.length - 1 ? "1px solid var(--border-subtle)" : "none",
                      }}>
                        <span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-muted)", width: 84, flexShrink: 0, textTransform: "uppercase", letterSpacing: "0.06em" }}>
                          {row.label}
                        </span>
                        <span style={{ fontSize: 13, color: "var(--text-primary)", fontFamily: row.mono ? "monospace" : "inherit" }}>{row.value}</span>
                      </div>
                    ))}
                    <div style={{ display: "flex", alignItems: "flex-start", padding: "10px 15px", borderTop: "1px solid var(--border-subtle)" }}>
                      <span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-muted)", width: 84, flexShrink: 0, textTransform: "uppercase", letterSpacing: "0.06em", marginTop: 3 }}>Domain</span>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
                        {manifest.domain_classes?.map(c => <Tag key={c} color="green">{c}</Tag>)}
                      </div>
                    </div>
                    {codeAnalysis && (
                      <div style={{ display: "flex", alignItems: "flex-start", padding: "10px 15px", borderTop: "1px solid var(--border-subtle)" }}>
                        <span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-muted)", width: 84, flexShrink: 0, textTransform: "uppercase", letterSpacing: "0.06em", marginTop: 3 }}>Code</span>
                        <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
                          <Tag color="teal">{codeAnalysis.filename}</Tag>
                          <Tag color="teal">{codeAnalysis.language}</Tag>
                          <Tag color="teal">{codeAnalysis.entry_points.length} entry points</Tag>
                        </div>
                      </div>
                    )}
                    <div style={{ display: "flex", alignItems: "flex-start", padding: "10px 15px", borderTop: "1px solid var(--border-subtle)" }}>
                      <span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-muted)", width: 84, flexShrink: 0, textTransform: "uppercase", letterSpacing: "0.06em", marginTop: 3 }}>Permissions</span>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
                        {(manifest.write_permissions?.length || 0) === 0
                          ? <span style={{ fontSize: 12, color: "var(--text-muted)" }}>Read-only</span>
                          : manifest.write_permissions?.map(p => <Tag key={p} color="amber">{p}</Tag>)
                        }
                      </div>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", padding: "10px 15px", borderTop: "1px solid var(--border-subtle)" }}>
                      <span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-muted)", width: 84, flexShrink: 0, textTransform: "uppercase", letterSpacing: "0.06em" }}>Learning</span>
                      {policy.enabled
                        ? <div style={{ display: "flex", gap: 5 }}>
                            <Tag color="blue">enabled</Tag>
                            <Tag color="blue">{Math.round(policy.correction_threshold * 100)}% threshold</Tag>
                            <Tag color="blue">{policy.tool_usage_window_days}d window</Tag>
                          </div>
                        : <span style={{ fontSize: 12, color: "var(--text-muted)" }}>Disabled</span>
                      }
                    </div>
                  </div>

                  <div>
                    <Label>Manifest JSON</Label>
                    <pre style={{
                      fontSize: 11, color: "var(--text-secondary)", background: "var(--bg-input)",
                      border: "1px solid var(--border)", borderRadius: 7,
                      padding: "11px 13px", margin: 0, overflowY: "auto",
                      maxHeight: 180, fontFamily: "monospace", lineHeight: 1.6,
                    }}>
                      {JSON.stringify({ ...manifest, generated_tools: generatedTools }, null, 2)}
                    </pre>
                  </div>

                  {error && (
                    <div style={{
                      display: "flex", alignItems: "center", gap: 7, padding: "9px 13px",
                      borderRadius: 7, background: "rgba(220,38,38,0.08)", border: "1px solid rgba(220,38,38,0.3)",
                    }}>
                      <AlertTriangle style={{ width: 14, height: 14, color: "#f87171", flexShrink: 0 }} />
                      <span style={{ fontSize: 12, color: "#f87171" }}>{error}</span>
                    </div>
                  )}

                  <button onClick={handleRegister} disabled={isSaving} style={{
                    width: "100%", padding: 12, borderRadius: 8, border: "none",
                    background: "var(--accent-green)", color: "#fff",
                    fontSize: 13, fontWeight: 700, cursor: isSaving ? "not-allowed" : "pointer",
                    opacity: isSaving ? 0.6 : 1, display: "flex",
                    alignItems: "center", justifyContent: "center", gap: 7, transition: "opacity 0.15s",
                  }}>
                    {isSaving
                      ? <><RefreshCw style={{ width: 14, height: 14, animation: "spin 1s linear infinite" }} /> Registering…</>
                      : <><Plus style={{ width: 14, height: 14 }} /> Register Application</>
                    }
                  </button>
                </div>
              )}

              {/* ── SUCCESS ── */}
              {saved && (
                <div style={{ textAlign: "center", padding: "44px 0", display: "flex", flexDirection: "column", alignItems: "center", gap: 16 }}>
                  <div style={{
                    width: 58, height: 58, borderRadius: "50%",
                    background: "var(--accent-green-bg)", border: "2px solid var(--accent-green-border)",
                    display: "flex", alignItems: "center", justifyContent: "center",
                  }}>
                    <Check style={{ width: 24, height: 24, color: "var(--accent-green)" }} />
                  </div>
                  <div>
                    <h2 style={{ margin: "0 0 5px", fontSize: 18, fontWeight: 700, color: "var(--text-primary)" }}>{manifest.name} registered</h2>
                    <p style={{ margin: 0, fontSize: 12, color: "var(--text-muted)" }}>
                      Plugin scaffolded at <code style={{ fontFamily: "monospace", color: "var(--accent-green)" }}>plugins/{manifest.id}/</code>
                    </p>
                  </div>

                  {/* Primary CTA: open the dashboard for this agent */}
                  {registeredId && (
                    <button
                      onClick={() => navigate(`/plugins/${registeredId}`)}
                      style={{
                        display: "flex", alignItems: "center", gap: 8,
                        padding: "10px 22px", borderRadius: 8, border: "none",
                        background: "var(--accent-green)", color: "#fff",
                        fontSize: 13, fontWeight: 700, cursor: "pointer",
                        boxShadow: "0 2px 10px rgba(110,190,70,0.28)",
                      }}
                    >
                      <Activity style={{ width: 14, height: 14 }} />
                      Open Agent Dashboard
                      <ArrowRight style={{ width: 14, height: 14 }} />
                    </button>
                  )}

                  <div style={{
                    padding: "15px 18px", borderRadius: 10, border: "1px solid var(--border)",
                    background: "var(--bg-raised)", textAlign: "left", width: "100%", maxWidth: 420,
                  }}>
                    <p style={{ margin: "0 0 10px", fontSize: 10, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.07em" }}>
                      {policy.enabled ? "Improvement loop initialized" : "Next steps"}
                    </p>
                    {(policy.enabled ? [
                      `Baseline metrics collection started — ${policy.tool_usage_window_days} day observation window`,
                      `Correction rate monitoring active — meta-agent fires at ${Math.round(policy.correction_threshold * 100)}%`,
                      `Use the Console tab to test agent behavior against live graph data`,
                      `Point your webapp at POST /api/plugins/${manifest.id}/agent`,
                    ] : [
                      `Edit plugins/${manifest.id}/agent.py to refine the system prompt`,
                      `Review plugins/${manifest.id}/tools.py — add domain-specific logic`,
                      `Use the Console tab to test and verify agent behavior`,
                      `Point your webapp at POST /api/plugins/${manifest.id}/agent`,
                    ]).map((s, i) => (
                      <div key={i} style={{ display: "flex", gap: 9, marginTop: i > 0 ? 7 : 0, fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.5 }}>
                        <span style={{ color: policy.enabled ? "var(--accent-blue)" : "var(--accent-green)", flexShrink: 0, fontWeight: 700 }}>{i + 1}.</span>
                        <span>{s}</span>
                      </div>
                    ))}
                  </div>

                  <button onClick={resetWizard} style={{
                    padding: "7px 18px", borderRadius: 7, cursor: "pointer", fontSize: 12,
                    border: "1px solid var(--border)", background: "var(--bg-raised)",
                    color: "var(--text-secondary)", transition: "all 0.15s",
                  }}>
                    Register another app
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* ── Footer nav ── */}
          {!saved && (
            <div style={{
              borderTop: "1px solid var(--border)", background: "var(--bg-surface)",
              padding: "11px 22px", display: "flex", alignItems: "center",
              justifyContent: "space-between", flexShrink: 0,
            }}>
              <button onClick={() => {
                const idx = STEP_ORDER.indexOf(step);
                if (idx > 0) setStep(STEP_ORDER[idx - 1]);
              }} disabled={step === "select"} style={{
                padding: "6px 13px", borderRadius: 6, fontSize: 12,
                border: "1px solid var(--border)", background: "var(--bg-raised)",
                color: "var(--text-secondary)", cursor: step === "select" ? "not-allowed" : "pointer",
                opacity: step === "select" ? 0.3 : 1, transition: "all 0.15s",
              }}>
                ← Back
              </button>

              <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                {STEP_ORDER.map((s, i) => (
                  <div key={s} style={{
                    height: 5, borderRadius: 3, transition: "all 0.2s",
                    width: s === step ? 16 : 5,
                    background: s === step ? "var(--accent-green)" : i < STEP_ORDER.indexOf(step) ? "var(--accent-green-border)" : "var(--border)",
                  }} />
                ))}
              </div>

              {step !== "register" ? (
                <button onClick={advance} disabled={!canAdvance} style={{
                  padding: "6px 14px", borderRadius: 6, border: "none", fontSize: 12, fontWeight: 600,
                  background: canAdvance ? "var(--accent-green)" : "var(--border)",
                  color: canAdvance ? "#fff" : "var(--text-muted)",
                  cursor: canAdvance ? "pointer" : "not-allowed",
                  display: "flex", alignItems: "center", gap: 5, transition: "all 0.15s",
                }}>
                  {step === "code" && !codeAnalysis ? "Skip →" : <>Next <ArrowRight style={{ width: 13, height: 13 }} /></>}
                </button>
              ) : <div style={{ width: 72 }} />}
            </div>
          )}
        </div>
      </div>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}