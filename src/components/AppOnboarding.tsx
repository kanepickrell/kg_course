import { useState, useEffect } from "react";
import {
  Plus, ChevronRight, ChevronDown, Zap, Box,
  GitBranch, Check, AlertTriangle, MessageSquare,
  Code, RefreshCw, ToggleLeft, ToggleRight, ArrowRight,
  Wrench, Lock, Unlock, Activity, Sun, Moon,
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

type Step = "select" | "domain" | "agent" | "tools" | "register";
type Theme = "dark" | "light";

const STEP_ORDER: Step[] = ["select", "domain", "agent", "tools", "register"];
const STEP_LABELS: Record<Step, string> = {
  select: "Identity", domain: "Domain", agent: "Agent",
  tools: "Tools", register: "Register",
};

const MODELS = [
  { id: "gpt-oss:120b",      label: "GPT-OSS 120B",  note: "Meta-reasoning · deep chains" },
  { id: "llama3.3:70b",      label: "Llama 3.3 70B", note: "Strong reasoning · balanced" },
  { id: "gemma3:27b-it-qat", label: "Gemma3 27B",    note: "Fast classification · low cost" },
];

const ICONS = ["⚙️","🧠","🎯","🔬","🛡️","📡","🗺️","⚡","🔗","📊"];

const PERMISSION_OPTIONS = [
  { id: "propose_edge",    label: "Propose edges",        note: "Suggest relationships → goes to review queue" },
  { id: "propose_node",    label: "Propose nodes",        note: "Suggest new artifacts → goes to review queue" },
  { id: "write_episode",   label: "Write episodes",       note: "Commit episode memory directly (NEEM pattern)" },
  { id: "write_execution", label: "Write execution logs", note: "Commit robot/execution logs directly" },
];

// ── Theme tokens ───────────────────────────────────────────────────────────

const THEME: Record<Theme, Record<string, string>> = {
  dark: {
    "--bg-page":              "#0f1117",
    "--bg-surface":           "#161b27",
    "--bg-raised":            "#1e2433",
    "--bg-input":             "#1a1f2e",
    "--border":               "#2a3045",
    "--border-subtle":        "#1e2433",
    "--text-primary":         "#e8eaf0",
    "--text-secondary":       "#8b92a8",
    "--text-muted":           "#505872",
    "--text-code":            "#7dd3fc",
    "--accent-green":         "#6EBE46",
    "--accent-green-bg":      "rgba(110,190,70,0.12)",
    "--accent-green-border":  "rgba(110,190,70,0.3)",
    "--accent-purple":        "#AFA9EC",
    "--accent-purple-bg":     "rgba(175,169,236,0.12)",
    "--accent-purple-border": "rgba(175,169,236,0.3)",
    "--accent-amber":         "#E6AA32",
    "--accent-amber-bg":      "rgba(230,170,50,0.1)",
    "--accent-amber-border":  "rgba(230,170,50,0.3)",
    "--accent-teal":          "#5DCAA5",
    "--accent-teal-bg":       "rgba(93,202,165,0.1)",
    "--shadow":               "0 1px 3px rgba(0,0,0,0.4)",
  },
  light: {
    "--bg-page":              "#f5f6fa",
    "--bg-surface":           "#ffffff",
    "--bg-raised":            "#f0f2f8",
    "--bg-input":             "#ffffff",
    "--border":               "#d4d8e8",
    "--border-subtle":        "#e8eaf2",
    "--text-primary":         "#1a1d2e",
    "--text-secondary":       "#4a5068",
    "--text-muted":           "#8b92a8",
    "--text-code":            "#0369a1",
    "--accent-green":         "#3a8a1f",
    "--accent-green-bg":      "rgba(58,138,31,0.08)",
    "--accent-green-border":  "rgba(58,138,31,0.25)",
    "--accent-purple":        "#5b4fcf",
    "--accent-purple-bg":     "rgba(91,79,207,0.08)",
    "--accent-purple-border": "rgba(91,79,207,0.25)",
    "--accent-amber":         "#92650a",
    "--accent-amber-bg":      "rgba(146,101,10,0.08)",
    "--accent-amber-border":  "rgba(146,101,10,0.25)",
    "--accent-teal":          "#0f766e",
    "--accent-teal-bg":       "rgba(15,118,110,0.08)",
    "--shadow":               "0 1px 3px rgba(0,0,0,0.08)",
  },
};

// ── Helpers ────────────────────────────────────────────────────────────────

function slugify(s: string) {
  return s.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
}

function inferTools(classes: string[], relationships: string[], concepts: OntologyConcept[]): GeneratedTool[] {
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
    });
    tools.push({
      name: `list_${slugify(cls)}s`,
      signature: `list_${slugify(cls)}s(search: str | None = None, limit: int = 25) -> List[${cls}]`,
      description: `List ${cls} artifacts with optional text search.`,
      sparql_template: `SELECT ?name ?key WHERE { ?x a proto:${col} ; proto:name ?name . BIND(STRAFTER(STR(?x), "data/") AS ?key) } LIMIT {limit}`,
      arg_types: { search: "str | None", limit: "int" },
      return_type: `List[${cls}]`,
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
    });
  }
  return tools;
}

// ── Shared style helpers ───────────────────────────────────────────────────

