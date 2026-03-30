import { useState, useEffect, useCallback, useRef } from "react";
import {
  Activity, AlertTriangle, ArrowLeft, ArrowRight,
  Brain, Check, ChevronDown,
  Code, FileCode, GitBranch, History,
  Play, RefreshCw, Sparkles, Square,
  Terminal, TrendingDown, TrendingUp, Wrench,
  X, Zap, ToggleLeft, ToggleRight,
  MessageSquare, Loader2, Send,
  AlertCircle, Plus, Trash2, Radar, ThumbsUp, ThumbsDown, Sun, Moon,
} from "lucide-react";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

// ── Types ──────────────────────────────────────────────────────────────────

type Tab = "overview" | "performance" | "proposals" | "execution" | "history" | "console";

interface IntentRules {
  direct_answer_triggers: string[];
  decline_triggers: string[];
  graph_query_triggers: string[];
}

interface Plugin {
  id: string;
  name: string;
  description: string;
  icon: string;
  active: boolean;
  collections: string[];
  created_at: string;
  mode?: string;
  llm_model?: string;
  system_prompt?: string;
  domain_classes?: string[];
  write_permissions?: string[];
  session_cache_ttl?: number;
  has_code?: boolean;
  generated_tools?: GeneratedTool[];
  improvement_policy?: ImprovementPolicy;
  filters?: { intent_rules?: IntentRules };
}

interface GeneratedTool {
  name: string;
  signature: string;
  description?: string;
  arg_types?: Record<string, string>;
  return_type?: string;
  source?: "ontology" | "code_analysis";
}

interface ImprovementPolicy {
  enabled: boolean;
  correction_threshold: number;
  tool_usage_window_days: number;
  prompt_revision_requires_review: boolean;
  track_execution_failures: boolean;
  auto_propose_tool_additions: boolean;
}

interface PerformanceMetric {
  date: string;
  interactions: number;
  approved: number;
  rejected: number;
  modified: number;
  correction_rate: number;
}

interface ToolUsage {
  name: string;
  calls: number;
  source: "ontology" | "code_analysis";
}

interface Proposal {
  id: string;
  type: "prompt_revision" | "tool_addition" | "rule_rewrite" | "exec_fix";
  triggered_by: string;
  created_at: string;
  status: "pending" | "approved" | "rejected";
  summary: string;
  detail: string;
  root_cause?: string;
  diff?: { before: string; after: string };
  correction_rate_at_trigger?: number;
  score?: number;
  confidence?: number;
}

interface ExecutionEvent {
  id: string;
  type: "start" | "stop" | "failure" | "ready";
  timestamp: string;
  message: string;
  stderr_tail?: string;
  exit_code?: number;
  duration_ms?: number;
}

interface PromptVersion {
  version: number;
  approved_at: string;
  approved_by: string;
  correction_rate_before?: number;
  correction_rate_after?: number;
  summary: string;
  prompt_snippet: string;
}

// ── Color palette ──────────────────────────────────────────────────────────

const C = {
  green:  { text: "#6EBE46", bg: "rgba(110,190,70,0.1)",   border: "rgba(110,190,70,0.28)" },
  purple: { text: "#AFA9EC", bg: "rgba(175,169,236,0.1)",  border: "rgba(175,169,236,0.28)" },
  amber:  { text: "#E6AA32", bg: "rgba(230,170,50,0.09)",  border: "rgba(230,170,50,0.28)" },
  teal:   { text: "#5DCAA5", bg: "rgba(93,202,165,0.09)",  border: "rgba(93,202,165,0.28)" },
  blue:   { text: "#60a5fa", bg: "rgba(96,165,250,0.09)",  border: "rgba(96,165,250,0.28)" },
  red:    { text: "#f87171", bg: "rgba(248,113,113,0.09)", border: "rgba(248,113,113,0.28)" },
};

const DARK = {
  bg: "var(--bg)", bgRaised: "var(--bg-raised)", bgCard: "var(--bg-card)",
  border: "var(--border)", borderSub: "var(--border-sub)",
  textPri: "var(--text-pri)", textSec: "var(--text-sec)",
  textMuted: "var(--text-muted)", textDim: "var(--text-dim)",
};
const LIGHT = {
  bg: "#f4f6fb", bgRaised: "#ffffff", bgCard: "#ffffff",
  border: "#dde2ef", borderSub: "#e8ecf5",
  textPri: "#111827", textSec: "#374151",
  textMuted: "#6b7280", textDim: "#9ca3af",
};

// ── Shared primitives ──────────────────────────────────────────────────────

function Tag({ color, children, mono = false }: { color: keyof typeof C; children: React.ReactNode; mono?: boolean }) {
  const c = C[color];
  return <span style={{ padding: "2px 8px", borderRadius: 4, fontSize: 11, fontWeight: 500, background: c.bg, border: `1px solid ${c.border}`, color: c.text, fontFamily: mono ? "monospace" : "inherit" }}>{children}</span>;
}

function StatCard({ label, value, sub, color = "green" }: { label: string; value: string | number; sub?: string; color?: keyof typeof C }) {
  return (
    <div style={{ padding: "14px 16px", borderRadius: 10, border: `1px solid var(--border)`, background: "var(--bg-card)" }}>
      <div style={{ fontSize: 22, fontWeight: 700, color: C[color].text, fontFamily: "monospace", letterSpacing: "-0.02em" }}>{value}</div>
      <div style={{ fontSize: 10, fontWeight: 700, color: "var(--text-muted)", marginTop: 3, textTransform: "uppercase", letterSpacing: "0.07em" }}>{label}</div>
      {sub && <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>{sub}</div>}
    </div>
  );
}

function EmptyState({ icon, title, sub }: { icon: React.ReactNode; title: string; sub: string }) {
  return (
    <div style={{ padding: 40, borderRadius: 10, textAlign: "center", border: "1px solid var(--border)", background: "var(--bg-card)" }}>
      <div style={{ color: "var(--text-muted)", display: "flex", justifyContent: "center", marginBottom: 12 }}>{icon}</div>
      <p style={{ fontSize: 13, color: "var(--text-sec)", margin: "0 0 4px", fontWeight: 600 }}>{title}</p>
      <p style={{ fontSize: 12, color: "var(--text-muted)", margin: 0 }}>{sub}</p>
    </div>
  );
}

function MiniBar({ value, max, color }: { value: number; max: number; color: string }) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  return <div style={{ flex: 1, height: 5, borderRadius: 3, background: "var(--border)", overflow: "hidden" }}><div style={{ width: `${pct}%`, height: "100%", background: color, borderRadius: 3, transition: "width 0.4s ease" }} /></div>;
}