function inputStyle(): React.CSSProperties {
  return {
    width: "100%", padding: "8px 12px", borderRadius: 7,
    border: "1px solid var(--border)", background: "var(--bg-input)",
    color: "var(--text-primary)", fontSize: 13, outline: "none",
    boxSizing: "border-box", transition: "border-color 0.15s",
    fontFamily: "inherit",
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
    <p style={{
      fontSize: 13, color: "var(--text-muted)", margin: "0 0 14px",
      lineHeight: 1.6,
    }}>
      {children}
    </p>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h2 style={{
      margin: "0 0 6px", fontSize: 18, fontWeight: 700,
      color: "var(--text-primary)", letterSpacing: "-0.01em",
    }}>
      {children}
    </h2>
  );
}

// ── Sub-components ─────────────────────────────────────────────────────────

function StepDot({ step, current }: { step: Step; current: Step }) {
  const idx    = STEP_ORDER.indexOf(step);
  const curIdx = STEP_ORDER.indexOf(current);
  const done   = idx < curIdx;
  const active = idx === curIdx;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <div style={{
        width: 24, height: 24, borderRadius: "50%",
        display: "flex", alignItems: "center", justifyContent: "center",
        fontSize: 11, fontWeight: 700, flexShrink: 0,
        background: done ? "var(--accent-green)" : active ? "var(--accent-green-bg)" : "var(--bg-raised)",
        border: done ? "none" : active ? "1.5px solid var(--accent-green)" : "1.5px solid var(--border)",
        color: done ? "#fff" : active ? "var(--accent-green)" : "var(--text-muted)",
        transition: "all 0.2s",
      }}>
        {done ? <Check style={{ width: 12, height: 12 }} /> : idx + 1}
      </div>
      <span style={{
        fontSize: 13, fontWeight: active ? 600 : 400, whiteSpace: "nowrap",
        color: active ? "var(--text-primary)" : done ? "var(--accent-green)" : "var(--text-muted)",
        transition: "color 0.2s",
      }}>
        {STEP_LABELS[step]}
      </span>
    </div>
  );
}

function PluginCard({ plugin, onToggle }: {
  plugin: RegisteredPlugin;
  onToggle: (id: string, active: boolean) => void;
}) {
  return (
    <div style={{
      padding: "12px 14px", borderRadius: 10, marginBottom: 8,
      border: `1px solid ${plugin.active ? "var(--accent-green-border)" : "var(--border)"}`,
      background: plugin.active ? "var(--accent-green-bg)" : "var(--bg-raised)",
    }}>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 10 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{
            width: 38, height: 38, borderRadius: 8, fontSize: 18,
            display: "flex", alignItems: "center", justifyContent: "center",
            border: "1px solid var(--border)", background: "var(--bg-surface)",
          }}>
            {plugin.icon || "⚙️"}
          </div>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 3 }}>
              <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)" }}>{plugin.name}</span>
              <span style={{
                padding: "1px 7px", borderRadius: 4, fontSize: 10, fontWeight: 700,
                fontFamily: "monospace", letterSpacing: "0.05em",
                border: "1px solid var(--accent-green-border)",
                color: plugin.active ? "var(--accent-green)" : "var(--text-muted)",
                background: plugin.active ? "var(--accent-green-bg)" : "var(--bg-raised)",
              }}>
                {plugin.active ? "ACTIVE" : "INACTIVE"}
              </span>
            </div>
            <p style={{ fontSize: 12, color: "var(--text-muted)", margin: "0 0 6px" }}>{plugin.description}</p>
            <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
              {plugin.collections.map(c => (
                <span key={c} style={{
                  padding: "1px 7px", borderRadius: 4, fontSize: 11,
                  background: "var(--accent-purple-bg)", border: "1px solid var(--accent-purple-border)",
                  color: "var(--accent-purple)",
                }}>{c}</span>
              ))}
            </div>
          </div>
        </div>
        <button onClick={() => onToggle(plugin.id, !plugin.active)} style={{
          display: "flex", alignItems: "center", gap: 5, whiteSpace: "nowrap",
          padding: "5px 10px", borderRadius: 6, fontSize: 12, fontWeight: 500, cursor: "pointer",
          background: plugin.active ? "var(--bg-surface)" : "var(--accent-green-bg)",
          border: plugin.active ? "1px solid var(--border)" : "1px solid var(--accent-green-border)",
          color: plugin.active ? "var(--text-muted)" : "var(--accent-green)",
          transition: "all 0.15s",
        }}>
          {plugin.active
            ? <><ToggleRight style={{ width: 14, height: 14 }} /> Deactivate</>
            : <><ToggleLeft  style={{ width: 14, height: 14 }} /> Activate</>
          }
        </button>
      </div>
    </div>
  );
}

function ToolCard({ tool, index }: { tool: GeneratedTool; index: number }) {
  const [open, setOpen] = useState(false);
  return (
    <div style={{
      border: "1px solid var(--border)", borderRadius: 8,
      overflow: "hidden", background: "var(--bg-raised)",
    }}>
      <button onClick={() => setOpen(!open)} style={{
        width: "100%", display: "flex", alignItems: "center", gap: 10,
        padding: "10px 14px", background: "none", border: "none",
        cursor: "pointer", textAlign: "left",
      }}>
        <span style={{ fontSize: 11, color: "var(--accent-green)", fontFamily: "monospace", width: 20, flexShrink: 0 }}>
          {index + 1}.
        </span>
        <Code style={{ width: 14, height: 14, color: "var(--accent-green)", flexShrink: 0 }} />
        <span style={{
          fontSize: 12, color: "var(--text-primary)", fontFamily: "monospace",
          flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
        }}>
          {tool.name}()
        </span>
        <span style={{ fontSize: 11, color: "var(--text-muted)", flexShrink: 0 }}>{tool.return_type}</span>
        <ChevronDown style={{
          width: 14, height: 14, color: "var(--text-muted)", flexShrink: 0,
          transform: open ? "rotate(180deg)" : "none", transition: "transform 0.2s",
        }} />
      </button>
      {open && (
        <div style={{
          borderTop: "1px solid var(--border-subtle)",
          padding: "10px 14px", display: "flex", flexDirection: "column", gap: 8,
        }}>
          <p style={{ fontSize: 13, color: "var(--text-secondary)", margin: 0 }}>{tool.description}</p>
          <pre style={{
            fontSize: 11, color: "var(--accent-teal)", background: "var(--accent-teal-bg)",
            borderRadius: 6, padding: "8px 10px", margin: 0, overflowX: "auto",
            fontFamily: "monospace", lineHeight: 1.5,
          }}>{tool.signature}</pre>
          <div>
            <span style={{ fontSize: 11, color: "var(--text-muted)" }}>SPARQL template</span>
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

// ── Main component ─────────────────────────────────────────────────────────

export default function AppOnboarding() {
  const [theme, setTheme]         = useState<Theme>("dark");
  const [step, setStep]           = useState<Step>("select");
  const [plugins, setPlugins]     = useState<RegisteredPlugin[]>([]);
  const [concepts, setConcepts]   = useState<OntologyConcept[]>([]);
  const [rels, setRels]           = useState<RelationshipType[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving]   = useState(false);
  const [saved, setSaved]         = useState(false);
  const [error, setError]         = useState<string | null>(null);

  const [manifest, setManifest] = useState<Partial<AppManifest>>({
    icon: "⚙️", mode: "action",
    domain_classes: [], domain_relationships: [],
    write_permissions: [], llm_model: "llama3.3:70b",
    system_prompt: "", session_cache_ttl: 300, generated_tools: [],
  });

  const update = (patch: Partial<AppManifest>) => setManifest(p => ({ ...p, ...patch }));

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

  const generatedTools = manifest.domain_classes?.length
    ? inferTools(manifest.domain_classes, manifest.domain_relationships || [], concepts)
    : [];

  const canAdvance = (() => {
    if (step === "select") return !!(manifest.name?.trim() && manifest.id?.trim() && manifest.description?.trim());
    if (step === "domain") return (manifest.domain_classes?.length || 0) > 0;
    if (step === "agent")  return !!(manifest.system_prompt?.trim());
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
      await fetch(`${API_BASE}/api/plugins/register`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...manifest, generated_tools: generatedTools }),
      });
      setSaved(true); refreshPlugins();
    } catch { setSaved(true); }
    finally { setIsSaving(false); }
  };

  const resetWizard = () => {
    setStep("select"); setSaved(false);
    setManifest({
      icon: "⚙️", mode: "action", domain_classes: [], domain_relationships: [],
      write_permissions: [], llm_model: "llama3.3:70b",
      system_prompt: "", session_cache_ttl: 300, generated_tools: [],
    });
  };

  // Apply CSS variable tokens to root div
  const cssVars = Object.fromEntries(Object.entries(THEME[theme]).map(([k, v]) => [k, v]));

  return (
    <div style={{
      ...cssVars,
      height: "100%", display: "flex", flexDirection: "column",
      background: "var(--bg-page)", color: "var(--text-primary)",
      fontFamily: "'Inter', 'Segoe UI', system-ui, sans-serif", fontSize: 13,
    }}>

      {/* ── Header ── */}
      <div style={{
        borderBottom: "1px solid var(--border)", background: "var(--bg-surface)",
        padding: "14px 24px", flexShrink: 0, display: "flex",
        alignItems: "center", justifyContent: "space-between",
        boxShadow: "var(--shadow)",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{
            width: 34, height: 34, borderRadius: 8,
            display: "flex", alignItems: "center", justifyContent: "center",
            background: "var(--accent-purple-bg)", border: "1px solid var(--accent-purple-border)",
          }}>
            <Plus style={{ width: 16, height: 16, color: "var(--accent-purple)" }} />
          </div>
          <div>
            <h1 style={{ margin: 0, fontSize: 15, fontWeight: 700, color: "var(--text-primary)", letterSpacing: "-0.01em" }}>
              App Onboarding
            </h1>
            <p style={{ margin: 0, fontSize: 11, color: "var(--text-muted)", marginTop: 1 }}>
              ProtoGraph · Register New Application
            </p>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <span style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--text-secondary)" }}>
            <Activity style={{ width: 13, height: 13, color: "var(--accent-green)" }} />
            {plugins.filter(p => p.active).length} active
            <span style={{ color: "var(--border)" }}>·</span>
            {plugins.length} registered
          </span>
          <button onClick={() => setTheme(t => t === "dark" ? "light" : "dark")} style={{
            display: "flex", alignItems: "center", gap: 6, padding: "6px 12px",
            borderRadius: 7, border: "1px solid var(--border)", background: "var(--bg-raised)",
            color: "var(--text-secondary)", cursor: "pointer", fontSize: 12, fontWeight: 500,
          }}>
            {theme === "dark"
              ? <><Sun style={{ width: 13, height: 13 }} /> Light mode</>
              : <><Moon style={{ width: 13, height: 13 }} /> Dark mode</>
            }
          </button>
        </div>
      </div>

      <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>

        {/* ── Sidebar ── */}
        <div style={{
          width: 280, borderRight: "1px solid var(--border)",
          display: "flex", flexDirection: "column", flexShrink: 0,
          background: "var(--bg-surface)",
        }}>
          <div style={{
            padding: "10px 16px", borderBottom: "1px solid var(--border-subtle)",
            fontSize: 11, fontWeight: 600, color: "var(--text-muted)",
            textTransform: "uppercase", letterSpacing: "0.06em",
          }}>
            Registered Applications
          </div>
          <div style={{ flex: 1, overflowY: "auto", padding: 10 }}>
            {isLoading ? (
              <div style={{ display: "flex", justifyContent: "center", padding: 32 }}>
                <RefreshCw style={{ width: 18, height: 18, color: "var(--text-muted)", animation: "spin 1s linear infinite" }} />
              </div>
            ) : plugins.length === 0 ? (
              <div style={{ textAlign: "center", padding: 32 }}>
                <Box style={{ width: 24, height: 24, color: "var(--text-muted)", margin: "0 auto 8px" }} />
                <p style={{ fontSize: 13, color: "var(--text-muted)", margin: 0 }}>No apps registered yet</p>
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
              padding: "12px 24px", display: "flex", alignItems: "center",
              gap: 10, flexShrink: 0, flexWrap: "wrap",
            }}>
              {STEP_ORDER.map((s, i) => (
                <div key={s} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <StepDot step={s} current={step} />
                  {i < STEP_ORDER.length - 1 && (
                    <ChevronRight style={{ width: 14, height: 14, color: "var(--border)", flexShrink: 0 }} />
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Content area */}
          <div style={{ flex: 1, overflowY: "auto" }}>
            <div style={{ maxWidth: 660, margin: "0 auto", padding: "32px 28px" }}>

              {/* ── IDENTITY ── */}
              {step === "select" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
                  <div>
                    <SectionTitle>Application identity</SectionTitle>
                    <Helper>Define the application's ID, display name, and purpose. The ID becomes the API path prefix.</Helper>
                  </div>

                  <div>
                    <Label>Icon</Label>
                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                      {ICONS.map(ic => (
                        <button key={ic} onClick={() => update({ icon: ic })} style={{
                          width: 42, height: 42, borderRadius: 8, fontSize: 20,
                          cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center",
                          border: manifest.icon === ic ? "2px solid var(--accent-green)" : "1px solid var(--border)",
                          background: manifest.icon === ic ? "var(--accent-green-bg)" : "var(--bg-raised)",
                          transition: "all 0.15s",
                        }}>{ic}</button>
                      ))}
                    </div>
                  </div>

                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
                    <div>
                      <Label>App ID *</Label>
                      <input
                        value={manifest.id || ""}
                        onChange={e => update({ id: slugify(e.target.value) })}
                        placeholder="lumen_v2"
                        style={{ ...inputStyle(), fontFamily: "monospace" }}
                      />
                      <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 5 }}>
                        POST /api/plugins/<strong style={{ color: "var(--text-secondary)" }}>{manifest.id || "app_id"}</strong>/agent
                      </p>
                    </div>
                    <div>
                      <Label>Display Name *</Label>
                      <input
                        value={manifest.name || ""}
                        onChange={e => update({ name: e.target.value })}
                        placeholder="Lumen Campaign Planner"
                        style={inputStyle()}
                      />
                    </div>
                  </div>

                  <div>
                    <Label>Description *</Label>
                    <textarea
                      value={manifest.description || ""}
                      onChange={e => update({ description: e.target.value })}
                      placeholder="Campaign planning assistant. Helps operators build execution plans by finding modules for required techniques."
                      rows={2}
                      style={{ ...inputStyle(), resize: "none", lineHeight: 1.6 }}
                    />
                  </div>

                  <div>
                    <Label>Interaction Mode</Label>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10 }}>
                      {([
                        { id: "action",         label: "Action-based",  icon: <Zap style={{ width: 16, height: 16 }} />,          note: "Typed events from UI" },
                        { id: "conversational", label: "Conversational", icon: <MessageSquare style={{ width: 16, height: 16 }} />,  note: "Natural language input" },
                        { id: "hybrid",         label: "Hybrid",         icon: <GitBranch style={{ width: 16, height: 16 }} />,     note: "Both modes" },
                      ] as const).map(m => (
                        <button key={m.id} onClick={() => update({ mode: m.id })} style={{
                          padding: 12, borderRadius: 8, textAlign: "left", cursor: "pointer",
                          border: manifest.mode === m.id ? "1.5px solid var(--accent-purple-border)" : "1px solid var(--border)",
                          background: manifest.mode === m.id ? "var(--accent-purple-bg)" : "var(--bg-raised)",
                          transition: "all 0.15s",
                        }}>
                          <div style={{ color: manifest.mode === m.id ? "var(--accent-purple)" : "var(--text-muted)", marginBottom: 7 }}>{m.icon}</div>
                          <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)" }}>{m.label}</div>
                          <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 3 }}>{m.note}</div>
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {/* ── DOMAIN ── */}
              {step === "domain" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
                  <div>
                    <SectionTitle>Domain boundary</SectionTitle>
                    <Helper>Select which OWL classes and relationship types this application can reason about. This determines what tools get generated and what graph data the agent can see.</Helper>
                  </div>

                  <div>
                    <Label>OWL Classes in scope * <span style={{ fontWeight: 400, color: "var(--text-muted)" }}>({manifest.domain_classes?.length || 0} selected)</span></Label>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, maxHeight: 220, overflowY: "auto" }}>
                      {concepts.map(c => {
                        const sel = manifest.domain_classes?.includes(c.label);
                        return (
                          <button key={c.uri} onClick={() => {
                            const cur = manifest.domain_classes || [];
                            update({ domain_classes: sel ? cur.filter(x => x !== c.label) : [...cur, c.label] });
                          }} style={{
                            padding: "9px 12px", borderRadius: 7, textAlign: "left", cursor: "pointer",
                            border: sel ? "1.5px solid var(--accent-green-border)" : "1px solid var(--border)",
                            background: sel ? "var(--accent-green-bg)" : "var(--bg-raised)",
                            transition: "all 0.15s",
                          }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                              <div style={{
                                width: 14, height: 14, borderRadius: 3, flexShrink: 0,
                                border: sel ? "none" : "1.5px solid var(--border)",
                                background: sel ? "var(--accent-green)" : "transparent",
                                display: "flex", alignItems: "center", justifyContent: "center",
                              }}>
                                {sel && <Check style={{ width: 10, height: 10, color: "#fff" }} />}
                              </div>
                              <span style={{ fontSize: 13, fontWeight: 500, color: "var(--text-primary)" }}>{c.label}</span>
                            </div>
                            {c.definition && (
                              <p style={{ fontSize: 11, color: "var(--text-muted)", margin: "4px 0 0 22px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                {c.definition}
                              </p>
                            )}
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  <div>
                    <Label>Relationship types in scope <span style={{ fontWeight: 400, color: "var(--text-muted)" }}>({manifest.domain_relationships?.length || 0} selected)</span></Label>
                    <div style={{ display: "flex", flexDirection: "column", gap: 5, maxHeight: 180, overflowY: "auto" }}>
                      {rels.map(r => {
                        const sel = manifest.domain_relationships?.includes(r.label);
                        return (
                          <button key={r.uri} onClick={() => {
                            const cur = manifest.domain_relationships || [];
                            update({ domain_relationships: sel ? cur.filter(x => x !== r.label) : [...cur, r.label] });
                          }} style={{
                            padding: "9px 12px", borderRadius: 7, textAlign: "left", cursor: "pointer",
                            display: "flex", alignItems: "center", gap: 10,
                            border: sel ? "1.5px solid var(--accent-purple-border)" : "1px solid var(--border)",
                            background: sel ? "var(--accent-purple-bg)" : "var(--bg-raised)",
                            transition: "all 0.15s",
                          }}>
                            <div style={{
                              width: 14, height: 14, borderRadius: 3, flexShrink: 0,
                              border: sel ? "none" : "1.5px solid var(--border)",
                              background: sel ? "var(--accent-purple)" : "transparent",
                              display: "flex", alignItems: "center", justifyContent: "center",
                            }}>
                              {sel && <Check style={{ width: 10, height: 10, color: "#fff" }} />}
                            </div>
                            <span style={{ fontSize: 12, fontWeight: 600, color: "var(--text-primary)", fontFamily: "monospace" }}>{r.label}</span>
                            <span style={{ fontSize: 12, color: "var(--text-muted)", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.definition}</span>
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  <div>
                    <Label>Write permissions</Label>
                    <Helper>By default agents are read-only. All writes go through the proposal queue. Enable only what this application genuinely needs.</Helper>
                    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                      {PERMISSION_OPTIONS.map(p => {
                        const sel = manifest.write_permissions?.includes(p.id);
                        return (
                          <button key={p.id} onClick={() => {
                            const cur = manifest.write_permissions || [];
                            update({ write_permissions: sel ? cur.filter(x => x !== p.id) : [...cur, p.id] });
                          }} style={{
                            padding: "10px 12px", borderRadius: 7, textAlign: "left", cursor: "pointer",
                            display: "flex", alignItems: "center", gap: 10,
                            border: sel ? "1.5px solid var(--accent-amber-border)" : "1px solid var(--border)",
                            background: sel ? "var(--accent-amber-bg)" : "var(--bg-raised)",
                            transition: "all 0.15s",
                          }}>
                            {sel
                              ? <Unlock style={{ width: 14, height: 14, color: "var(--accent-amber)", flexShrink: 0 }} />
                              : <Lock   style={{ width: 14, height: 14, color: "var(--text-muted)",   flexShrink: 0 }} />
                            }
                            <div>
                              <div style={{ fontSize: 13, fontWeight: 500, color: "var(--text-primary)" }}>{p.label}</div>
                              <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>{p.note}</div>
                            </div>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                </div>
              )}

              {/* ── AGENT ── */}
              {step === "agent" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
                  <div>
                    <SectionTitle>Agent configuration</SectionTitle>
                    <Helper>Configure the LLM and write the system prompt. The system prompt is the only part you write by hand — everything else is derived from the ontology.</Helper>
                  </div>

                  <div>
                    <Label>LLM Model</Label>
                    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                      {MODELS.map(m => (
                        <button key={m.id} onClick={() => update({ llm_model: m.id })} style={{
                          padding: "10px 14px", borderRadius: 7, textAlign: "left", cursor: "pointer",
                          display: "flex", alignItems: "center", gap: 12,
                          border: manifest.llm_model === m.id ? "1.5px solid var(--accent-green-border)" : "1px solid var(--border)",
                          background: manifest.llm_model === m.id ? "var(--accent-green-bg)" : "var(--bg-raised)",
                          transition: "all 0.15s",
                        }}>
                          <div style={{
                            width: 14, height: 14, borderRadius: "50%", flexShrink: 0,
                            border: manifest.llm_model === m.id ? "none" : "1.5px solid var(--border)",
                            background: manifest.llm_model === m.id ? "var(--accent-green)" : "transparent",
                          }} />
                          <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)" }}>{m.label}</span>
                          <span style={{ fontSize: 12, color: "var(--text-muted)" }}>{m.note}</span>
                          <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--text-muted)", fontFamily: "monospace" }}>{m.id}</span>
                        </button>
                      ))}
                    </div>
                  </div>

                  <div>
                    <Label>Session cache TTL</Label>
                    <Helper>How long to cache reconnaissance values and schema fragments per session. Reduces repeated graph queries for agents in multi-step tasks.</Helper>
                    <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                      <input
                        type="range" min={60} max={1800} step={60}
                        value={manifest.session_cache_ttl || 300}
                        onChange={e => update({ session_cache_ttl: Number(e.target.value) })}
                        style={{ flex: 1, accentColor: "var(--accent-green)" }}
                      />
                      <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)", minWidth: 44, textAlign: "right" }}>
                        {manifest.session_cache_ttl}s
                      </span>
                    </div>
                  </div>

                  <div>
                    <Label>System Prompt *</Label>
                    <Helper>Define the agent's role, domain context, and behavioral rules. Explicitly state what the agent should and should not do with graph data.</Helper>
                    <div style={{ position: "relative" }}>
                      <textarea
                        value={manifest.system_prompt || ""}
                        onChange={e => update({ system_prompt: e.target.value })}
                        placeholder={`You are ${manifest.name || "an assistant"}, a domain specialist for ProtoGraph.\n\nYou help users with [specific domain task].\n\nYou have access to the knowledge graph via tools. Always use graph data — never invent artifact names or relationships.\n\n[Add domain-specific behavioral rules here]`}
                        rows={9}
                        style={{ ...inputStyle(), resize: "none", lineHeight: 1.7, paddingBottom: 28 }}
                      />
                      <span style={{ position: "absolute", bottom: 8, right: 10, fontSize: 11, color: "var(--text-muted)" }}>
                        {(manifest.system_prompt || "").length} chars
                      </span>
                    </div>
                    <div style={{
                      marginTop: 10, padding: "12px 14px", borderRadius: 8,
                      background: "var(--accent-purple-bg)", border: "1px solid var(--accent-purple-border)",
                    }}>
                      <p style={{ margin: "0 0 8px", fontSize: 12, fontWeight: 600, color: "var(--accent-purple)" }}>Prompt guidelines</p>
                      {[
                        "Start with the agent's role and the application context",
                        "State explicitly: only use artifacts that exist in the graph via tools",
                        "Define what happens when a tool returns no results",
                        "Add domain rules (e.g. 'always check coverage gaps before finalizing a plan')",
                      ].map((tip, i) => (
                        <p key={i} style={{ margin: "4px 0 0", fontSize: 12, color: "var(--text-secondary)", display: "flex", gap: 8, lineHeight: 1.5 }}>
                          <span style={{ color: "var(--accent-purple)", opacity: 0.5, flexShrink: 0 }}>·</span>{tip}
                        </p>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {/* ── TOOLS ── */}
              {step === "tools" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
                  <div>
                    <SectionTitle>Generated tool set</SectionTitle>
                    <Helper>These typed functions are auto-generated from your domain boundary. They become the agent's only interface to the graph — the agent never writes SPARQL directly.</Helper>
                  </div>

                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
                    {[
                      { label: "Tools",       value: generatedTools.length,                   color: "var(--accent-green)" },
                      { label: "Classes",     value: manifest.domain_classes?.length || 0,    color: "var(--accent-purple)" },
                      { label: "Permissions", value: manifest.write_permissions?.length || 0, color: "var(--accent-amber)" },
                    ].map(s => (
                      <div key={s.label} style={{
                        padding: 16, borderRadius: 10, textAlign: "center",
                        border: "1px solid var(--border)", background: "var(--bg-raised)",
                      }}>
                        <div style={{ fontSize: 28, fontWeight: 700, color: s.color }}>{s.value}</div>
                        <div style={{ fontSize: 13, color: "var(--text-muted)", marginTop: 4 }}>{s.label}</div>
                      </div>
                    ))}
                  </div>

                  <div style={{ padding: "12px 14px", borderRadius: 8, border: "1px solid var(--border)", background: "var(--bg-raised)" }}>
                    <p style={{ margin: "0 0 8px", fontSize: 11, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em" }}>Domain scope</p>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                      {manifest.domain_classes?.map(c => (
                        <span key={c} style={{ padding: "3px 10px", borderRadius: 5, fontSize: 12, background: "var(--accent-green-bg)", border: "1px solid var(--accent-green-border)", color: "var(--accent-green)" }}>{c}</span>
                      ))}
                      {manifest.domain_relationships?.map(r => (
                        <span key={r} style={{ padding: "3px 10px", borderRadius: 5, fontSize: 12, fontFamily: "monospace", background: "var(--accent-purple-bg)", border: "1px solid var(--accent-purple-border)", color: "var(--accent-purple)" }}>{r}</span>
                      ))}
                    </div>
                  </div>

                  {generatedTools.length === 0 ? (
                    <div style={{ textAlign: "center", padding: 32 }}>
                      <Wrench style={{ width: 24, height: 24, color: "var(--text-muted)", margin: "0 auto 10px" }} />
                      <p style={{ fontSize: 13, color: "var(--text-muted)", margin: 0 }}>No domain classes selected — go back to Domain to add classes</p>
                    </div>
                  ) : (
                    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                      {generatedTools.map((t, i) => <ToolCard key={t.name} tool={t} index={i} />)}
                    </div>
                  )}

                  <div style={{ padding: "12px 14px", borderRadius: 8, border: "1px solid var(--accent-amber-border)", background: "var(--accent-amber-bg)" }}>
                    <p style={{ margin: "0 0 6px", fontSize: 13, fontWeight: 600, color: "var(--accent-amber)" }}>After registration</p>
                    <p style={{ margin: 0, fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.6 }}>
                      ProtoGraph scaffolds <code style={{ fontFamily: "monospace", color: "var(--accent-amber)" }}>plugins/{manifest.id}/</code> with{" "}
                      <code style={{ fontFamily: "monospace" }}>domain.py</code>, <code style={{ fontFamily: "monospace" }}>agent.py</code>, and{" "}
                      <code style={{ fontFamily: "monospace" }}>tools.py</code> pre-populated from this manifest.
                    </p>
                  </div>
                </div>
              )}

              {/* ── REGISTER ── */}
              {step === "register" && !saved && (
                <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
                  <div>
                    <SectionTitle>Review & register</SectionTitle>
                    <Helper>Review the full manifest before registering the application with ProtoGraph.</Helper>
                  </div>

                  <div style={{ border: "1px solid var(--border)", borderRadius: 10, overflow: "hidden", background: "var(--bg-raised)" }}>
                    {[
                      { label: "App ID",    value: manifest.id,                              mono: true },
                      { label: "Name",      value: manifest.name,                            mono: false },
                      { label: "Mode",      value: manifest.mode,                            mono: true },
                      { label: "LLM",       value: manifest.llm_model,                      mono: true },
                      { label: "Cache TTL", value: `${manifest.session_cache_ttl}s`,         mono: true },
                      { label: "Tools",     value: `${generatedTools.length} auto-generated`, mono: false },
                    ].map((row, i, arr) => (
                      <div key={row.label} style={{
                        display: "flex", alignItems: "center", padding: "11px 16px",
                        borderBottom: i < arr.length - 1 ? "1px solid var(--border-subtle)" : "none",
                      }}>
                        <span style={{ fontSize: 11, fontWeight: 600, color: "var(--text-muted)", width: 90, flexShrink: 0, textTransform: "uppercase", letterSpacing: "0.05em" }}>
                          {row.label}
                        </span>
                        <span style={{ fontSize: 13, color: "var(--text-primary)", fontFamily: row.mono ? "monospace" : "inherit" }}>{row.value}</span>
                      </div>
                    ))}
                    <div style={{ display: "flex", alignItems: "flex-start", padding: "11px 16px", borderTop: "1px solid var(--border-subtle)" }}>
                      <span style={{ fontSize: 11, fontWeight: 600, color: "var(--text-muted)", width: 90, flexShrink: 0, textTransform: "uppercase", letterSpacing: "0.05em", marginTop: 3 }}>Domain</span>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
                        {manifest.domain_classes?.map(c => (
                          <span key={c} style={{ padding: "2px 9px", borderRadius: 4, fontSize: 12, background: "var(--accent-green-bg)", border: "1px solid var(--accent-green-border)", color: "var(--accent-green)" }}>{c}</span>
                        ))}
                      </div>
                    </div>
                    <div style={{ display: "flex", alignItems: "flex-start", padding: "11px 16px", borderTop: "1px solid var(--border-subtle)" }}>
                      <span style={{ fontSize: 11, fontWeight: 600, color: "var(--text-muted)", width: 90, flexShrink: 0, textTransform: "uppercase", letterSpacing: "0.05em", marginTop: 3 }}>Permissions</span>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
                        {(manifest.write_permissions?.length || 0) === 0
                          ? <span style={{ fontSize: 13, color: "var(--text-muted)" }}>Read-only (default)</span>
                          : manifest.write_permissions?.map(p => (
                            <span key={p} style={{ padding: "2px 9px", borderRadius: 4, fontSize: 12, background: "var(--accent-amber-bg)", border: "1px solid var(--accent-amber-border)", color: "var(--accent-amber)" }}>{p}</span>
                          ))
                        }
                      </div>
                    </div>
                  </div>

                  <div>
                    <Label>Manifest JSON</Label>
                    <pre style={{
                      fontSize: 11, color: "var(--text-secondary)", background: "var(--bg-input)",
                      border: "1px solid var(--border)", borderRadius: 8,
                      padding: "12px 14px", margin: 0, overflowY: "auto",
                      maxHeight: 200, fontFamily: "monospace", lineHeight: 1.6,
                    }}>
                      {JSON.stringify({ ...manifest, generated_tools: generatedTools }, null, 2)}
                    </pre>
                  </div>

                  {error && (
                    <div style={{
                      display: "flex", alignItems: "center", gap: 8, padding: "10px 14px",
                      borderRadius: 8, background: "rgba(220,38,38,0.08)", border: "1px solid rgba(220,38,38,0.3)",
                    }}>
                      <AlertTriangle style={{ width: 16, height: 16, color: "#f87171", flexShrink: 0 }} />
                      <span style={{ fontSize: 13, color: "#f87171" }}>{error}</span>
                    </div>
                  )}

                  <button onClick={handleRegister} disabled={isSaving} style={{
                    width: "100%", padding: 13, borderRadius: 8, border: "none",
                    background: "var(--accent-green)", color: "#fff",
                    fontSize: 14, fontWeight: 700, cursor: isSaving ? "not-allowed" : "pointer",
                    opacity: isSaving ? 0.6 : 1, display: "flex",
                    alignItems: "center", justifyContent: "center", gap: 8, transition: "opacity 0.15s",
                  }}>
                    {isSaving
                      ? <><RefreshCw style={{ width: 16, height: 16, animation: "spin 1s linear infinite" }} /> Registering...</>
                      : <><Plus style={{ width: 16, height: 16 }} /> Register Application</>
                    }
                  </button>
                </div>
              )}

              {/* ── SUCCESS ── */}
              {saved && (
                <div style={{ textAlign: "center", padding: "48px 0", display: "flex", flexDirection: "column", alignItems: "center", gap: 18 }}>
                  <div style={{
                    width: 64, height: 64, borderRadius: "50%",
                    background: "var(--accent-green-bg)", border: "2px solid var(--accent-green-border)",
                    display: "flex", alignItems: "center", justifyContent: "center",
                  }}>
                    <Check style={{ width: 28, height: 28, color: "var(--accent-green)" }} />
                  </div>
                  <div>
                    <h2 style={{ margin: "0 0 6px", fontSize: 20, fontWeight: 700, color: "var(--text-primary)" }}>{manifest.name} registered</h2>
                    <p style={{ margin: 0, fontSize: 13, color: "var(--text-muted)" }}>
                      Plugin scaffolded at <code style={{ fontFamily: "monospace", color: "var(--accent-green)" }}>plugins/{manifest.id}/</code>
                    </p>
                  </div>
                  <div style={{
                    padding: "16px 20px", borderRadius: 10, border: "1px solid var(--border)",
                    background: "var(--bg-raised)", textAlign: "left", width: "100%", maxWidth: 440,
                  }}>
                    <p style={{ margin: "0 0 12px", fontSize: 11, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em" }}>Next steps</p>
                    {[
                      `Edit plugins/${manifest.id}/agent.py to refine the system prompt`,
                      `Review plugins/${manifest.id}/tools.py — add domain-specific logic`,
                      `Point your webapp at POST /api/plugins/${manifest.id}/agent`,
                      `Test with a structured action call from the webapp`,
                    ].map((s, i) => (
                      <div key={i} style={{ display: "flex", gap: 10, marginTop: i > 0 ? 8 : 0, fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.5 }}>
                        <span style={{ color: "var(--accent-green)", flexShrink: 0, fontWeight: 700 }}>{i + 1}.</span>
                        <span>{s}</span>
                      </div>
                    ))}
                  </div>
                  <button onClick={resetWizard} style={{
                    padding: "8px 20px", borderRadius: 7, cursor: "pointer", fontSize: 13,
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
              padding: "12px 24px", display: "flex", alignItems: "center",
              justifyContent: "space-between", flexShrink: 0,
            }}>
              <button onClick={() => {
                const idx = STEP_ORDER.indexOf(step);
                if (idx > 0) setStep(STEP_ORDER[idx - 1]);
              }} disabled={step === "select"} style={{
                padding: "7px 14px", borderRadius: 7, fontSize: 13,
                border: "1px solid var(--border)", background: "var(--bg-raised)",
                color: "var(--text-secondary)", cursor: step === "select" ? "not-allowed" : "pointer",
                opacity: step === "select" ? 0.3 : 1, transition: "all 0.15s",
              }}>
                ← Back
              </button>

              <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                {STEP_ORDER.map((s, i) => (
                  <div key={s} style={{
                    height: 6, borderRadius: 3, transition: "all 0.2s",
                    width: s === step ? 18 : 6,
                    background: s === step ? "var(--accent-green)" : i < STEP_ORDER.indexOf(step) ? "var(--accent-green-border)" : "var(--border)",
                  }} />
                ))}
              </div>

              {step !== "register" ? (
                <button onClick={advance} disabled={!canAdvance} style={{
                  padding: "7px 16px", borderRadius: 7, border: "none", fontSize: 13, fontWeight: 600,
                  background: canAdvance ? "var(--accent-green)" : "var(--border)",
                  color: canAdvance ? "#fff" : "var(--text-muted)",
                  cursor: canAdvance ? "pointer" : "not-allowed",
                  display: "flex", alignItems: "center", gap: 6, transition: "all 0.15s",
                }}>
                  Next <ArrowRight style={{ width: 14, height: 14 }} />
                </button>
              ) : <div style={{ width: 80 }} />}
            </div>
          )}

        </div>
      </div>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}