function Sparkline({ data, color = "#6EBE46", width = 100, height = 28 }: { data: number[]; color?: string; width?: number; height?: number }) {
  if (data.length < 2) return null;
  const max = Math.max(...data) || 1;
  const min = Math.min(...data);
  const range = max - min || 1;
  const pad = 2;
  const pts = data.map((v, i) => {
    const x = pad + (i / (data.length - 1)) * (width - pad * 2);
    const y = pad + ((max - v) / range) * (height - pad * 2);
    return `${x},${y}`;
  });
  const path = "M" + pts.join(" L");
  const area = `${path} L${width - pad},${height - pad} L${pad},${height - pad} Z`;
  const gid  = `g${color.replace(/[^a-z0-9]/gi, "")}`;
  return (
    <svg width={width} height={height} style={{ display: "block" }}>
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%"   stopColor={color} stopOpacity="0.3" />
          <stop offset="100%" stopColor={color} stopOpacity="0"   />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#${gid})`} />
      <path d={path} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

function DiffView({ before, after }: { before: string; after: string }) {
  const bl = before.split("\n");
  const al = after.split("\n");
  const added   = al.filter(l => !bl.includes(l));
  const removed = bl.filter(l => !al.includes(l));
  return (
    <pre style={{ fontSize: 11, fontFamily: "monospace", lineHeight: 1.7, background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 7, padding: "10px 12px", margin: 0, overflowX: "auto", whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
      {al.map((line, i) => {
        const isAdded   = added.includes(line);
        const isRemoved = removed.includes(line);
        return (
          <div key={i} style={{ background: isAdded ? "rgba(110,190,70,0.12)" : isRemoved ? "rgba(248,113,113,0.1)" : "transparent", color: isAdded ? "#6EBE46" : isRemoved ? "#f87171" : "var(--text-sec)", paddingLeft: 4, marginLeft: -4 }}>
            <span style={{ opacity: 0.5, marginRight: 8, userSelect: "none" }}>{isAdded ? "+" : isRemoved ? "-" : " "}</span>
            {line}
          </div>
        );
      })}
    </pre>
  );
}

function TriggerList({ label, color, items, onChange }: { label: string; color: keyof typeof C; items: string[]; onChange: (next: string[]) => void }) {
  const [draft, setDraft] = useState("");
  const c = C[color];
  const add = () => {
    const t = draft.trim().toLowerCase();
    if (t && !items.includes(t)) { onChange([...items, t]); setDraft(""); }
  };
  return (
    <div>
      <div style={{ fontSize: 10, fontWeight: 700, color: c.text, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>{label}</div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginBottom: 6 }}>
        {items.map((item, idx) => (
          <span key={idx} style={{ display: "flex", alignItems: "center", gap: 4, padding: "2px 8px", borderRadius: 4, fontSize: 11, background: c.bg, border: `1px solid ${c.border}`, color: c.text }}>
            {item}
            <button onClick={() => onChange(items.filter((_, i) => i !== idx))} style={{ background: "none", border: "none", cursor: "pointer", color: c.text, padding: 0, display: "flex", lineHeight: 1 }}><X style={{ width: 9, height: 9 }} /></button>
          </span>
        ))}
        {items.length === 0 && <span style={{ fontSize: 11, color: "var(--text-dim)", fontStyle: "italic" }}>none — all messages route here by default</span>}
      </div>
      <div style={{ display: "flex", gap: 6 }}>
        <input value={draft} onChange={e => setDraft(e.target.value)} onKeyDown={e => { if (e.key === "Enter") { e.preventDefault(); add(); } }} placeholder="Add phrase…" style={{ flex: 1, padding: "5px 9px", borderRadius: 5, border: "1px solid var(--border)", background: "var(--bg)", color: "var(--text-pri)", fontSize: 11, fontFamily: "monospace", outline: "none" }} />
        <button onClick={add} style={{ padding: "5px 9px", borderRadius: 5, border: `1px solid ${c.border}`, background: c.bg, color: c.text, cursor: "pointer", fontSize: 11, display: "flex", alignItems: "center", gap: 4 }}><Plus style={{ width: 9, height: 9 }} /> Add</button>
      </div>
    </div>
  );
}

// ── Fleet card ─────────────────────────────────────────────────────────────

function FleetCard({ plugin, metrics, proposals, onSelect, onToggle, onDelete, isDark }: {
  plugin: Plugin; metrics: PerformanceMetric[]; proposals: Proposal[];
  onSelect: () => void; onToggle: (v: boolean) => void; onDelete: (e: React.MouseEvent) => void; isDark: boolean;
}) {
  const latest  = metrics.slice(-1)[0];
  const rateData = metrics.map(m => m.correction_rate);
  const trend   = rateData.length > 3 ? rateData[rateData.length - 1] - rateData[rateData.length - 4] : 0;
  const pending  = proposals.filter(p => p.status === "pending").length;
  const policy  = plugin.improvement_policy;
  const over    = policy?.enabled && latest && latest.correction_rate > (policy.correction_threshold ?? 0.25);
  const TF      = isDark ? DARK : LIGHT;

  return (
    <div onClick={onSelect} style={{ padding: "16px 18px", borderRadius: 12, cursor: "pointer", border: `1px solid ${over ? C.amber.border : plugin.active ? C.green.border : TF.border}`, background: over ? C.amber.bg : TF.bgRaised, transition: "border-color 0.18s, background 0.18s", position: "relative" }}>
      {pending > 0 && <div style={{ position: "absolute", top: 12, right: 40, width: 18, height: 18, borderRadius: "50%", background: C.amber.text, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 10, fontWeight: 700, color: "#0b0e18" }}>{pending}</div>}
      <button onClick={onDelete} style={{ position: "absolute", top: 10, right: 10, background: "none", border: "none", cursor: "pointer", color: TF.textMuted, padding: 3, borderRadius: 4, display: "flex", alignItems: "center", opacity: 0.6 }} onMouseEnter={e => (e.currentTarget.style.opacity = "1")} onMouseLeave={e => (e.currentTarget.style.opacity = "0.6")}>
        <Trash2 style={{ width: 13, height: 13, color: C.red.text }} />
      </button>
      <div style={{ display: "flex", alignItems: "flex-start", gap: 12, marginBottom: 14 }}>
        <div style={{ width: 40, height: 40, borderRadius: 9, fontSize: 20, display: "flex", alignItems: "center", justifyContent: "center", border: `1px solid ${TF.border}`, background: TF.bg, flexShrink: 0 }}>{plugin.icon}</div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 3, flexWrap: "wrap" }}>
            <span style={{ fontSize: 13, fontWeight: 700, color: TF.textPri }}>{plugin.name}</span>
            <span style={{ padding: "1px 6px", borderRadius: 3, fontSize: 9, fontWeight: 700, fontFamily: "monospace", background: plugin.active ? C.green.bg : TF.border, border: `1px solid ${plugin.active ? C.green.border : TF.borderSub}`, color: plugin.active ? C.green.text : TF.textMuted }}>{plugin.active ? "LIVE" : "OFF"}</span>
            {policy?.enabled && <span style={{ padding: "1px 6px", borderRadius: 3, fontSize: 9, fontWeight: 700, background: C.blue.bg, border: `1px solid ${C.blue.border}`, color: C.blue.text }}>LEARNING</span>}
            {plugin.has_code  && <span style={{ padding: "1px 6px", borderRadius: 3, fontSize: 9, fontWeight: 700, background: C.teal.bg, border: `1px solid ${C.teal.border}`, color: C.teal.text }}>EXEC</span>}
          </div>
          <p style={{ fontSize: 11, color: TF.textSec, margin: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{plugin.description}</p>
        </div>
      </div>
      <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between" }}>
        <div>
          <div style={{ fontSize: 10, color: TF.textMuted, marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.06em" }}>Correction rate (14d)</div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 20, fontWeight: 700, fontFamily: "monospace", color: over ? C.amber.text : C.green.text }}>
              {latest ? `${Math.round(latest.correction_rate * 100)}%` : "—"}
            </span>
            {trend !== 0 && (
              <span style={{ fontSize: 11, color: trend > 0 ? C.red.text : C.green.text, display: "flex", alignItems: "center", gap: 3 }}>
                {trend > 0 ? <TrendingUp style={{ width: 12, height: 12 }} /> : <TrendingDown style={{ width: 12, height: 12 }} />}
                {Math.abs(Math.round(trend * 100))}%
              </span>
            )}
          </div>
        </div>
        <Sparkline data={rateData.slice(-14)} color={over ? C.amber.text : C.green.text} width={90} height={28} />
      </div>
      {over && (
        <div style={{ marginTop: 10, padding: "6px 10px", borderRadius: 6, background: C.amber.bg, border: `1px solid ${C.amber.border}` }}>
          <span style={{ fontSize: 11, color: C.amber.text }}>⚡ Rate above threshold — {pending} proposal{pending !== 1 ? "s" : ""} queued</span>
        </div>
      )}
      {!latest && metrics.length === 0 && (
        <div style={{ marginTop: 8, fontSize: 11, color: TF.textMuted, fontStyle: "italic" }}>No interactions logged yet</div>
      )}
    </div>
  );
}

// ── Tab: Overview ──────────────────────────────────────────────────────────

function TabOverview({ plugin, onToggle, onConfigSaved }: { plugin: Plugin; onToggle: (v: boolean) => void; onConfigSaved: (patch: Partial<Plugin>) => void }) {
  const policy = plugin.improvement_policy;
  const [editingPrompt, setEditingPrompt] = useState(false);
  const [promptDraft, setPromptDraft]     = useState("");
  const [livePrompt, setLivePrompt]       = useState<string | null>(null);
  const [promptSaving, setPromptSaving]   = useState(false);
  const [promptSaved, setPromptSaved]     = useState(false);
  const [showRules, setShowRules]         = useState(false);
  const [rules, setRules]                 = useState<IntentRules>({ direct_answer_triggers: [], decline_triggers: [], graph_query_triggers: [] });
  const [rulesSaving, setRulesSaving]     = useState(false);
  const [rulesSaved, setRulesSaved]       = useState(false);
  const [rulesError, setRulesError]       = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API_BASE}/api/plugins/${plugin.id}/config`)
      .then(r => r.json())
      .then(d => {
        if (d.success) {
          setLivePrompt(d.config?.system_prompt ?? d.system_prompt ?? null);
          setRules(d.intent_rules ?? { direct_answer_triggers: [], decline_triggers: [], graph_query_triggers: [] });
        }
      })
      .catch(() => {
        setLivePrompt(plugin.system_prompt ?? null);
        setRules(plugin.filters?.intent_rules ?? { direct_answer_triggers: [], decline_triggers: [], graph_query_triggers: [] });
      });
  }, [plugin.id]);

  const displayPrompt = livePrompt ?? plugin.system_prompt ?? "";

  const savePrompt = async () => {
    setPromptSaving(true);
    try {
      const res  = await fetch(`${API_BASE}/api/plugins/${plugin.id}/config`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ system_prompt: promptDraft }) });
      const data = await res.json();
      if (data.success) { setLivePrompt(promptDraft); setEditingPrompt(false); setPromptSaved(true); onConfigSaved({ system_prompt: promptDraft }); setTimeout(() => setPromptSaved(false), 3000); }
    } catch (e) { console.error(e); }
    finally { setPromptSaving(false); }
  };

  const saveRules = async () => {
    setRulesSaving(true); setRulesError(null);
    try {
      const res  = await fetch(`${API_BASE}/api/plugins/${plugin.id}/intent-rules`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(rules) });
      const data = await res.json();
      if (data.success) { setRulesSaved(true); onConfigSaved({ filters: { intent_rules: rules } }); setTimeout(() => setRulesSaved(false), 3000); }
      else { setRulesError(data.detail ?? "Save failed"); }
    } catch { setRulesError("Network error"); }
    finally { setRulesSaving(false); }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
        {/* Manifest */}
        <div style={{ border: "1px solid var(--border)", borderRadius: 10, overflow: "hidden", background: "var(--bg-card)" }}>
          <div style={{ padding: "10px 14px", borderBottom: "1px solid var(--border-sub)", fontSize: 10, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.07em" }}>Manifest</div>
          {[
            { k: "App ID", v: plugin.id },
            { k: "Mode",   v: plugin.mode || "action" },
            { k: "LLM",    v: plugin.llm_model || "—" },
            { k: "Cache",  v: `${plugin.session_cache_ttl || 300}s` },
          ].map(row => (
            <div key={row.k} style={{ display: "flex", alignItems: "center", padding: "8px 14px", borderBottom: "1px solid var(--border-sub)" }}>
              <span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-muted)", width: 56, flexShrink: 0, textTransform: "uppercase", letterSpacing: "0.05em" }}>{row.k}</span>
              <span style={{ fontSize: 12, color: "var(--text-pri)", fontFamily: "monospace" }}>{row.v}</span>
            </div>
          ))}
          <div style={{ padding: "8px 14px", borderBottom: "1px solid var(--border-sub)" }}>
            <span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em", display: "block", marginBottom: 5 }}>Domain</span>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>{plugin.domain_classes?.map(c => <Tag key={c} color="green">{c}</Tag>) || <span style={{ fontSize: 11, color: "var(--text-muted)" }}>None</span>}</div>
          </div>
          <div style={{ padding: "8px 14px" }}>
            <span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em", display: "block", marginBottom: 5 }}>Permissions</span>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>{plugin.write_permissions?.length ? plugin.write_permissions.map(p => <Tag key={p} color="amber">{p}</Tag>) : <span style={{ fontSize: 11, color: "var(--text-muted)" }}>Read-only</span>}</div>
          </div>
        </div>

        {/* Status */}
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <div style={{ border: "1px solid var(--border)", borderRadius: 10, overflow: "hidden", background: "var(--bg-card)" }}>
            <div style={{ padding: "10px 14px", borderBottom: "1px solid var(--border-sub)", fontSize: 10, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.07em" }}>Agent status</div>
            <div style={{ padding: 14 }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <div>
                  <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-pri)", marginBottom: 2 }}>Plugin endpoint</div>
                  <div style={{ fontSize: 10, color: "var(--text-muted)", fontFamily: "monospace" }}>POST /api/plugins/{plugin.id}/agent</div>
                </div>
                <button onClick={() => onToggle(!plugin.active)} style={{ display: "flex", alignItems: "center", gap: 5, padding: "5px 12px", borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: "pointer", border: `1px solid ${plugin.active ? C.green.border : "var(--border)"}`, background: plugin.active ? C.green.bg : "var(--border)", color: plugin.active ? C.green.text : "var(--text-sec)", transition: "all 0.15s" }}>
                  {plugin.active ? <><ToggleRight style={{ width: 13, height: 13 }} /> Active</> : <><ToggleLeft style={{ width: 13, height: 13 }} /> Inactive</>}
                </button>
              </div>
            </div>
          </div>
          {plugin.has_code && (
            <div style={{ border: "1px solid var(--border)", borderRadius: 10, overflow: "hidden", background: "var(--bg-card)" }}>
              <div style={{ padding: "10px 14px", borderBottom: "1px solid var(--border-sub)", fontSize: 10, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.07em" }}>Program</div>
              <div style={{ padding: 14, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 5 }}><div style={{ width: 6, height: 6, borderRadius: "50%", background: C.green.text }} /><span style={{ fontSize: 11, color: C.green.text }}>Running</span></div>
                <div style={{ display: "flex", gap: 6 }}>
                  <button style={{ padding: "5px 10px", borderRadius: 6, border: `1px solid ${C.green.border}`, background: C.green.bg, color: C.green.text, cursor: "pointer", fontSize: 11, display: "flex", alignItems: "center", gap: 4 }}><Play style={{ width: 10, height: 10 }} /> Start</button>
                  <button style={{ padding: "5px 10px", borderRadius: 6, border: `1px solid ${C.red.border}`, background: C.red.bg, color: C.red.text, cursor: "pointer", fontSize: 11, display: "flex", alignItems: "center", gap: 4 }}><Square style={{ width: 10, height: 10 }} /> Stop</button>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* System prompt */}
      <div style={{ border: `1px solid ${editingPrompt ? C.purple.border : "var(--border)"}`, borderRadius: 10, overflow: "hidden", background: "var(--bg-card)", transition: "border-color 0.2s" }}>
        <div style={{ padding: "10px 14px", borderBottom: "1px solid var(--border-sub)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.07em" }}>System prompt</span>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            {promptSaved && <span style={{ fontSize: 10, color: C.green.text, display: "flex", alignItems: "center", gap: 4 }}><Check style={{ width: 10, height: 10 }} /> Saved</span>}
            {!editingPrompt
              ? <button onClick={() => { setPromptDraft(displayPrompt); setEditingPrompt(true); setPromptSaved(false); }} style={{ fontSize: 11, color: C.purple.text, background: "none", border: "none", cursor: "pointer", display: "flex", alignItems: "center", gap: 4 }}><FileCode style={{ width: 11, height: 11 }} /> Edit</button>
              : <div style={{ display: "flex", gap: 6 }}>
                  <button onClick={() => setEditingPrompt(false)} style={{ fontSize: 11, color: "var(--text-muted)", background: "none", border: "none", cursor: "pointer" }}>Cancel</button>
                  <button onClick={savePrompt} disabled={promptSaving} style={{ fontSize: 11, fontWeight: 600, color: "var(--bg)", background: C.green.text, border: "none", borderRadius: 5, padding: "3px 10px", cursor: "pointer", display: "flex", alignItems: "center", gap: 4 }}>
                    {promptSaving ? <RefreshCw style={{ width: 10, height: 10, animation: "spin 1s linear infinite" }} /> : <Check style={{ width: 10, height: 10 }} />} Save
                  </button>
                </div>
            }
          </div>
        </div>
        {editingPrompt
          ? <textarea value={promptDraft} onChange={e => setPromptDraft(e.target.value)} style={{ width: "100%", padding: "12px 14px", margin: 0, fontSize: 11, color: "var(--text-pri)", fontFamily: "monospace", lineHeight: 1.7, background: "var(--bg)", border: "none", outline: "none", resize: "vertical", minHeight: 180, boxSizing: "border-box" }} />
          : <pre style={{ padding: "12px 14px", margin: 0, fontSize: 11, color: "var(--text-sec)", fontFamily: "monospace", lineHeight: 1.7, overflowY: "auto", maxHeight: 200, whiteSpace: "pre-wrap", wordBreak: "break-word", background: "transparent" }}>
              {displayPrompt || <span style={{ color: "var(--text-dim)", fontStyle: "italic" }}>No system prompt configured</span>}
            </pre>
        }
      </div>

      {/* Intent routing rules */}
      <div style={{ border: `1px solid ${showRules ? C.teal.border : "var(--border)"}`, borderRadius: 10, overflow: "hidden", background: "var(--bg-card)", transition: "border-color 0.2s" }}>
        <button onClick={() => setShowRules(s => !s)} style={{ width: "100%", padding: "10px 14px", borderBottom: showRules ? "1px solid var(--border-sub)" : "none", display: "flex", alignItems: "center", justifyContent: "space-between", background: "none", border: "none", cursor: "pointer" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
            <span style={{ fontSize: 10, fontWeight: 700, color: showRules ? C.teal.text : "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.07em" }}>Intent routing rules</span>
            <span style={{ fontSize: 10, color: "var(--text-dim)" }}>controls direct-answer · graph-query · decline</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            {rulesSaved && <span style={{ fontSize: 10, color: C.green.text, display: "flex", alignItems: "center", gap: 4 }}><Check style={{ width: 10, height: 10 }} /> Saved</span>}
            <ChevronDown style={{ width: 13, height: 13, color: "var(--text-muted)", transform: showRules ? "none" : "rotate(-90deg)", transition: "transform 0.2s" }} />
          </div>
        </button>
        {showRules && (
          <div style={{ padding: "14px 16px", display: "flex", flexDirection: "column", gap: 16 }}>
            <div style={{ padding: "10px 12px", borderRadius: 7, background: "var(--bg)", border: "1px solid var(--border-sub)", fontSize: 11, color: "var(--text-muted)", lineHeight: 1.6 }}>
              These phrase lists are read by the agent on every request. Changes take effect immediately.
              <br /><strong style={{ color: "var(--text-sec)" }}>Priority:</strong> direct_answer → decline → graph_query (catch-all).
            </div>
            <TriggerList label="Direct answer — respond from system prompt, skip graph" color="green" items={rules.direct_answer_triggers} onChange={v => setRules(r => ({ ...r, direct_answer_triggers: v }))} />
            <TriggerList label="Decline — out of scope, push back" color="red" items={rules.decline_triggers} onChange={v => setRules(r => ({ ...r, decline_triggers: v }))} />
            <TriggerList label="Explicit graph query triggers (empty = all remaining)" color="purple" items={rules.graph_query_triggers} onChange={v => setRules(r => ({ ...r, graph_query_triggers: v }))} />
            {rulesError && <div style={{ display: "flex", alignItems: "center", gap: 7, padding: "8px 11px", borderRadius: 6, background: C.red.bg, border: `1px solid ${C.red.border}`, fontSize: 11, color: C.red.text }}><AlertCircle style={{ width: 12, height: 12 }} /> {rulesError}</div>}
            <button onClick={saveRules} disabled={rulesSaving} style={{ alignSelf: "flex-start", padding: "6px 14px", borderRadius: 6, border: `1px solid ${C.teal.border}`, background: C.teal.bg, color: C.teal.text, cursor: "pointer", fontSize: 12, fontWeight: 600, display: "flex", alignItems: "center", gap: 5 }}>
              {rulesSaving ? <RefreshCw style={{ width: 11, height: 11, animation: "spin 1s linear infinite" }} /> : <Check style={{ width: 11, height: 11 }} />}
              {rulesSaving ? "Saving…" : "Save rules"}
            </button>
          </div>
        )}
      </div>

      {/* Learning policy */}
      {policy && (
        <div style={{ padding: "14px 16px", borderRadius: 10, border: `1px solid ${policy.enabled ? C.blue.border : "var(--border)"}`, background: policy.enabled ? C.blue.bg : "var(--bg-card)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: policy.enabled ? 10 : 0 }}>
            <Brain style={{ width: 15, height: 15, color: policy.enabled ? C.blue.text : "var(--text-muted)" }} />
            <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text-pri)" }}>Adaptive learning</span>
            <span style={{ marginLeft: "auto", fontSize: 11, color: policy.enabled ? C.blue.text : "var(--text-muted)", fontWeight: 700 }}>{policy.enabled ? "ENABLED" : "DISABLED"}</span>
          </div>
          {policy.enabled && (
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <Tag color="blue">{Math.round(policy.correction_threshold * 100)}% threshold</Tag>
              <Tag color="blue">{policy.tool_usage_window_days}d window</Tag>
              {policy.track_execution_failures && <Tag color="teal">exec tracking</Tag>}
              {policy.auto_propose_tool_additions && <Tag color="blue">tool proposals</Tag>}
              <Tag color="amber">review required</Tag>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Tab: Performance ───────────────────────────────────────────────────────

function TabPerformance({ plugin, metrics, tools, totals }: { plugin: Plugin; metrics: PerformanceMetric[]; tools: ToolUsage[]; totals: { interactions: number; confirmed: number; rejected: number; correction_rate: number } }) {
  const latest   = metrics.slice(-1)[0];
  const policy   = plugin.improvement_policy;
  const maxCalls = Math.max(...tools.map(t => t.calls), 1);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 10 }}>
        <StatCard label="Total interactions" value={totals.interactions} color="green" />
        <StatCard label="Confirmed"          value={totals.confirmed}    color="green" />
        <StatCard label="Rejected"           value={totals.rejected}     color="red"   />
        <StatCard label="Correction rate"
          value={totals.interactions ? `${Math.round(totals.correction_rate * 100)}%` : "—"}
          color={latest && policy?.enabled && latest.correction_rate > (policy.correction_threshold ?? 0.25) ? "amber" : "green"}
          sub={policy?.enabled ? `Threshold: ${Math.round((policy.correction_threshold) * 100)}%` : undefined}
        />
      </div>

      {metrics.length === 0 ? (
        <EmptyState icon={<Activity style={{ width: 24, height: 24 }} />} title="No interaction data yet" sub="Interactions are logged automatically when the agent handles requests." />
      ) : (
        <div style={{ border: "1px solid var(--border)", borderRadius: 10, overflow: "hidden", background: "var(--bg-card)" }}>
          <div style={{ padding: "12px 16px", borderBottom: "1px solid var(--border-sub)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <span style={{ fontSize: 12, fontWeight: 600, color: "var(--text-pri)" }}>Correction rate over time</span>
            <span style={{ fontSize: 11, color: "var(--text-muted)" }}>14-day window</span>
          </div>
          <div style={{ padding: "14px 16px", display: "flex", flexDirection: "column", gap: 5 }}>
            {metrics.slice(-14).map((m, i) => {
              const over = policy?.enabled && m.correction_rate > (policy.correction_threshold ?? 0.25);
              return (
                <div key={i} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <span style={{ fontSize: 10, color: "var(--text-muted)", width: 52, flexShrink: 0, fontFamily: "monospace" }}>{m.date}</span>
                  <MiniBar value={m.correction_rate} max={0.6} color={over ? C.amber.text : C.green.text} />
                  <span style={{ fontSize: 11, fontWeight: 600, fontFamily: "monospace", width: 34, flexShrink: 0, color: over ? C.amber.text : "var(--text-sec)" }}>{Math.round(m.correction_rate * 100)}%</span>
                  <span style={{ fontSize: 10, color: "var(--text-muted)", width: 24, flexShrink: 0, textAlign: "right" }}>{m.interactions}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {tools.length === 0 ? (
        <EmptyState icon={<Wrench style={{ width: 22, height: 22 }} />} title="No tool usage data" sub="Tools are tracked automatically when the agent dispatches to them." />
      ) : (
        <div style={{ border: "1px solid var(--border)", borderRadius: 10, overflow: "hidden", background: "var(--bg-card)" }}>
          <div style={{ padding: "12px 16px", borderBottom: "1px solid var(--border-sub)" }}><span style={{ fontSize: 12, fontWeight: 600, color: "var(--text-pri)" }}>Tool usage</span></div>
          <div style={{ padding: "14px 16px", display: "flex", flexDirection: "column", gap: 7 }}>
            {tools.map(t => (
              <div key={t.name} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                {t.source === "code_analysis" ? <Terminal style={{ width: 11, height: 11, color: C.teal.text, flexShrink: 0 }} /> : <Code style={{ width: 11, height: 11, color: C.green.text, flexShrink: 0 }} />}
                <span style={{ fontSize: 11, color: "var(--text-pri)", fontFamily: "monospace", width: 200, flexShrink: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{t.name}</span>
                <MiniBar value={t.calls} max={maxCalls} color={t.source === "code_analysis" ? C.teal.text : C.green.text} />
                <span style={{ fontSize: 11, fontFamily: "monospace", color: "var(--text-sec)", width: 34, flexShrink: 0, textAlign: "right" }}>{t.calls}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Tab: Proposals ─────────────────────────────────────────────────────────

function TabProposals({ proposals, analyzing, onAction, onAnalyze }: { proposals: Proposal[]; analyzing: boolean; onAction: (id: string, action: "approved" | "rejected") => void; onAnalyze: () => void }) {
  const [expanded, setExpanded] = useState<string | null>(null);
  const typeIcon: Record<Proposal["type"], React.ReactNode> = {
    prompt_revision: <Brain style={{ width: 13, height: 13 }} />,
    tool_addition:   <Wrench style={{ width: 13, height: 13 }} />,
    rule_rewrite:    <GitBranch style={{ width: 13, height: 13 }} />,
    exec_fix:        <Terminal style={{ width: 13, height: 13 }} />,
  };
  const typeColor: Record<Proposal["type"], keyof typeof C> = { prompt_revision: "blue", tool_addition: "purple", rule_rewrite: "amber", exec_fix: "teal" };
  const typeLabel: Record<Proposal["type"], string>         = { prompt_revision: "Prompt revision", tool_addition: "Tool addition", rule_rewrite: "Rule rewrite", exec_fix: "Exec fix" };
  const pending  = proposals.filter(p => p.status === "pending");
  const resolved = proposals.filter(p => p.status !== "pending");

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
          {analyzing ? "LLM analysis running in background…" : "Proposals generated by LLM meta-agent analyzing interaction logs."}
        </span>
        <button onClick={onAnalyze} style={{ padding: "5px 12px", borderRadius: 6, border: `1px solid ${C.blue.border}`, background: C.blue.bg, color: C.blue.text, cursor: "pointer", fontSize: 11, display: "flex", alignItems: "center", gap: 5 }}>
          {analyzing ? <RefreshCw style={{ width: 10, height: 10, animation: "spin 1s linear infinite" }} /> : <RefreshCw style={{ width: 10, height: 10 }} />}
          Re-analyze
        </button>
      </div>

      {pending.length === 0 && !analyzing && (
        <EmptyState icon={<Check style={{ width: 22, height: 22 }} />} title="No pending proposals" sub="The improvement loop is healthy, or not enough interaction data exists yet." />
      )}

      {pending.length > 0 && (
        <div>
          <div style={{ fontSize: 10, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 8 }}>Pending review ({pending.length})</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {pending.map(p => {
              const col  = typeColor[p.type];
              const open = expanded === p.id;
              return (
                <div key={p.id} style={{ border: `1px solid ${C[col].border}`, borderRadius: 10, background: C[col].bg, overflow: "hidden" }}>
                  <div onClick={() => setExpanded(open ? null : p.id)} style={{ padding: "12px 14px", cursor: "pointer", display: "flex", alignItems: "flex-start", gap: 10 }}>
                    <span style={{ color: C[col].text, marginTop: 1, flexShrink: 0 }}>{typeIcon[p.type]}</span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 4, flexWrap: "wrap" }}>
                        <span style={{ fontSize: 12, fontWeight: 600, color: "var(--text-pri)" }}>{p.summary}</span>
                        <Tag color={col}>{typeLabel[p.type]}</Tag>
                        {p.correction_rate_at_trigger !== undefined && <Tag color="amber">{Math.round(p.correction_rate_at_trigger * 100)}% rate</Tag>}
                        {p.confidence !== undefined && <Tag color="teal">{Math.round(p.confidence * 100)}% confidence</Tag>}
                      </div>
                      <p style={{ margin: 0, fontSize: 11, color: "var(--text-muted)", lineHeight: 1.5 }}>{p.triggered_by}</p>
                    </div>
                    <ChevronDown style={{ width: 13, height: 13, color: "var(--text-muted)", flexShrink: 0, marginTop: 2, transform: open ? "rotate(180deg)" : "none", transition: "transform 0.2s" }} />
                  </div>
                  {open && (
                    <div style={{ borderTop: `1px solid ${C[col].border}`, padding: 14 }}>
                      {p.root_cause && <p style={{ margin: "0 0 8px", fontSize: 11, color: C[col].text, fontStyle: "italic" }}>Root cause: {p.root_cause}</p>}
                      <p style={{ margin: "0 0 12px", fontSize: 12, color: "var(--text-sec)", lineHeight: 1.6 }}>{p.detail}</p>
                      {p.diff && (
                        <div style={{ marginBottom: 14 }}>
                          <div style={{ fontSize: 10, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>Proposed diff</div>
                          <DiffView before={p.diff.before} after={p.diff.after} />
                        </div>
                      )}
                      <div style={{ display: "flex", gap: 8 }}>
                        <button onClick={e => { e.stopPropagation(); onAction(p.id, "approved"); }} style={{ padding: "6px 14px", borderRadius: 6, border: `1px solid ${C.green.border}`, background: C.green.bg, color: C.green.text, cursor: "pointer", fontSize: 12, fontWeight: 600, display: "flex", alignItems: "center", gap: 5 }}><Check style={{ width: 12, height: 12 }} /> Approve & apply</button>
                        <button onClick={e => { e.stopPropagation(); onAction(p.id, "rejected"); }} style={{ padding: "6px 12px", borderRadius: 6, border: `1px solid ${C.red.border}`, background: C.red.bg, color: C.red.text, cursor: "pointer", fontSize: 12, fontWeight: 600, display: "flex", alignItems: "center", gap: 5 }}><X style={{ width: 12, height: 12 }} /> Reject</button>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {resolved.length > 0 && (
        <div>
          <div style={{ fontSize: 10, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 8 }}>Resolved ({resolved.length})</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
            {resolved.map(p => (
              <div key={p.id} style={{ padding: "10px 14px", borderRadius: 8, display: "flex", alignItems: "center", gap: 10, border: "1px solid var(--border)", background: "var(--bg-card)" }}>
                {p.status === "approved" ? <Check style={{ width: 13, height: 13, color: C.green.text, flexShrink: 0 }} /> : <X style={{ width: 13, height: 13, color: C.red.text, flexShrink: 0 }} />}
                <span style={{ fontSize: 12, color: "var(--text-sec)", flex: 1 }}>{p.summary}</span>
                <span style={{ fontSize: 11, color: "var(--text-muted)" }}>{new Date(p.created_at).toLocaleDateString()}</span>
                <Tag color={p.status === "approved" ? "green" : "red"}>{p.status}</Tag>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Tab: Execution ─────────────────────────────────────────────────────────

function TabExecution({ plugin_id, events, onRefresh }: { plugin_id: string; events: ExecutionEvent[]; onRefresh: () => void }) {
  const [expandedErr, setExpandedErr] = useState<string | null>(null);
  const typeStyle: Record<ExecutionEvent["type"], { icon: React.ReactNode; color: keyof typeof C }> = {
    start:   { icon: <Play style={{ width: 11, height: 11 }} />,          color: "green" },
    stop:    { icon: <Square style={{ width: 11, height: 11 }} />,         color: "amber" },
    failure: { icon: <AlertTriangle style={{ width: 11, height: 11 }} />,  color: "red"   },
    ready:   { icon: <Check style={{ width: 11, height: 11 }} />,          color: "teal"  },
  };

  const logStart = async () => {
    await fetch(`${API_BASE}/api/plugins/${plugin_id}/log-execution`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ type: "start", message: "Manual start triggered from dashboard" }) });
    onRefresh();
  };

  const logStop = async () => {
    await fetch(`${API_BASE}/api/plugins/${plugin_id}/log-execution`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ type: "stop", message: "Manual stop triggered from dashboard", exit_code: 0 }) });
    onRefresh();
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={logStart} style={{ padding: "6px 14px", borderRadius: 6, border: `1px solid ${C.green.border}`, background: C.green.bg, color: C.green.text, cursor: "pointer", fontSize: 12, fontWeight: 600, display: "flex", alignItems: "center", gap: 5 }}><Play style={{ width: 11, height: 11 }} /> Start program</button>
          <button onClick={logStop}  style={{ padding: "6px 14px", borderRadius: 6, border: `1px solid ${C.red.border}`,   background: C.red.bg,   color: C.red.text,   cursor: "pointer", fontSize: 12, fontWeight: 600, display: "flex", alignItems: "center", gap: 5 }}><Square style={{ width: 11, height: 11 }} /> Stop program</button>
        </div>
        <button onClick={onRefresh} style={{ padding: "5px 10px", borderRadius: 6, border: "1px solid var(--border)", background: "var(--bg-card)", color: "var(--text-muted)", cursor: "pointer", fontSize: 11, display: "flex", alignItems: "center", gap: 4 }}><RefreshCw style={{ width: 11, height: 11 }} /> Refresh</button>
      </div>

      {events.length === 0 ? (
        <EmptyState icon={<Terminal style={{ width: 22, height: 22 }} />} title="No execution events" sub="Events are logged when the agent program starts, stops, or fails." />
      ) : (
        <div style={{ border: "1px solid var(--border)", borderRadius: 10, overflow: "hidden", background: "var(--bg-card)" }}>
          <div style={{ padding: "10px 14px", borderBottom: "1px solid var(--border-sub)", fontSize: 10, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.07em" }}>Execution log</div>
          <div style={{ padding: "10px 14px" }}>
            {events.map(e => {
              const s     = typeStyle[e.type] || typeStyle.start;
              const isErr = e.type === "failure";
              const isOpen = expandedErr === e.id;
              const ts    = e.timestamp || (e as any).ts || "";
              return (
                <div key={e.id}>
                  <div onClick={() => isErr && setExpandedErr(isOpen ? null : e.id)} style={{ display: "flex", alignItems: "center", gap: 10, padding: "7px 0", borderBottom: "1px solid var(--border-sub)", cursor: isErr ? "pointer" : "default" }}>
                    <span style={{ color: C[s.color].text, flexShrink: 0 }}>{s.icon}</span>
                    <span style={{ fontSize: 11, fontFamily: "monospace", color: "var(--text-muted)", width: 108, flexShrink: 0 }}>{ts ? new Date(ts).toLocaleTimeString() : "—"}</span>
                    <span style={{ fontSize: 12, color: "var(--text-sec)", flex: 1 }}>{e.message}</span>
                    {e.duration_ms && <span style={{ fontSize: 10, color: "var(--text-muted)", fontFamily: "monospace" }}>{e.duration_ms}ms</span>}
                    {e.exit_code !== undefined && <span style={{ fontSize: 10, fontFamily: "monospace", color: e.exit_code === 0 ? C.green.text : C.red.text }}>exit {e.exit_code}</span>}
                    {isErr && <ChevronDown style={{ width: 12, height: 12, color: "var(--text-muted)", transform: isOpen ? "rotate(180deg)" : "none", transition: "transform 0.2s" }} />}
                  </div>
                  {isErr && isOpen && e.stderr_tail && (
                    <pre style={{ margin: "4px 0", fontSize: 11, color: C.red.text, background: C.red.bg, border: `1px solid ${C.red.border}`, borderRadius: 6, padding: "8px 10px", fontFamily: "monospace", lineHeight: 1.6, whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{e.stderr_tail}</pre>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Tab: History ───────────────────────────────────────────────────────────

function TabHistory({ versions }: { versions: PromptVersion[] }) {
  const [expanded, setExpanded] = useState<number | null>(null);

  if (versions.length === 0) {
    return <EmptyState icon={<History style={{ width: 22, height: 22 }} />} title="No prompt history yet" sub="Approved prompt revisions are versioned here automatically." />;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <p style={{ margin: "0 0 6px", fontSize: 12, color: "var(--text-muted)", lineHeight: 1.5 }}>Every prompt revision approved through the review queue is versioned here.</p>
      {[...versions].reverse().map((v, i) => {
        const open     = expanded === v.version;
        const improved = v.correction_rate_after !== undefined && v.correction_rate_after < (v.correction_rate_before ?? 1);
        return (
          <div key={v.version} style={{ border: "1px solid var(--border)", borderRadius: 10, overflow: "hidden", background: "var(--bg-card)" }}>
            <div onClick={() => setExpanded(open ? null : v.version)} style={{ padding: "12px 14px", cursor: "pointer", display: "flex", alignItems: "center", gap: 12 }}>
              <div style={{ width: 26, height: 26, borderRadius: "50%", flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "center", background: i === 0 ? C.green.bg : "var(--border)", border: `1px solid ${i === 0 ? C.green.border : "var(--border)"}`, fontSize: 10, fontWeight: 700, color: i === 0 ? C.green.text : "var(--text-muted)" }}>v{v.version}</div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-pri)", marginBottom: 2 }}>{v.summary}</div>
                <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{new Date(v.approved_at).toLocaleDateString()} · {v.approved_by}</div>
              </div>
              {v.correction_rate_after !== undefined && v.correction_rate_before !== undefined && (
                <div style={{ display: "flex", alignItems: "center", gap: 6, flexShrink: 0 }}>
                  <span style={{ fontSize: 11, fontFamily: "monospace", color: "var(--text-muted)" }}>{Math.round(v.correction_rate_before * 100)}%</span>
                  <ArrowRight style={{ width: 12, height: 12, color: "var(--text-muted)" }} />
                  <span style={{ fontSize: 11, fontFamily: "monospace", fontWeight: 700, color: improved ? C.green.text : C.red.text }}>{Math.round(v.correction_rate_after * 100)}%</span>
                  {improved ? <TrendingDown style={{ width: 12, height: 12, color: C.green.text }} /> : <TrendingUp style={{ width: 12, height: 12, color: C.red.text }} />}
                </div>
              )}
              <ChevronDown style={{ width: 13, height: 13, color: "var(--text-muted)", flexShrink: 0, transform: open ? "rotate(180deg)" : "none", transition: "transform 0.2s" }} />
            </div>
            {open && (
              <div style={{ borderTop: "1px solid var(--border-sub)", padding: "12px 14px" }}>
                <div style={{ fontSize: 10, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>Prompt snippet</div>
                <pre style={{ fontSize: 11, color: "var(--text-sec)", background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 6, padding: "8px 10px", margin: 0, fontFamily: "monospace", lineHeight: 1.6, whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{v.prompt_snippet}</pre>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Tab: Console ───────────────────────────────────────────────────────────

interface ConsoleMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  question?: string;
  sparql?: string;
  results?: Record<string, unknown>[];
  resultCount?: number;
  timingMs?: number;
  error?: string;
  confirmed?: boolean;
  confirmPending?: boolean;
  intent?: string;
  toolName?: string;
  rawResponse?: unknown;
}

function TabConsole({ plugin }: { plugin: Plugin }) {
  const isConversational = plugin.mode === "conversational" || plugin.mode === "hybrid" || !plugin.mode;
  const isAction         = plugin.mode === "action" || plugin.mode === "hybrid";
  const [messages, setMessages]         = useState<ConsoleMessage[]>([]);
  const [nlInput, setNlInput]           = useState("");
  const [nlLoading, setNlLoading]       = useState(false);
  const [toolCall, setToolCall]         = useState<{ toolName: string; args: Record<string, string> }>({ toolName: "", args: {} });
  const [actionLoading, setActionLoading] = useState(false);
  const [actionResult, setActionResult]   = useState<ConsoleMessage | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => { if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight; }, [messages]);

  useEffect(() => {
    const tools = plugin.generated_tools || [];
    if (tools.length > 0 && !toolCall.toolName) {
      const first = tools[0];
      setToolCall({ toolName: first.name, args: Object.fromEntries(Object.keys(first.arg_types || {}).map(k => [k, ""])) });
    }
  }, [plugin]);

  const submitNL = async () => {
    const q = nlInput.trim();
    if (!q || nlLoading) return;
    setNlInput("");
    const userMsg: ConsoleMessage = { id: Date.now() + "u", role: "user", text: q, question: q };
    setMessages(prev => [...prev, userMsg]);
    setNlLoading(true);
    try {
      const res  = await fetch(`${API_BASE}/api/plugins/${plugin.id}/agent`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message: q }) });
      const data = await res.json();
      setMessages(prev => [...prev, {
        id: Date.now() + "a", role: "assistant",
        text:        data.answer || (data.success ? `Returned ${data.result_count ?? 0} result(s).` : (data.error || "No answer returned.")),
        question:    q,
        sparql:      data.sparql,
        results:     data.results || [],
        resultCount: data.result_count,
        timingMs:    data.timing_ms,
        error:       data.error,
        intent:      data.intent,
        toolName:    data.tool,
        rawResponse: data,
      }]);
    } catch (e) {
      const err = e instanceof Error ? e.message : "Request failed";
      setMessages(prev => [...prev, { id: Date.now() + "e", role: "assistant", text: "Failed to reach the agent.", error: err, question: q }]);
    } finally { setNlLoading(false); }
  };

  const updateOutcome = async (msg: ConsoleMessage, outcome: "confirmed" | "rejected") => {
    if (!msg.question) return;
    setMessages(prev => prev.map(m => m.id === msg.id ? { ...m, confirmPending: true } : m));
    try {
      await fetch(`${API_BASE}/api/plugins/${plugin.id}/interactions/outcome`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question: msg.question, outcome }) });
      setMessages(prev => prev.map(m => m.id === msg.id ? { ...m, confirmed: outcome === "confirmed", confirmPending: false } : m));
    } catch { setMessages(prev => prev.map(m => m.id === msg.id ? { ...m, confirmPending: false } : m)); }
  };

  const selectedTool = (plugin.generated_tools || []).find(t => t.name === toolCall.toolName);

  const submitAction = async () => {
    if (!toolCall.toolName || actionLoading) return;
    setActionLoading(true); setActionResult(null);
    const t0 = Date.now();
    try {
      const res  = await fetch(`${API_BASE}/api/plugins/${plugin.id}/agent`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action: toolCall.toolName, params: toolCall.args }) });
      const data = await res.json();
      setActionResult({ id: Date.now() + "r", role: "assistant", text: typeof data.answer === "string" ? data.answer : JSON.stringify(data, null, 2), toolName: toolCall.toolName, rawResponse: data, timingMs: Date.now() - t0, error: data.error });
    } catch (e) {
      const err = e instanceof Error ? e.message : "Request failed";
      setActionResult({ id: Date.now() + "e", role: "assistant", text: "Tool call failed.", error: err, toolName: toolCall.toolName, timingMs: Date.now() - t0 });
    } finally { setActionLoading(false); }
  };

  const intentBadge = (intent?: string) => {
    if (!intent) return null;
    const map: Record<string, keyof typeof C> = { direct_answer: "green", graph_query: "purple", decline: "amber", tool_call: "teal" };
    return <Tag color={map[intent] ?? "teal"}>{intent.replace("_", " ")}</Tag>;
  };

  const panelBase: React.CSSProperties = { border: "1px solid var(--border)", borderRadius: 10, background: "var(--bg-card)", overflow: "hidden" };
  const panelHeader: React.CSSProperties = { padding: "10px 14px", borderBottom: "1px solid var(--border-sub)", fontSize: 10, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.07em", display: "flex", alignItems: "center", justifyContent: "space-between" };
  const codeBlock: React.CSSProperties = { background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 7, padding: "8px 11px", margin: 0, fontSize: 11, fontFamily: "monospace", lineHeight: 1.65, color: "var(--text-sec)", overflowX: "auto", whiteSpace: "pre-wrap", wordBreak: "break-word" as const };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ fontSize: 12, color: "var(--text-muted)" }}>Agent test surface —</span>
        <code style={{ fontSize: 12, color: C.green.text, fontFamily: "monospace" }}>POST /api/plugins/{plugin.id}/agent</code>
        {isConversational && <Tag color="purple">NL Query</Tag>}
        {isAction         && <Tag color="teal">Tool Inspector</Tag>}
      </div>

      {isConversational && (
        <div style={{ ...panelBase, display: "flex", flexDirection: "column", minHeight: 420 }}>
          <div style={panelHeader}>
            <span style={{ display: "flex", alignItems: "center", gap: 6 }}><MessageSquare style={{ width: 11, height: 11 }} /> Natural language console</span>
            {messages.length > 0 && <button onClick={() => setMessages([])} style={{ fontSize: 10, color: "var(--text-muted)", background: "none", border: "none", cursor: "pointer" }}>Clear</button>}
          </div>
          <div ref={scrollRef} style={{ flex: 1, overflowY: "auto", padding: "14px 16px", display: "flex", flexDirection: "column", gap: 14, minHeight: 300 }}>
            {messages.length === 0 && (
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", flex: 1, gap: 10, opacity: 0.5 }}>
                <Radar style={{ width: 28, height: 28, color: "var(--text-muted)" }} />
                <p style={{ fontSize: 12, color: "var(--text-muted)", margin: 0, textAlign: "center" }}>Messages run through the full agent pipeline. Thumbs up/down trains the improvement loop.</p>
              </div>
            )}
            {messages.map(msg => (
              <div key={msg.id} style={{ display: "flex", flexDirection: "column", alignItems: msg.role === "user" ? "flex-end" : "flex-start" }}>
                <div style={{ maxWidth: "88%", padding: "9px 13px", borderRadius: msg.role === "user" ? "12px 12px 3px 12px" : "12px 12px 12px 3px", background: msg.role === "user" ? C.green.bg : "var(--msg-bg)", border: `1px solid ${msg.role === "user" ? C.green.border : "var(--border)"}`, fontSize: 13, color: "var(--text-pri)", lineHeight: 1.6 }}>
                  {msg.error ? <span style={{ color: C.red.text }}>{msg.text}</span> : msg.text}
                  {msg.error && <div style={{ marginTop: 5, fontSize: 11, color: C.red.text, fontFamily: "monospace" }}>{msg.error}</div>}
                  {msg.sparql && (
                    <details style={{ marginTop: 6 }}>
                      <summary style={{ fontSize: 10, fontWeight: 700, color: C.teal.text, cursor: "pointer", textTransform: "uppercase", letterSpacing: "0.06em" }}>Generated SPARQL</summary>
                      <pre style={{ ...codeBlock, marginTop: 6 }}>{msg.sparql}</pre>
                    </details>
                  )}
                  {(msg.resultCount ?? 0) > 0 && (
                    <details style={{ marginTop: 6 }}>
                      <summary style={{ fontSize: 10, fontWeight: 700, color: C.green.text, cursor: "pointer", textTransform: "uppercase", letterSpacing: "0.06em" }}>{msg.resultCount} result{msg.resultCount !== 1 ? "s" : ""}</summary>
                      <pre style={{ ...codeBlock, marginTop: 6, maxHeight: 160, overflowY: "auto" }}>{JSON.stringify(msg.results?.slice(0, 5), null, 2)}</pre>
                    </details>
                  )}
                </div>
                {msg.role === "assistant" && (
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 4, paddingLeft: 4 }}>
                    {intentBadge(msg.intent)}
                    {msg.timingMs !== undefined && <span style={{ fontSize: 10, color: "var(--text-dim)", fontFamily: "monospace" }}>{msg.timingMs}ms</span>}
                    {!msg.error && !msg.confirmed && (
                      <>
                        <button onClick={() => updateOutcome(msg, "confirmed")} disabled={!!msg.confirmPending} style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 10, color: msg.confirmPending ? "var(--text-dim)" : C.green.text, background: "none", border: "none", cursor: "pointer", padding: 0 }}>
                          <ThumbsUp style={{ width: 10, height: 10 }} />{msg.confirmPending ? "Saving…" : "Confirm"}
                        </button>
                        <button onClick={() => updateOutcome(msg, "rejected")} disabled={!!msg.confirmPending} style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 10, color: msg.confirmPending ? "var(--text-dim)" : C.red.text, background: "none", border: "none", cursor: "pointer", padding: 0 }}>
                          <ThumbsDown style={{ width: 10, height: 10 }} />Reject
                        </button>
                      </>
                    )}
                    {msg.confirmed !== undefined && <span style={{ fontSize: 10, color: msg.confirmed ? C.green.text : C.red.text, display: "flex", alignItems: "center", gap: 4 }}><Check style={{ width: 9, height: 9 }} />{msg.confirmed ? "Confirmed" : "Rejected"}</span>}
                  </div>
                )}
              </div>
            ))}
            {nlLoading && <div style={{ display: "flex", alignItems: "center", gap: 8, paddingLeft: 2 }}><Loader2 style={{ width: 13, height: 13, color: C.green.text, animation: "spin 1s linear infinite" }} /><span style={{ fontSize: 12, color: "var(--text-muted)" }}>Routing intent → executing…</span></div>}
          </div>
          <div style={{ borderTop: "1px solid var(--border)", padding: "12px 14px", display: "flex", gap: 8 }}>
            <input value={nlInput} onChange={e => setNlInput(e.target.value)} onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submitNL(); } }} placeholder={`Ask about ${plugin.domain_classes?.[0] || "artifacts"}, relationships, coverage…`} style={{ flex: 1, padding: "8px 12px", borderRadius: 7, border: "1px solid var(--border)", background: "var(--bg)", color: "var(--text-pri)", fontSize: 13, outline: "none", fontFamily: "inherit" }} />
            <button onClick={submitNL} disabled={!nlInput.trim() || nlLoading} style={{ padding: "8px 14px", borderRadius: 7, border: "none", background: nlInput.trim() && !nlLoading ? C.green.text : "var(--border)", color: nlInput.trim() && !nlLoading ? "var(--bg)" : "var(--text-muted)", cursor: nlInput.trim() && !nlLoading ? "pointer" : "not-allowed", display: "flex", alignItems: "center", gap: 5, fontSize: 12, fontWeight: 700, transition: "all 0.15s" }}>
              {nlLoading ? <Loader2 style={{ width: 13, height: 13, animation: "spin 1s linear infinite" }} /> : <Send style={{ width: 13, height: 13 }} />}
            </button>
          </div>
        </div>
      )}

      {isAction && (plugin.generated_tools || []).length > 0 && (
        <div style={panelBase}>
          <div style={panelHeader}><span style={{ display: "flex", alignItems: "center", gap: 6 }}><Wrench style={{ width: 11, height: 11 }} /> Tool call inspector</span><span style={{ fontSize: 10, color: "var(--text-dim)" }}>{(plugin.generated_tools || []).length} tools</span></div>
          <div style={{ padding: "14px 16px", display: "flex", flexDirection: "column", gap: 14 }}>
            <div><div style={{ fontSize: 10, fontWeight: 700, color: "var(--text-muted)", marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.06em" }}>Tool</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
                {(plugin.generated_tools || []).map(t => {
                  const isCode = t.source === "code_analysis";
                  const isSel  = toolCall.toolName === t.name;
                  return (
                    <button key={t.name} onClick={() => setToolCall({ toolName: t.name, args: Object.fromEntries(Object.keys(t.arg_types || {}).map(k => [k, ""])) })} style={{ padding: "4px 10px", borderRadius: 5, cursor: "pointer", border: `1px solid ${isSel ? (isCode ? C.teal.border : C.green.border) : "var(--border)"}`, background: isSel ? (isCode ? C.teal.bg : C.green.bg) : "var(--msg-bg)", color: isSel ? (isCode ? C.teal.text : C.green.text) : "var(--text-muted)", fontSize: 11, fontFamily: "monospace", display: "flex", alignItems: "center", gap: 5 }}>
                      {isCode ? <Terminal style={{ width: 9, height: 9 }} /> : <Code style={{ width: 9, height: 9 }} />}{t.name}
                    </button>
                  );
                })}
              </div>
            </div>
            {selectedTool && <div><div style={{ fontSize: 10, fontWeight: 700, color: "var(--text-muted)", marginBottom: 5, textTransform: "uppercase", letterSpacing: "0.06em" }}>Signature</div><pre style={codeBlock}>{selectedTool.signature}</pre>{selectedTool.description && <p style={{ fontSize: 11, color: "var(--text-muted)", margin: "5px 0 0" }}>{selectedTool.description}</p>}</div>}
            {selectedTool && Object.keys(selectedTool.arg_types || {}).length > 0 && (
              <div>
                <div style={{ fontSize: 10, fontWeight: 700, color: "var(--text-muted)", marginBottom: 8, textTransform: "uppercase", letterSpacing: "0.06em" }}>Arguments</div>
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {Object.entries(selectedTool.arg_types || {}).map(([argName, argType]) => (
                    <div key={argName}>
                      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}><code style={{ fontSize: 11, color: C.green.text }}>{argName}</code><span style={{ fontSize: 10, color: "var(--text-dim)", fontFamily: "monospace" }}>{argType}</span></div>
                      <input value={toolCall.args[argName] ?? ""} onChange={e => setToolCall(prev => ({ ...prev, args: { ...prev.args, [argName]: e.target.value } }))} placeholder={`Enter ${argName}…`} style={{ width: "100%", padding: "7px 11px", borderRadius: 6, border: "1px solid var(--border)", background: "var(--bg)", color: "var(--text-pri)", fontSize: 12, outline: "none", fontFamily: "monospace", boxSizing: "border-box" }} />
                    </div>
                  ))}
                </div>
              </div>
            )}
            <button onClick={submitAction} disabled={!toolCall.toolName || actionLoading} style={{ padding: "9px 16px", borderRadius: 7, border: "none", background: toolCall.toolName && !actionLoading ? C.teal.text : "var(--border)", color: toolCall.toolName && !actionLoading ? "var(--bg)" : "var(--text-muted)", cursor: toolCall.toolName && !actionLoading ? "pointer" : "not-allowed", fontSize: 12, fontWeight: 700, display: "flex", alignItems: "center", justifyContent: "center", gap: 6 }}>
              {actionLoading ? <><Loader2 style={{ width: 13, height: 13, animation: "spin 1s linear infinite" }} /> Calling…</> : <><Play style={{ width: 11, height: 11 }} /> Call tool</>}
            </button>
            {actionResult && (
              <div style={{ borderRadius: 8, overflow: "hidden", border: `1px solid ${actionResult.error ? C.red.border : C.teal.border}`, background: actionResult.error ? C.red.bg : C.teal.bg }}>
                <div style={{ padding: "8px 12px", borderBottom: `1px solid ${actionResult.error ? C.red.border : C.teal.border}`, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                    {actionResult.error ? <AlertTriangle style={{ width: 12, height: 12, color: C.red.text }} /> : <Check style={{ width: 12, height: 12, color: C.teal.text }} />}
                    <code style={{ fontSize: 11, color: actionResult.error ? C.red.text : C.teal.text, fontFamily: "monospace" }}>{actionResult.toolName}()</code>
                  </div>
                  <span style={{ fontSize: 10, color: "var(--text-muted)", fontFamily: "monospace" }}>{actionResult.timingMs}ms</span>
                </div>
                <div style={{ padding: "10px 12px" }}>
                  {actionResult.error && <div style={{ fontSize: 11, color: C.red.text, fontFamily: "monospace", marginBottom: 8 }}>{actionResult.error}</div>}
                  <pre style={{ ...codeBlock, maxHeight: 240, overflowY: "auto" }}>{typeof actionResult.rawResponse === "string" ? actionResult.rawResponse : JSON.stringify(actionResult.rawResponse, null, 2)}</pre>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {isAction && (plugin.generated_tools || []).length === 0 && (
        <EmptyState icon={<Wrench style={{ width: 22, height: 22 }} />} title="No tools registered" sub="Register tools via the App Onboarding wizard." />
      )}
    </div>
  );
}

// ── Main ───────────────────────────────────────────────────────────────────

export default function PluginDashboard({ initialPluginId = null }: { initialPluginId?: string | null }) {
  const [plugins, setPlugins]           = useState<Plugin[]>([]);
  const [selected, setSelected]         = useState<Plugin | null>(null);
  const [tab, setTab]                   = useState<Tab>("overview");
  const [isLoading, setIsLoading]       = useState(true);
  const [proposalsMap, setProposalsMap] = useState<Record<string, Proposal[]>>({});
  const [proposals, setProposals]       = useState<Proposal[]>([]);
  const [analyzing, setAnalyzing]       = useState(false);
  const [metricsMap, setMetricsMap]     = useState<Record<string, PerformanceMetric[]>>({});
  const [toolsMap, setToolsMap]         = useState<Record<string, ToolUsage[]>>({});
  const [totalsMap, setTotalsMap]       = useState<Record<string, { interactions: number; confirmed: number; rejected: number; correction_rate: number }>>({});
  const [execEvents, setExecEvents]     = useState<ExecutionEvent[]>([]);
  const [historyVersions, setHistory]   = useState<PromptVersion[]>([]);
  const [isDark, setIsDark]             = useState<boolean>(() => localStorage.getItem("pg_theme") !== "light");
  const didAutoSelect = useRef(false);
  const T = isDark ? DARK : LIGHT;

  const toggleTheme = () => {
    const next = !isDark;
    setIsDark(next);
    localStorage.setItem("pg_theme", next ? "dark" : "light");
  };

  const deletePlugin = async (pluginId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm(`Delete plugin "${pluginId}"? This cannot be undone.`)) return;
    try {
      await fetch(`${API_BASE}/api/plugins/${pluginId}`, { method: "DELETE" });
      setPlugins(ps => ps.filter(p => p.id !== pluginId));
      if (selected?.id === pluginId) setSelected(null);
    } catch { alert("Delete failed — check server logs."); }
  };

  const loadPluginData = useCallback(async (p: Plugin) => {
    // Stats (interactions + tool usage) — real API
    try {
      const res  = await fetch(`${API_BASE}/api/plugins/${p.id}/stats?days=14`);
      const data = await res.json();
      if (data.success) {
        setMetricsMap(prev => ({ ...prev, [p.id]: data.interactions || [] }));
        setToolsMap(prev => ({ ...prev, [p.id]: data.tool_usage || [] }));
        setTotalsMap(prev => ({ ...prev, [p.id]: data.totals || { interactions: 0, confirmed: 0, rejected: 0, correction_rate: 0 } }));
      }
    } catch {}

    // Prompt history — real API
    try {
      const res  = await fetch(`${API_BASE}/api/plugins/${p.id}/prompt-history`);
      const data = await res.json();
      if (data.success && data.history.length > 0) {
        setHistory(data.history.map((h: Record<string, unknown>) => ({
          version:                h.version as number,
          approved_at:            h.approved_at as string,
          approved_by:            h.approved_by as string,
          correction_rate_before: h.correction_rate_before as number | undefined,
          correction_rate_after:  h.correction_rate_after  as number | undefined,
          summary:                h.summary as string,
          prompt_snippet:         ((h.prompt as string) || "").slice(0, 140) + "…",
        })));
      } else {
        setHistory([]);
      }
    } catch { setHistory([]); }

    // Proposals — real API (LLM analysis runs in background)
    try {
      const res  = await fetch(`${API_BASE}/api/plugins/${p.id}/proposals`);
      const data = await res.json();
      if (data.success) {
        const all = [...(data.pending || []), ...(data.resolved || [])];
        setProposals(all);
        setProposalsMap(prev => ({ ...prev, [p.id]: all }));
        setAnalyzing(data.analyzing ?? false);
      } else {
        setProposals([]);
      }
    } catch { setProposals([]); }

    // Execution log — real API
    try {
      const res  = await fetch(`${API_BASE}/api/plugins/${p.id}/execution-log`);
      const data = await res.json();
      if (data.success) setExecEvents(data.events || []);
    } catch { setExecEvents([]); }
  }, []);

  // Load fleet-level proposal counts for all plugins
  const loadFleetProposals = useCallback(async (plugins: Plugin[]) => {
    const results = await Promise.allSettled(
      plugins.map(p =>
        fetch(`${API_BASE}/api/plugins/${p.id}/proposals`)
          .then(r => r.json())
          .then(data => ({ id: p.id, all: data.success ? [...(data.pending || []), ...(data.resolved || [])] : [] }))
      )
    );
    const map: Record<string, Proposal[]> = {};
    results.forEach(r => { if (r.status === "fulfilled") map[r.value.id] = r.value.all; });
    setProposalsMap(prev => ({ ...prev, ...map }));
  }, []);

  useEffect(() => {
    fetch(`${API_BASE}/api/plugins`)
      .then(r => r.json())
      .catch(() => ({ plugins: [] }))
      .then(d => {
        // Use real data from API — no mock fallbacks
        const loaded: Plugin[] = (d.plugins || []).map((p: Plugin) => ({
          ...p,
          mode:              p.mode              ?? "action",
          llm_model:         p.llm_model         ?? null,
          domain_classes:    p.domain_classes    ?? p.collections ?? [],
          write_permissions: p.write_permissions ?? [],
          session_cache_ttl: p.session_cache_ttl ?? 300,
          system_prompt:     p.system_prompt     ?? "",
          has_code:          p.has_code          ?? false,
          generated_tools:   p.generated_tools   ?? [],
          improvement_policy: p.improvement_policy ?? null,
        }));

        setPlugins(loaded);

        if (initialPluginId && !didAutoSelect.current) {
          const match = loaded.find(p => p.id === initialPluginId);
          if (match) { didAutoSelect.current = true; setSelected(match); setTab("console"); loadPluginData(match); }
        }

        // Load fleet-level proposal counts in background
        loadFleetProposals(loaded);
      })
      .finally(() => setIsLoading(false));
  }, [initialPluginId, loadPluginData, loadFleetProposals]);

  const selectPlugin = useCallback((p: Plugin) => { setSelected(p); setTab("overview"); loadPluginData(p); }, [loadPluginData]);

  const handleToggle = (active: boolean) => {
    if (!selected) return;
    fetch(`${API_BASE}/api/plugins/${selected.id}/${active ? "activate" : "deactivate"}`, { method: "POST" }).catch(() => {});
    const updated = { ...selected, active };
    setSelected(updated);
    setPlugins(ps => ps.map(p => p.id === selected.id ? updated : p));
  };

  const handleProposalAction = async (id: string, action: "approved" | "rejected") => {
    if (!selected) return;
    setProposals(ps => ps.map(p => p.id === id ? { ...p, status: action } : p));
    try {
      const res  = await fetch(`${API_BASE}/api/plugins/${selected.id}/proposals/action`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ proposal_id: id, action }) });
      const data = await res.json();
      if (!data.success) {
        setProposals(ps => ps.map(p => p.id === id ? { ...p, status: "pending" } : p));
        alert(`Failed to ${action} proposal: ${data.detail || "unknown error"}`);
      }
    } catch { setProposals(ps => ps.map(p => p.id === id ? { ...p, status: "pending" } : p)); }
  };

  const handleAnalyze = async () => {
    if (!selected) return;
    setAnalyzing(true);
    try {
      await fetch(`${API_BASE}/api/plugins/${selected.id}/proposals/analyze`, { method: "POST" });
      // Reload after short delay to pick up new proposals
      setTimeout(() => loadPluginData(selected), 4000);
    } catch {}
  };

  const handleConfigSaved = (patch: Partial<Plugin>) => {
    if (!selected) return;
    const updated = { ...selected, ...patch };
    setSelected(updated);
    setPlugins(ps => ps.map(p => p.id === selected.id ? updated : p));
  };

  const pendingTotal = proposals.filter(p => p.status === "pending").length;
  const fleetPending = Object.values(proposalsMap).flat().filter(p => p.status === "pending").length;

  const TABS: { id: Tab; label: string; icon: React.ReactNode; show: boolean; badge?: number }[] = [
    { id: "overview",    label: "Overview",       icon: <Activity      style={{ width: 13, height: 13 }} />, show: true },
    { id: "performance", label: "Performance",    icon: <TrendingUp    style={{ width: 13, height: 13 }} />, show: true },
    { id: "proposals",   label: "Proposals",      icon: <Brain         style={{ width: 13, height: 13 }} />, show: true, badge: pendingTotal },
    { id: "execution",   label: "Execution",      icon: <Terminal      style={{ width: 13, height: 13 }} />, show: !!selected?.has_code },
    { id: "history",     label: "Prompt history", icon: <History       style={{ width: 13, height: 13 }} />, show: true },
    { id: "console",     label: "Console",        icon: <MessageSquare style={{ width: 13, height: 13 }} />, show: true },
  ];

  return (
    <div data-theme={isDark ? "dark" : "light"} style={{ height: "100%", display: "flex", flexDirection: "column", background: T.bg, color: T.textPri, fontFamily: "'IBM Plex Mono', 'Fira Code', monospace", transition: "background 0.2s, color 0.2s" }}>
      {/* Header */}
      <div style={{ borderBottom: `1px solid ${T.border}`, background: T.bgRaised, padding: "13px 22px", flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 11 }}>
          {selected && <button onClick={() => setSelected(null)} style={{ display: "flex", alignItems: "center", gap: 5, background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)", fontSize: 12, fontFamily: "inherit" }}><ArrowLeft style={{ width: 14, height: 14 }} /></button>}
          <div style={{ width: 30, height: 30, borderRadius: 7, fontSize: 14, display: "flex", alignItems: "center", justifyContent: "center", background: C.blue.bg, border: `1px solid ${C.blue.border}` }}>{selected ? selected.icon : "📊"}</div>
          <div>
            <h1 style={{ margin: 0, fontSize: 14, fontWeight: 700, color: "var(--text-pri)", letterSpacing: "-0.01em", fontFamily: "inherit" }}>{selected ? selected.name : "Plugin Dashboard"}</h1>
            <p style={{ margin: 0, fontSize: 10, color: "var(--text-muted)" }}>{selected ? `ATLAS · ${selected.id}` : `ATLAS · ${plugins.length} registered · ${plugins.filter(p => p.active).length} active`}</p>
          </div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          {selected && pendingTotal > 0 && <div style={{ padding: "5px 12px", borderRadius: 6, display: "flex", alignItems: "center", gap: 6, background: C.amber.bg, border: `1px solid ${C.amber.border}`, fontSize: 12, color: C.amber.text, fontWeight: 600 }}><Sparkles style={{ width: 12, height: 12 }} />{pendingTotal} proposal{pendingTotal !== 1 ? "s" : ""} pending</div>}
          <button onClick={toggleTheme} style={{ padding: "5px 10px", borderRadius: 6, border: `1px solid ${T.border}`, background: T.bgCard, color: T.textMuted, cursor: "pointer", display: "flex", alignItems: "center", gap: 5, fontSize: 12, fontFamily: "inherit" }}>
            {isDark ? <Sun style={{ width: 13, height: 13 }} /> : <Moon style={{ width: 13, height: 13 }} />}
          </button>
          <button onClick={() => selected ? loadPluginData(selected) : window.location.reload()} style={{ padding: "5px 10px", borderRadius: 6, border: `1px solid ${T.border}`, background: T.bgCard, color: T.textMuted, cursor: "pointer", display: "flex", alignItems: "center", gap: 5, fontSize: 12, fontFamily: "inherit" }}><RefreshCw style={{ width: 12, height: 12 }} /></button>
        </div>
      </div>

      {/* Fleet view */}
      {!selected ? (
        <div style={{ flex: 1, overflowY: "auto", padding: 22, background: T.bg }}>
          {isLoading
            ? <div style={{ display: "flex", justifyContent: "center", paddingTop: 60 }}><RefreshCw style={{ width: 20, height: 20, color: "var(--text-muted)", animation: "spin 1s linear infinite" }} /></div>
            : plugins.length === 0
              ? <EmptyState icon={<Zap style={{ width: 28, height: 28 }} />} title="No plugins registered yet" sub="Use the App Onboarding wizard to register your first application." />
              : <>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 10, marginBottom: 22 }}>
                    <StatCard label="Registered" value={plugins.length}                                        color="green" />
                    <StatCard label="Active"      value={plugins.filter(p => p.active).length}                color="green" />
                    <StatCard label="Learning"    value={plugins.filter(p => p.improvement_policy?.enabled).length} color="blue" />
                    <StatCard label="Proposals"   value={fleetPending}                                         color={fleetPending > 0 ? "amber" : "green"} />
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(290px,1fr))", gap: 12 }}>
                    {plugins.map(p => (
                      <FleetCard
                        key={p.id}
                        plugin={p}
                        metrics={metricsMap[p.id] || []}
                        proposals={proposalsMap[p.id] || []}
                        onSelect={() => selectPlugin(p)}
                        onToggle={active => {
                          fetch(`${API_BASE}/api/plugins/${p.id}/${active ? "activate" : "deactivate"}`, { method: "POST" }).catch(() => {});
                          setPlugins(ps => ps.map(x => x.id === p.id ? { ...x, active } : x));
                        }}
                        onDelete={e => deletePlugin(p.id, e)}
                        isDark={isDark}
                      />
                    ))}
                  </div>
                </>
          }
        </div>
      ) : (
        /* Detail view */
        <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
          <div style={{ borderBottom: `1px solid ${T.border}`, background: T.bgRaised, padding: "0 22px", display: "flex", alignItems: "center", gap: 2, flexShrink: 0 }}>
            {TABS.filter(t => t.show).map(t => (
              <button key={t.id} onClick={() => setTab(t.id)} style={{ padding: "11px 14px", borderRadius: "6px 6px 0 0", cursor: "pointer", border: "none", borderBottom: tab === t.id ? `2px solid ${C.green.text}` : "2px solid transparent", background: tab === t.id ? T.bgCard : "transparent", color: tab === t.id ? T.textPri : T.textMuted, fontSize: 12, fontWeight: tab === t.id ? 600 : 400, display: "flex", alignItems: "center", gap: 6, transition: "all 0.15s", fontFamily: "inherit" }}>
                {t.icon}{t.label}
                {t.badge !== undefined && t.badge > 0 && <span style={{ width: 16, height: 16, borderRadius: "50%", fontSize: 9, fontWeight: 700, background: C.amber.text, color: "var(--bg)", display: "flex", alignItems: "center", justifyContent: "center" }}>{t.badge}</span>}
              </button>
            ))}
          </div>
          <div style={{ flex: 1, overflowY: "auto", padding: 22, background: T.bg }}>
            <div style={{ maxWidth: tab === "console" ? 860 : 740, margin: "0 auto" }}>
              {tab === "overview"    && <TabOverview    plugin={selected} onToggle={handleToggle} onConfigSaved={handleConfigSaved} />}
              {tab === "performance" && <TabPerformance plugin={selected} metrics={metricsMap[selected.id] || []} tools={toolsMap[selected.id] || []} totals={totalsMap[selected.id] || { interactions: 0, confirmed: 0, rejected: 0, correction_rate: 0 }} />}
              {tab === "proposals"   && <TabProposals   proposals={proposals} analyzing={analyzing} onAction={handleProposalAction} onAnalyze={handleAnalyze} />}
              {tab === "execution"   && <TabExecution   plugin_id={selected.id} events={execEvents} onRefresh={() => loadPluginData(selected)} />}
              {tab === "history"     && <TabHistory     versions={historyVersions} />}
              {tab === "console"     && <TabConsole     plugin={selected} />}
            </div>
          </div>
        </div>
      )}

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
        [data-theme="dark"] {
          --bg: #0b0e18; --bg-raised: #10131f; --bg-card: #131929;
          --border: #1e2740; --border-sub: #1a2035;
          --text-pri: #e2e6f0; --text-sec: #8892aa; --text-muted: #4a5570; --text-dim: #2a3045;
          --msg-bg: #0f1522;
        }
        [data-theme="light"] {
          --bg: #f4f6fb; --bg-raised: #ffffff; --bg-card: #f8fafc;
          --border: #dde2ef; --border-sub: #e8ecf5;
          --text-pri: #111827; --text-sec: #374151; --text-muted: #6b7280; --text-dim: #9ca3af;
          --msg-bg: #eef2f7;
        }
      `}</style>
    </div>
  );
}