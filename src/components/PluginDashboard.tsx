import { useState, useEffect, useCallback, useRef } from "react";
import {
  Activity, AlertTriangle, ArrowLeft, ArrowRight,
  Brain, Check, ChevronDown,
  Code, FileCode, GitBranch, History,
  Play, RefreshCw, Sparkles, Square,
  Terminal, TrendingDown, TrendingUp, Wrench,
  X, Zap, ToggleLeft, ToggleRight,
  MessageSquare, Loader2, Send, BookOpen, Layers, ChevronRight,
  ExternalLink, Copy, ThumbsUp, Radar,
} from "lucide-react";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

// ── Types ──────────────────────────────────────────────────────────────────

type Tab = "overview" | "performance" | "proposals" | "execution" | "history" | "console";

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
  code_filename?: string;
  generated_tools?: {
    name: string;
    signature: string;
    description?: string;
    sparql_template?: string;
    arg_types?: Record<string, string>;
    return_type?: string;
    source?: "ontology" | "code_analysis";
  }[];
  improvement_policy?: {
    enabled: boolean;
    correction_threshold: number;
    tool_usage_window_days: number;
    prompt_revision_requires_review: boolean;
    track_execution_failures: boolean;
    auto_propose_tool_additions: boolean;
  };
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
  diff?: { before: string; after: string };
  correction_rate_at_trigger?: number;
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
  correction_rate_before: number;
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

// ── Mock data ──────────────────────────────────────────────────────────────

function mockMetrics(days: number): PerformanceMetric[] {
  const out: PerformanceMetric[] = [];
  let rate = 0.38;
  for (let i = days; i >= 0; i--) {
    const d = new Date(); d.setDate(d.getDate() - i);
    const total = 8 + Math.floor(Math.random() * 20);
    const approved = Math.floor(total * (1 - rate) * (0.85 + Math.random() * 0.3));
    const rejected = Math.floor((total - approved) * 0.7);
    const modified = Math.max(0, total - approved - rejected);
    rate = Math.max(0.05, rate - 0.008 + (Math.random() - 0.5) * 0.04);
    out.push({
      date: d.toLocaleDateString("en-US", { month: "short", day: "numeric" }),
      interactions: total, approved, rejected, modified,
      correction_rate: (rejected + modified) / total,
    });
  }
  return out;
}

function mockToolUsage(classes: string[], hasCode: boolean): ToolUsage[] {
  const tools: ToolUsage[] = [];
  for (const cls of classes) {
    tools.push(
      { name: `get_${cls.toLowerCase()}_by_id`, calls: Math.floor(Math.random() * 120) + 5, source: "ontology" },
      { name: `list_${cls.toLowerCase()}s`, calls: Math.floor(Math.random() * 80) + 2, source: "ontology" },
    );
  }
  if (hasCode) {
    tools.push(
      { name: "program_start",  calls: Math.floor(Math.random() * 30) + 5,  source: "code_analysis" },
      { name: "program_stop",   calls: Math.floor(Math.random() * 28) + 4,  source: "code_analysis" },
      { name: "program_status", calls: Math.floor(Math.random() * 60) + 10, source: "code_analysis" },
    );
  }
  return tools.sort((a, b) => b.calls - a.calls);
}

function mockProposals(): Proposal[] {
  return [
    {
      id: "prop_001", type: "prompt_revision", status: "pending",
      triggered_by: "Correction rate reached 31% (threshold: 25%) over 14 days",
      created_at: new Date(Date.now() - 2 * 86400000).toISOString(),
      correction_rate_at_trigger: 0.31,
      summary: "Tighten relationship classification — REFERENCES vs RELATED_TO confusion",
      detail: "Analysis of 43 rejected edges shows the agent consistently proposes RELATED_TO when evidence clearly supports REFERENCES. The prompt does not define the distinction.",
      diff: {
        before: `You are a domain specialist. Suggest relationships between artifacts based on semantic similarity.`,
        after:  `You are a domain specialist. Suggest relationships between artifacts based on semantic similarity.\n\nRelationship rules:\n- Use REFERENCES when artifact A explicitly cites or depends on artifact B\n- Use RELATED_TO only when the connection is thematic with no direct dependency\n- When in doubt, prefer REFERENCES over RELATED_TO for module→TTP links`,
      },
    },
    {
      id: "prop_002", type: "tool_addition", status: "pending",
      triggered_by: "Operators asked 'what modules cover T1558?' 18 times — no matching tool",
      created_at: new Date(Date.now() - 5 * 86400000).toISOString(),
      summary: "Add get_modules_by_technique(technique_id) tool",
      detail: "Operators repeatedly query for modules mapped to a specific MITRE technique ID. No direct tool exists — operators filter manually from list results.",
      diff: {
        before: "# No matching tool",
        after:  `def get_modules_by_technique(technique_id: str) -> List[LibraryModule]:\n    """Find all LibraryModules that REFERENCES a given MITRE technique ID."""\n    # SPARQL: SELECT ?m WHERE { ?m rel:REFERENCES ?t . ?t proto:mitreId "{technique_id}" }`,
      },
    },
    {
      id: "prop_003", type: "exec_fix", status: "pending",
      triggered_by: "program_start failed 4 times — working directory not found",
      created_at: new Date(Date.now() - 86400000).toISOString(),
      summary: "Prepend mkdir -p to start command",
      detail: "Execution log shows 4 consecutive failures with 'No such file or directory'. The start command assumes the working directory already exists.",
      diff: {
        before: "python -m kerberoast --target $DC_HOST",
        after:  "mkdir -p /home/kane/atlas/operators/kerberoast && python -m kerberoast --target $DC_HOST",
      },
    },
    {
      id: "prop_004", type: "prompt_revision", status: "approved",
      triggered_by: "Manual trigger by operator",
      created_at: new Date(Date.now() - 8 * 86400000).toISOString(),
      correction_rate_at_trigger: 0.27,
      summary: "Added explicit no-hallucination rule for artifact names",
      detail: "Operator flagged that the agent was inventing module names when no graph results were returned.",
    },
  ];
}

function mockExecLog(): ExecutionEvent[] {
  return [
    { id: "e1", type: "start",   timestamp: new Date(Date.now() - 3600000).toISOString(), message: "Program started successfully", duration_ms: 1240 },
    { id: "e2", type: "ready",   timestamp: new Date(Date.now() - 3598000).toISOString(), message: "stdout: 'Ready for connections'" },
    { id: "e3", type: "stop",    timestamp: new Date(Date.now() - 1800000).toISOString(), message: "SIGTERM sent — clean exit", exit_code: 0 },
    { id: "e4", type: "start",   timestamp: new Date(Date.now() - 1200000).toISOString(), message: "Program started successfully", duration_ms: 1190 },
    { id: "e5", type: "failure", timestamp: new Date(Date.now() - 600000).toISOString(),  message: "Exit code 1 — see stderr", exit_code: 1,
      stderr_tail: "Traceback (most recent call last):\n  File \"kerberoast.py\", line 44, in run\n    assert dc_host, 'DC_HOST env var required'\nAssertionError: DC_HOST env var required" },
    { id: "e6", type: "start",   timestamp: new Date(Date.now() - 300000).toISOString(),  message: "Program started successfully", duration_ms: 1310 },
    { id: "e7", type: "ready",   timestamp: new Date(Date.now() - 298000).toISOString(),  message: "stdout: 'Ready for connections'" },
  ];
}

function mockHistory(): PromptVersion[] {
  return [
    {
      version: 1, approved_by: "kane.pickrell",
      approved_at: new Date(Date.now() - 30 * 86400000).toISOString(),
      correction_rate_before: 0, correction_rate_after: 0.38,
      summary: "Initial registration",
      prompt_snippet: "You are a domain specialist for the 318th RANS knowledge graph...",
    },
    {
      version: 2, approved_by: "kane.pickrell",
      approved_at: new Date(Date.now() - 8 * 86400000).toISOString(),
      correction_rate_before: 0.27, correction_rate_after: 0.19,
      summary: "Added explicit no-hallucination rule for artifact names",
      prompt_snippet: "...Never invent artifact names or relationships not found via tools. If a tool returns no results, say so explicitly...",
    },
  ];
}

// ── Shared primitives ──────────────────────────────────────────────────────

function Tag({ color, children, mono = false }: { color: keyof typeof C; children: React.ReactNode; mono?: boolean }) {
  const c = C[color];
  return (
    <span style={{
      padding: "2px 8px", borderRadius: 4, fontSize: 11, fontWeight: 500,
      background: c.bg, border: `1px solid ${c.border}`, color: c.text,
      fontFamily: mono ? "monospace" : "inherit",
    }}>
      {children}
    </span>
  );
}

function StatCard({ label, value, sub, color = "green" }: { label: string; value: string | number; sub?: string; color?: keyof typeof C }) {
  return (
    <div style={{ padding: "14px 16px", borderRadius: 10, border: "1px solid #1e2740", background: "#131929" }}>
      <div style={{ fontSize: 22, fontWeight: 700, color: C[color].text, fontFamily: "monospace", letterSpacing: "-0.02em" }}>{value}</div>
      <div style={{ fontSize: 10, fontWeight: 700, color: "#4a5370", marginTop: 3, textTransform: "uppercase", letterSpacing: "0.07em" }}>{label}</div>
      {sub && <div style={{ fontSize: 11, color: "#4a5370", marginTop: 2 }}>{sub}</div>}
    </div>
  );
}

function MiniBar({ value, max, color }: { value: number; max: number; color: string }) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  return (
    <div style={{ flex: 1, height: 5, borderRadius: 3, background: "#1e2740", overflow: "hidden" }}>
      <div style={{ width: `${pct}%`, height: "100%", background: color, borderRadius: 3, transition: "width 0.4s ease" }} />
    </div>
  );
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
          <stop offset="100%" stopColor={color} stopOpacity="0" />
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
    <pre style={{
      fontSize: 11, fontFamily: "monospace", lineHeight: 1.7,
      background: "#0b0e18", border: "1px solid #1e2740",
      borderRadius: 7, padding: "10px 12px", margin: 0,
      overflowX: "auto", whiteSpace: "pre-wrap", wordBreak: "break-word",
    }}>
      {al.map((line, i) => {
        const isAdded   = added.includes(line);
        const isRemoved = removed.includes(line);
        return (
          <div key={i} style={{
            background: isAdded ? "rgba(110,190,70,0.12)" : isRemoved ? "rgba(248,113,113,0.1)" : "transparent",
            color: isAdded ? "#6EBE46" : isRemoved ? "#f87171" : "#8892aa",
            paddingLeft: 4, marginLeft: -4,
          }}>
            <span style={{ opacity: 0.5, marginRight: 8, userSelect: "none" }}>
              {isAdded ? "+" : isRemoved ? "-" : " "}
            </span>
            {line}
          </div>
        );
      })}
    </pre>
  );
}

// ── Fleet card ─────────────────────────────────────────────────────────────

function FleetCard({ plugin, metrics, proposals, onSelect, onToggle }: {
  plugin: Plugin;
  metrics: PerformanceMetric[];
  proposals: Proposal[];
  onSelect: () => void;
  onToggle: (v: boolean) => void;
}) {
  const latest   = metrics.slice(-1)[0];
  const rateData = metrics.map(m => m.correction_rate);
  const trend    = rateData.length > 3 ? rateData[rateData.length - 1] - rateData[rateData.length - 4] : 0;
  const pending  = proposals.filter(p => p.status === "pending").length;
  const policy   = plugin.improvement_policy;
  const over     = policy?.enabled && latest && latest.correction_rate > (policy.correction_threshold ?? 0.25);

  return (
    <div
      onClick={onSelect}
      style={{
        padding: "16px 18px", borderRadius: 12, cursor: "pointer",
        border: `1px solid ${over ? C.amber.border : plugin.active ? C.green.border : "#1e2740"}`,
        background: over ? C.amber.bg : "#10131f",
        transition: "border-color 0.18s, background 0.18s",
        position: "relative",
      }}
    >
      {pending > 0 && (
        <div style={{
          position: "absolute", top: 12, right: 12,
          width: 18, height: 18, borderRadius: "50%",
          background: C.amber.text, display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 10, fontWeight: 700, color: "#0b0e18",
        }}>
          {pending}
        </div>
      )}

      <div style={{ display: "flex", alignItems: "flex-start", gap: 12, marginBottom: 14 }}>
        <div style={{
          width: 40, height: 40, borderRadius: 9, fontSize: 20,
          display: "flex", alignItems: "center", justifyContent: "center",
          border: "1px solid #1e2740", background: "#0b0e18", flexShrink: 0,
        }}>
          {plugin.icon}
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 3, flexWrap: "wrap" }}>
            <span style={{ fontSize: 13, fontWeight: 700, color: "#e2e6f0" }}>{plugin.name}</span>
            <span style={{
              padding: "1px 6px", borderRadius: 3, fontSize: 9, fontWeight: 700, fontFamily: "monospace",
              background: plugin.active ? C.green.bg : "#1e2740",
              border: `1px solid ${plugin.active ? C.green.border : "#252b3d"}`,
              color: plugin.active ? C.green.text : "#4a5370",
            }}>
              {plugin.active ? "LIVE" : "OFF"}
            </span>
            {policy?.enabled && <span style={{ padding: "1px 6px", borderRadius: 3, fontSize: 9, fontWeight: 700, background: C.blue.bg, border: `1px solid ${C.blue.border}`, color: C.blue.text }}>LEARNING</span>}
            {plugin.has_code && <span style={{ padding: "1px 6px", borderRadius: 3, fontSize: 9, fontWeight: 700, background: C.teal.bg, border: `1px solid ${C.teal.border}`, color: C.teal.text }}>EXEC</span>}
          </div>
          <p style={{ fontSize: 11, color: "#4a5370", margin: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {plugin.description}
          </p>
        </div>
      </div>

      <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between" }}>
        <div>
          <div style={{ fontSize: 10, color: "#4a5370", marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.06em" }}>
            Correction rate (14d)
          </div>
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
          <span style={{ fontSize: 11, color: C.amber.text }}>
            ⚡ Rate above threshold — {pending} proposal{pending !== 1 ? "s" : ""} queued
          </span>
        </div>
      )}
    </div>
  );
}

// ── Tab: Overview ──────────────────────────────────────────────────────────

function TabOverview({ plugin, onToggle }: { plugin: Plugin; onToggle: (v: boolean) => void }) {
  const policy = plugin.improvement_policy;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
        {/* Manifest */}
        <div style={{ border: "1px solid #1e2740", borderRadius: 10, overflow: "hidden", background: "#131929" }}>
          <div style={{ padding: "10px 14px", borderBottom: "1px solid #1a2035", fontSize: 10, fontWeight: 700, color: "#4a5370", textTransform: "uppercase", letterSpacing: "0.07em" }}>Manifest</div>
          {[
            { k: "App ID", v: plugin.id,                    mono: true },
            { k: "Mode",   v: plugin.mode || "action",       mono: true },
            { k: "LLM",    v: plugin.llm_model || "—",       mono: true },
            { k: "Cache",  v: `${plugin.session_cache_ttl || 300}s`, mono: true },
          ].map(row => (
            <div key={row.k} style={{ display: "flex", alignItems: "center", padding: "8px 14px", borderBottom: "1px solid #1a2035" }}>
              <span style={{ fontSize: 10, fontWeight: 700, color: "#4a5370", width: 56, flexShrink: 0, textTransform: "uppercase", letterSpacing: "0.05em" }}>{row.k}</span>
              <span style={{ fontSize: 12, color: "#e2e6f0", fontFamily: row.mono ? "monospace" : "inherit" }}>{row.v}</span>
            </div>
          ))}
          <div style={{ padding: "8px 14px", borderBottom: "1px solid #1a2035" }}>
            <span style={{ fontSize: 10, fontWeight: 700, color: "#4a5370", textTransform: "uppercase", letterSpacing: "0.05em", display: "block", marginBottom: 5 }}>Domain</span>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
              {plugin.domain_classes?.map(c => <Tag key={c} color="green">{c}</Tag>) || <span style={{ fontSize: 11, color: "#4a5370" }}>None</span>}
            </div>
          </div>
          <div style={{ padding: "8px 14px" }}>
            <span style={{ fontSize: 10, fontWeight: 700, color: "#4a5370", textTransform: "uppercase", letterSpacing: "0.05em", display: "block", marginBottom: 5 }}>Permissions</span>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
              {plugin.write_permissions?.length
                ? plugin.write_permissions.map(p => <Tag key={p} color="amber">{p}</Tag>)
                : <span style={{ fontSize: 11, color: "#4a5370" }}>Read-only</span>}
            </div>
          </div>
        </div>

        {/* Controls */}
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <div style={{ border: "1px solid #1e2740", borderRadius: 10, overflow: "hidden", background: "#131929" }}>
            <div style={{ padding: "10px 14px", borderBottom: "1px solid #1a2035", fontSize: 10, fontWeight: 700, color: "#4a5370", textTransform: "uppercase", letterSpacing: "0.07em" }}>Agent status</div>
            <div style={{ padding: "14px" }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
                <div>
                  <div style={{ fontSize: 12, fontWeight: 600, color: "#e2e6f0", marginBottom: 2 }}>Plugin endpoint</div>
                  <div style={{ fontSize: 10, color: "#4a5370", fontFamily: "monospace" }}>POST /api/plugins/{plugin.id}/agent</div>
                </div>
                <button onClick={() => onToggle(!plugin.active)} style={{
                  display: "flex", alignItems: "center", gap: 5, padding: "5px 12px", borderRadius: 6,
                  fontSize: 12, fontWeight: 600, cursor: "pointer",
                  border: `1px solid ${plugin.active ? C.green.border : "#252b3d"}`,
                  background: plugin.active ? C.green.bg : "#1e2740",
                  color: plugin.active ? C.green.text : "#8892aa", transition: "all 0.15s",
                }}>
                  {plugin.active
                    ? <><ToggleRight style={{ width: 13, height: 13 }} /> Active</>
                    : <><ToggleLeft  style={{ width: 13, height: 13 }} /> Inactive</>}
                </button>
              </div>
            </div>
          </div>

          {plugin.has_code && (
            <div style={{ border: "1px solid #1e2740", borderRadius: 10, overflow: "hidden", background: "#131929" }}>
              <div style={{ padding: "10px 14px", borderBottom: "1px solid #1a2035", fontSize: 10, fontWeight: 700, color: "#4a5370", textTransform: "uppercase", letterSpacing: "0.07em" }}>Program</div>
              <div style={{ padding: "14px" }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  <div>
                    <div style={{ fontSize: 12, color: C.teal.text, fontFamily: "monospace", marginBottom: 4 }}>{plugin.code_filename}</div>
                    <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                      <div style={{ width: 6, height: 6, borderRadius: "50%", background: C.green.text, boxShadow: `0 0 6px ${C.green.text}` }} />
                      <span style={{ fontSize: 11, color: C.green.text }}>Running</span>
                    </div>
                  </div>
                  <div style={{ display: "flex", gap: 6 }}>
                    <button style={{ padding: "5px 10px", borderRadius: 6, border: `1px solid ${C.green.border}`, background: C.green.bg, color: C.green.text, cursor: "pointer", fontSize: 11, display: "flex", alignItems: "center", gap: 4 }}>
                      <Play style={{ width: 10, height: 10 }} /> Start
                    </button>
                    <button style={{ padding: "5px 10px", borderRadius: 6, border: `1px solid ${C.red.border}`, background: C.red.bg, color: C.red.text, cursor: "pointer", fontSize: 11, display: "flex", alignItems: "center", gap: 4 }}>
                      <Square style={{ width: 10, height: 10 }} /> Stop
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* System prompt */}
      <div style={{ border: "1px solid #1e2740", borderRadius: 10, overflow: "hidden", background: "#131929" }}>
        <div style={{ padding: "10px 14px", borderBottom: "1px solid #1a2035", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <span style={{ fontSize: 10, fontWeight: 700, color: "#4a5370", textTransform: "uppercase", letterSpacing: "0.07em" }}>System prompt · v2</span>
          <span style={{ fontSize: 11, color: "#4a5370" }}>Revised 8 days ago</span>
        </div>
        <pre style={{
          padding: "12px 14px", margin: 0, fontSize: 11, color: "#8892aa",
          fontFamily: "monospace", lineHeight: 1.7, overflowY: "auto",
          maxHeight: 130, whiteSpace: "pre-wrap", wordBreak: "break-word", background: "transparent",
        }}>
          {plugin.system_prompt || "You are a domain specialist for the 318th RANS knowledge graph.\n\nAlways use graph tools — never invent artifact names or relationships not found via tools. If a tool returns no results, say so explicitly."}
        </pre>
      </div>

      {/* Learning policy */}
      {policy && (
        <div style={{ padding: "14px 16px", borderRadius: 10, border: `1px solid ${policy.enabled ? C.blue.border : "#1e2740"}`, background: policy.enabled ? C.blue.bg : "#131929" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: policy.enabled ? 10 : 0 }}>
            <Brain style={{ width: 15, height: 15, color: policy.enabled ? C.blue.text : "#4a5370" }} />
            <span style={{ fontSize: 13, fontWeight: 600, color: "#e2e6f0" }}>Adaptive learning</span>
            <span style={{ marginLeft: "auto", fontSize: 11, color: policy.enabled ? C.blue.text : "#4a5370", fontWeight: 700 }}>
              {policy.enabled ? "ENABLED" : "DISABLED"}
            </span>
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

function TabPerformance({ plugin, metrics, tools }: { plugin: Plugin; metrics: PerformanceMetric[]; tools: ToolUsage[] }) {
  const totals  = metrics.reduce((a, m) => ({ interactions: a.interactions + m.interactions, approved: a.approved + m.approved, rejected: a.rejected + m.rejected, modified: a.modified + m.modified }), { interactions: 0, approved: 0, rejected: 0, modified: 0 });
  const latest  = metrics.slice(-1)[0];
  const policy  = plugin.improvement_policy;
  const maxCalls = Math.max(...tools.map(t => t.calls), 1);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 10 }}>
        <StatCard label="Interactions" value={totals.interactions} color="green" />
        <StatCard label="Approved" value={totals.approved} color="green" />
        <StatCard label="Rejected" value={totals.rejected} color="red" />
        <StatCard label="Current rate" value={latest ? `${Math.round(latest.correction_rate * 100)}%` : "—"}
          color={latest && policy?.enabled && latest.correction_rate > (policy.correction_threshold ?? 0.25) ? "amber" : "green"}
          sub={policy?.enabled ? `Threshold: ${Math.round((policy.correction_threshold) * 100)}%` : undefined} />
      </div>

      {/* Rate chart */}
      <div style={{ border: "1px solid #1e2740", borderRadius: 10, overflow: "hidden", background: "#131929" }}>
        <div style={{ padding: "12px 16px", borderBottom: "1px solid #1a2035", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <span style={{ fontSize: 12, fontWeight: 600, color: "#e2e6f0" }}>Correction rate over time</span>
          <span style={{ fontSize: 11, color: "#4a5370" }}>14-day window</span>
        </div>
        <div style={{ padding: "14px 16px", display: "flex", flexDirection: "column", gap: 5 }}>
          {policy?.enabled && (
            <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
              <div style={{ width: 16, height: 0, borderTop: `1px dashed ${C.amber.text}` }} />
              <span style={{ fontSize: 10, color: C.amber.text }}>Threshold {Math.round(policy.correction_threshold * 100)}%</span>
            </div>
          )}
          {metrics.slice(-14).map((m, i) => {
            const over = policy?.enabled && m.correction_rate > (policy.correction_threshold ?? 0.25);
            return (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span style={{ fontSize: 10, color: "#4a5370", width: 48, flexShrink: 0, fontFamily: "monospace" }}>{m.date}</span>
                <MiniBar value={m.correction_rate} max={0.6} color={over ? C.amber.text : C.green.text} />
                <span style={{ fontSize: 11, fontWeight: 600, fontFamily: "monospace", width: 34, flexShrink: 0, color: over ? C.amber.text : "#8892aa" }}>
                  {Math.round(m.correction_rate * 100)}%
                </span>
                <span style={{ fontSize: 10, color: "#4a5370", width: 18, flexShrink: 0, textAlign: "right" }}>{m.interactions}</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Tool heatmap */}
      <div style={{ border: "1px solid #1e2740", borderRadius: 10, overflow: "hidden", background: "#131929" }}>
        <div style={{ padding: "12px 16px", borderBottom: "1px solid #1a2035" }}>
          <span style={{ fontSize: 12, fontWeight: 600, color: "#e2e6f0" }}>Tool usage</span>
        </div>
        <div style={{ padding: "14px 16px", display: "flex", flexDirection: "column", gap: 7 }}>
          {tools.map(t => (
            <div key={t.name} style={{ display: "flex", alignItems: "center", gap: 10 }}>
              {t.source === "code_analysis"
                ? <Terminal style={{ width: 11, height: 11, color: C.teal.text, flexShrink: 0 }} />
                : <Code     style={{ width: 11, height: 11, color: C.green.text, flexShrink: 0 }} />}
              <span style={{ fontSize: 11, color: "#e2e6f0", fontFamily: "monospace", width: 200, flexShrink: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {t.name}
              </span>
              <MiniBar value={t.calls} max={maxCalls} color={t.source === "code_analysis" ? C.teal.text : C.green.text} />
              <span style={{ fontSize: 11, fontFamily: "monospace", color: "#8892aa", width: 34, flexShrink: 0, textAlign: "right" }}>{t.calls}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Tab: Proposals ─────────────────────────────────────────────────────────

function TabProposals({ proposals, onAction }: { proposals: Proposal[]; onAction: (id: string, action: "approved" | "rejected") => void }) {
  const [expanded, setExpanded] = useState<string | null>(null);

  const typeIcon: Record<Proposal["type"], React.ReactNode> = {
    prompt_revision: <Brain    style={{ width: 13, height: 13 }} />,
    tool_addition:   <Wrench   style={{ width: 13, height: 13 }} />,
    rule_rewrite:    <GitBranch style={{ width: 13, height: 13 }} />,
    exec_fix:        <Terminal style={{ width: 13, height: 13 }} />,
  };
  const typeColor: Record<Proposal["type"], keyof typeof C> = {
    prompt_revision: "blue", tool_addition: "purple", rule_rewrite: "amber", exec_fix: "teal",
  };
  const typeLabel: Record<Proposal["type"], string> = {
    prompt_revision: "Prompt revision", tool_addition: "Tool addition", rule_rewrite: "Rule rewrite", exec_fix: "Exec fix",
  };

  const pending  = proposals.filter(p => p.status === "pending");
  const resolved = proposals.filter(p => p.status !== "pending");

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {pending.length === 0 && (
        <div style={{ padding: 28, borderRadius: 10, textAlign: "center", border: "1px solid #1e2740", background: "#131929" }}>
          <Check style={{ width: 20, height: 20, color: C.green.text, margin: "0 auto 8px" }} />
          <p style={{ fontSize: 13, color: "#8892aa", margin: 0 }}>No pending proposals — improvement loop is healthy</p>
        </div>
      )}

      {pending.length > 0 && (
        <div>
          <div style={{ fontSize: 10, fontWeight: 700, color: "#4a5370", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 8 }}>
            Pending review ({pending.length})
          </div>
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
                        <span style={{ fontSize: 12, fontWeight: 600, color: "#e2e6f0" }}>{p.summary}</span>
                        <Tag color={col}>{typeLabel[p.type]}</Tag>
                        {p.correction_rate_at_trigger !== undefined && <Tag color="amber">{Math.round(p.correction_rate_at_trigger * 100)}% rate</Tag>}
                      </div>
                      <p style={{ margin: 0, fontSize: 11, color: "#4a5370", lineHeight: 1.5 }}>{p.triggered_by}</p>
                    </div>
                    <ChevronDown style={{ width: 13, height: 13, color: "#4a5370", flexShrink: 0, marginTop: 2, transform: open ? "rotate(180deg)" : "none", transition: "transform 0.2s" }} />
                  </div>
                  {open && (
                    <div style={{ borderTop: `1px solid ${C[col].border}`, padding: "14px" }}>
                      <p style={{ margin: "0 0 12px", fontSize: 12, color: "#8892aa", lineHeight: 1.6 }}>{p.detail}</p>
                      {p.diff && (
                        <div style={{ marginBottom: 14 }}>
                          <div style={{ fontSize: 10, fontWeight: 700, color: "#4a5370", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>Proposed diff</div>
                          <DiffView before={p.diff.before} after={p.diff.after} />
                        </div>
                      )}
                      <div style={{ display: "flex", gap: 8 }}>
                        <button onClick={e => { e.stopPropagation(); onAction(p.id, "approved"); }} style={{ padding: "6px 14px", borderRadius: 6, border: `1px solid ${C.green.border}`, background: C.green.bg, color: C.green.text, cursor: "pointer", fontSize: 12, fontWeight: 600, display: "flex", alignItems: "center", gap: 5 }}>
                          <Check style={{ width: 12, height: 12 }} /> Approve & apply
                        </button>
                        <button onClick={e => { e.stopPropagation(); onAction(p.id, "rejected"); }} style={{ padding: "6px 12px", borderRadius: 6, border: `1px solid ${C.red.border}`, background: C.red.bg, color: C.red.text, cursor: "pointer", fontSize: 12, fontWeight: 600, display: "flex", alignItems: "center", gap: 5 }}>
                          <X style={{ width: 12, height: 12 }} /> Reject
                        </button>
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
          <div style={{ fontSize: 10, fontWeight: 700, color: "#4a5370", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 8 }}>
            Resolved ({resolved.length})
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
            {resolved.map(p => (
              <div key={p.id} style={{ padding: "10px 14px", borderRadius: 8, display: "flex", alignItems: "center", gap: 10, border: "1px solid #1e2740", background: "#131929" }}>
                {p.status === "approved"
                  ? <Check style={{ width: 13, height: 13, color: C.green.text, flexShrink: 0 }} />
                  : <X     style={{ width: 13, height: 13, color: C.red.text,   flexShrink: 0 }} />}
                <span style={{ fontSize: 12, color: "#8892aa", flex: 1 }}>{p.summary}</span>
                <span style={{ fontSize: 11, color: "#4a5370" }}>{new Date(p.created_at).toLocaleDateString()}</span>
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

function TabExecution({ events }: { events: ExecutionEvent[] }) {
  const [expandedErr, setExpandedErr] = useState<string | null>(null);
  const typeStyle: Record<ExecutionEvent["type"], { icon: React.ReactNode; color: keyof typeof C }> = {
    start:   { icon: <Play          style={{ width: 11, height: 11 }} />, color: "green" },
    stop:    { icon: <Square        style={{ width: 11, height: 11 }} />, color: "amber" },
    failure: { icon: <AlertTriangle style={{ width: 11, height: 11 }} />, color: "red" },
    ready:   { icon: <Check         style={{ width: 11, height: 11 }} />, color: "teal" },
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", gap: 8 }}>
          <button style={{ padding: "6px 14px", borderRadius: 6, border: `1px solid ${C.green.border}`, background: C.green.bg, color: C.green.text, cursor: "pointer", fontSize: 12, fontWeight: 600, display: "flex", alignItems: "center", gap: 5 }}>
            <Play style={{ width: 11, height: 11 }} /> Start program
          </button>
          <button style={{ padding: "6px 14px", borderRadius: 6, border: `1px solid ${C.red.border}`, background: C.red.bg, color: C.red.text, cursor: "pointer", fontSize: 12, fontWeight: 600, display: "flex", alignItems: "center", gap: 5 }}>
            <Square style={{ width: 11, height: 11 }} /> Stop program
          </button>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <div style={{ width: 7, height: 7, borderRadius: "50%", background: C.green.text, boxShadow: `0 0 8px ${C.green.text}` }} />
          <span style={{ fontSize: 12, color: C.green.text, fontWeight: 600 }}>Running</span>
        </div>
      </div>

      <div style={{ border: "1px solid #1e2740", borderRadius: 10, overflow: "hidden", background: "#131929" }}>
        <div style={{ padding: "10px 14px", borderBottom: "1px solid #1a2035", fontSize: 10, fontWeight: 700, color: "#4a5370", textTransform: "uppercase", letterSpacing: "0.07em" }}>Execution log</div>
        <div style={{ padding: "10px 14px" }}>
          {[...events].reverse().map(e => {
            const s      = typeStyle[e.type];
            const isErr  = e.type === "failure";
            const isOpen = expandedErr === e.id;
            return (
              <div key={e.id}>
                <div onClick={() => isErr && setExpandedErr(isOpen ? null : e.id)} style={{ display: "flex", alignItems: "center", gap: 10, padding: "7px 0", borderBottom: "1px solid #1a2035", cursor: isErr ? "pointer" : "default" }}>
                  <span style={{ color: C[s.color].text, flexShrink: 0 }}>{s.icon}</span>
                  <span style={{ fontSize: 11, fontFamily: "monospace", color: "#4a5370", width: 108, flexShrink: 0 }}>{new Date(e.timestamp).toLocaleTimeString()}</span>
                  <span style={{ fontSize: 12, color: "#8892aa", flex: 1 }}>{e.message}</span>
                  {e.duration_ms && <span style={{ fontSize: 10, color: "#4a5370", fontFamily: "monospace" }}>{e.duration_ms}ms</span>}
                  {e.exit_code !== undefined && <span style={{ fontSize: 10, fontFamily: "monospace", color: e.exit_code === 0 ? C.green.text : C.red.text }}>exit {e.exit_code}</span>}
                  {isErr && <ChevronDown style={{ width: 12, height: 12, color: "#4a5370", transform: isOpen ? "rotate(180deg)" : "none", transition: "transform 0.2s" }} />}
                </div>
                {isErr && isOpen && e.stderr_tail && (
                  <pre style={{ margin: "4px 0 4px", fontSize: 11, color: C.red.text, background: C.red.bg, border: `1px solid ${C.red.border}`, borderRadius: 6, padding: "8px 10px", fontFamily: "monospace", lineHeight: 1.6, whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                    {e.stderr_tail}
                  </pre>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ── Tab: Prompt history ────────────────────────────────────────────────────

function TabHistory({ versions }: { versions: PromptVersion[] }) {
  const [expanded, setExpanded] = useState<number | null>(null);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <p style={{ margin: "0 0 6px", fontSize: 12, color: "#4a5370", lineHeight: 1.5 }}>
        Every prompt revision approved through the review queue is versioned here. Correction rate before → after shows the improvement loop working.
      </p>
      {[...versions].reverse().map((v, i) => {
        const open     = expanded === v.version;
        const improved = v.correction_rate_after !== undefined && v.correction_rate_after < v.correction_rate_before;
        return (
          <div key={v.version} style={{ border: "1px solid #1e2740", borderRadius: 10, overflow: "hidden", background: "#131929" }}>
            <div onClick={() => setExpanded(open ? null : v.version)} style={{ padding: "12px 14px", cursor: "pointer", display: "flex", alignItems: "center", gap: 12 }}>
              <div style={{
                width: 26, height: 26, borderRadius: "50%", flexShrink: 0,
                display: "flex", alignItems: "center", justifyContent: "center",
                background: i === 0 ? C.green.bg : "#1e2740",
                border: `1px solid ${i === 0 ? C.green.border : "#252b3d"}`,
                fontSize: 10, fontWeight: 700,
                color: i === 0 ? C.green.text : "#4a5370",
              }}>
                v{v.version}
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: "#e2e6f0", marginBottom: 2 }}>{v.summary}</div>
                <div style={{ fontSize: 11, color: "#4a5370" }}>{new Date(v.approved_at).toLocaleDateString()} · {v.approved_by}</div>
              </div>
              {v.correction_rate_after !== undefined && (
                <div style={{ display: "flex", alignItems: "center", gap: 6, flexShrink: 0 }}>
                  <span style={{ fontSize: 11, fontFamily: "monospace", color: "#4a5370" }}>{Math.round(v.correction_rate_before * 100)}%</span>
                  <ArrowRight style={{ width: 12, height: 12, color: "#4a5370" }} />
                  <span style={{ fontSize: 11, fontFamily: "monospace", fontWeight: 700, color: improved ? C.green.text : C.red.text }}>
                    {Math.round(v.correction_rate_after * 100)}%
                  </span>
                  {improved ? <TrendingDown style={{ width: 12, height: 12, color: C.green.text }} /> : <TrendingUp style={{ width: 12, height: 12, color: C.red.text }} />}
                </div>
              )}
              <ChevronDown style={{ width: 13, height: 13, color: "#4a5370", flexShrink: 0, transform: open ? "rotate(180deg)" : "none", transition: "transform 0.2s" }} />
            </div>
            {open && (
              <div style={{ borderTop: "1px solid #1a2035", padding: "12px 14px" }}>
                <div style={{ fontSize: 10, fontWeight: 700, color: "#4a5370", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>Prompt snippet</div>
                <pre style={{ fontSize: 11, color: "#8892aa", background: "#0b0e18", border: "1px solid #1e2740", borderRadius: 6, padding: "8px 10px", margin: 0, fontFamily: "monospace", lineHeight: 1.6, whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                  {v.prompt_snippet}
                </pre>
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
  sparql?: string;
  ragContext?: { category: string; label: string; text: string }[];
  fewShot?: { question: string; sparql: string }[];
  results?: Record<string, unknown>[];
  resultCount?: number;
  timingMs?: number;
  error?: string;
  confirmed?: boolean;
  confirmPending?: boolean;
  toolName?: string;        // action-mode: which tool was called
  toolArgs?: Record<string, string>; // action-mode: args sent
  rawResponse?: unknown;    // action-mode: raw response
}

interface ToolCallState {
  toolName: string;
  args: Record<string, string>;
}

// Collapsible detail panel used in chat bubbles
function ConsoleDetail({
  label, color, children, defaultOpen = false,
}: { label: string; color: string; children: React.ReactNode; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div style={{ marginTop: 6 }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          display: "flex", alignItems: "center", gap: 5,
          background: "none", border: "none", cursor: "pointer",
          fontSize: 10, fontWeight: 700, color, padding: 0,
          textTransform: "uppercase", letterSpacing: "0.06em",
        }}
      >
        <ChevronDown style={{ width: 10, height: 10, transform: open ? "none" : "rotate(-90deg)", transition: "transform 0.15s" }} />
        {label}
      </button>
      {open && <div style={{ marginTop: 6 }}>{children}</div>}
    </div>
  );
}

function TabConsole({ plugin }: { plugin: Plugin }) {
  const isConversational = plugin.mode === "conversational" || plugin.mode === "hybrid" || !plugin.mode;
  const isAction         = plugin.mode === "action" || plugin.mode === "hybrid";

  // ── Conversational state ──
  const [messages, setMessages]   = useState<ConsoleMessage[]>([]);
  const [nlInput, setNlInput]     = useState("");
  const [nlLoading, setNlLoading] = useState(false);
  const scrollRef                 = useRef<HTMLDivElement>(null);

  // ── Action / tool-call state ──
  const [toolCall, setToolCall]   = useState<ToolCallState>({ toolName: "", args: {} });
  const [actionLoading, setActionLoading] = useState(false);
  const [actionResult, setActionResult]   = useState<ConsoleMessage | null>(null);

  // Auto-scroll chat
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  // Populate default tool selection from plugin's first tool
  useEffect(() => {
    const tools = plugin.generated_tools || [];
    if (tools.length > 0 && !toolCall.toolName) {
      const first = tools[0];
      setToolCall({ toolName: first.name, args: Object.fromEntries(Object.keys(first.arg_types || {}).map(k => [k, ""])) });
    }
  }, [plugin]);

  // ── Conversational submit ──
  const submitNL = async () => {
    const q = nlInput.trim();
    if (!q || nlLoading) return;
    setNlInput("");
    const userMsg: ConsoleMessage = { id: Date.now() + "u", role: "user", text: q };
    setMessages(prev => [...prev, userMsg]);
    setNlLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/query/natural`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: q,
          plugin_id: plugin.id,
          domain_classes: plugin.domain_classes || [],
        }),
      });
      const data = await res.json();
      const assistantMsg: ConsoleMessage = {
        id: Date.now() + "a",
        role: "assistant",
        text: data.answer || (data.success ? `Returned ${data.result_count ?? 0} result(s).` : (data.error || "No answer returned.")),
        sparql: data.sparql,
        ragContext: data.rag_context || [],
        fewShot: data.few_shot_examples || [],
        results: data.results || [],
        resultCount: data.result_count,
        timingMs: data.timing_ms,
        error: data.error,
      };
      setMessages(prev => [...prev, assistantMsg]);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Request failed";
      setMessages(prev => [...prev, {
        id: Date.now() + "e", role: "assistant",
        text: "Failed to reach the query endpoint.", error: msg,
      }]);
    } finally {
      setNlLoading(false);
    }
  };

  // Confirm to few-shot library
  const confirmEntry = async (msg: ConsoleMessage) => {
    if (!msg.sparql) return;
    setMessages(prev => prev.map(m => m.id === msg.id ? { ...m, confirmPending: true } : m));
    try {
      await fetch(`${API_BASE}/api/query/fewshot/confirm`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: msg.text, sparql: msg.sparql, source: "console_confirm" }),
      });
      setMessages(prev => prev.map(m => m.id === msg.id ? { ...m, confirmed: true, confirmPending: false } : m));
    } catch {
      setMessages(prev => prev.map(m => m.id === msg.id ? { ...m, confirmPending: false } : m));
    }
  };

  // ── Action / tool-call submit ──
  const selectedTool = (plugin.generated_tools || []).find(t => t.name === toolCall.toolName);

  const submitAction = async () => {
    if (!toolCall.toolName || actionLoading) return;
    setActionLoading(true);
    setActionResult(null);
    const t0 = Date.now();
    try {
      const res = await fetch(`${API_BASE}/api/plugins/${plugin.id}/agent`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: toolCall.toolName, params: toolCall.args }),
      });
      const data = await res.json().catch(async () => {
        const raw = await res.text().catch(() => "");
        return { raw };
      });
      setActionResult({
        id: Date.now() + "r", role: "assistant",
        text: typeof data.answer === "string" ? data.answer : JSON.stringify(data, null, 2),
        toolName: toolCall.toolName,
        toolArgs: { ...toolCall.args },
        rawResponse: data,
        timingMs: Date.now() - t0,
        error: data.error,
      });
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Request failed";
      setActionResult({
        id: Date.now() + "e", role: "assistant",
        text: "Tool call failed.", error: msg,
        toolName: toolCall.toolName, toolArgs: { ...toolCall.args },
        timingMs: Date.now() - t0,
      });
    } finally {
      setActionLoading(false);
    }
  };

  // ── Shared styles ──
  const panelBase: React.CSSProperties = {
    border: "1px solid #1e2740", borderRadius: 10,
    background: "#131929", overflow: "hidden",
  };
  const panelHeader: React.CSSProperties = {
    padding: "10px 14px", borderBottom: "1px solid #1a2035",
    fontSize: 10, fontWeight: 700, color: "#4a5370",
    textTransform: "uppercase", letterSpacing: "0.07em",
    display: "flex", alignItems: "center", justifyContent: "space-between",
  };
  const codeBlock: React.CSSProperties = {
    background: "#0b0e18", border: "1px solid #1e2740", borderRadius: 7,
    padding: "8px 11px", margin: 0, fontSize: 11,
    fontFamily: "monospace", lineHeight: 1.65,
    color: "#8892aa", overflowX: "auto", whiteSpace: "pre-wrap",
    wordBreak: "break-word" as const,
  };

  // Category color for RAG fragments
  const ragColor = (cat: string) => {
    if (cat === "namespace") return C.blue;
    if (cat === "class")     return C.green;
    if (cat === "taxonomy")  return C.amber;
    return C.purple;
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18, height: "100%" }}>

      {/* ── Mode badge ── */}
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ fontSize: 12, color: "#4a5370" }}>Agent test surface for</span>
        <code style={{ fontSize: 12, color: C.green.text, fontFamily: "monospace" }}>
          POST /api/plugins/{plugin.id}/agent
        </code>
        {isConversational && <Tag color="purple">NL Query</Tag>}
        {isAction         && <Tag color="teal">Tool Inspector</Tag>}
      </div>

      {/* ── Conversational pane ── */}
      {isConversational && (
        <div style={{ ...panelBase, display: "flex", flexDirection: "column", minHeight: 420 }}>
          <div style={panelHeader}>
            <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <MessageSquare style={{ width: 11, height: 11 }} />
              Natural language console
            </span>
            {messages.length > 0 && (
              <button
                onClick={() => setMessages([])}
                style={{ fontSize: 10, color: "#4a5370", background: "none", border: "none", cursor: "pointer" }}
              >
                Clear
              </button>
            )}
          </div>

          {/* Messages */}
          <div
            ref={scrollRef}
            style={{ flex: 1, overflowY: "auto", padding: "14px 16px", display: "flex", flexDirection: "column", gap: 14, minHeight: 300 }}
          >
            {messages.length === 0 && (
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", flex: 1, gap: 10, opacity: 0.5 }}>
                <Radar style={{ width: 28, height: 28, color: "#4a5370" }} />
                <p style={{ fontSize: 12, color: "#4a5370", margin: 0 }}>
                  Ask anything about {plugin.domain_classes?.join(", ") || "the knowledge graph"}
                </p>
              </div>
            )}
            {messages.map(msg => (
              <div
                key={msg.id}
                style={{
                  display: "flex",
                  flexDirection: "column",
                  alignItems: msg.role === "user" ? "flex-end" : "flex-start",
                }}
              >
                {/* Bubble */}
                <div style={{
                  maxWidth: "88%",
                  padding: "9px 13px",
                  borderRadius: msg.role === "user" ? "12px 12px 3px 12px" : "12px 12px 12px 3px",
                  background: msg.role === "user" ? C.green.bg : "#0f1522",
                  border: `1px solid ${msg.role === "user" ? C.green.border : "#1e2740"}`,
                  fontSize: 13,
                  color: "#e2e6f0",
                  lineHeight: 1.6,
                }}>
                  {msg.error
                    ? <span style={{ color: C.red.text }}>{msg.text}</span>
                    : msg.text
                  }

                  {/* Error detail */}
                  {msg.error && (
                    <div style={{ marginTop: 5, fontSize: 11, color: C.red.text, fontFamily: "monospace" }}>
                      {msg.error}
                    </div>
                  )}

                  {/* RAG context */}
                  {(msg.ragContext?.length ?? 0) > 0 && (
                    <ConsoleDetail label={`Schema context · ${msg.ragContext!.length} fragments`} color={C.blue.text}>
                      <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                        {msg.ragContext!.map((f, i) => {
                          const rc = ragColor(f.category);
                          return (
                            <div key={i} style={{
                              padding: "6px 9px", borderRadius: 6,
                              background: rc.bg, border: `1px solid ${rc.border}`,
                            }}>
                              <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 3 }}>
                                <span style={{ fontSize: 9, fontWeight: 700, color: rc.text, textTransform: "uppercase", letterSpacing: "0.06em" }}>{f.category}</span>
                                <span style={{ fontSize: 11, fontWeight: 600, color: "#e2e6f0" }}>{f.label}</span>
                              </div>
                              <pre style={{ ...codeBlock, fontSize: 10, padding: "4px 7px" }}>{f.text}</pre>
                            </div>
                          );
                        })}
                      </div>
                    </ConsoleDetail>
                  )}

                  {/* Few-shot examples */}
                  {(msg.fewShot?.length ?? 0) > 0 && (
                    <ConsoleDetail label={`Few-shot examples · ${msg.fewShot!.length}`} color={C.amber.text}>
                      <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                        {msg.fewShot!.map((ex, i) => (
                          <div key={i} style={{
                            padding: "6px 9px", borderRadius: 6,
                            background: C.amber.bg, border: `1px solid ${C.amber.border}`,
                          }}>
                            <div style={{ fontSize: 11, color: "#e2e6f0", marginBottom: 4 }}>{ex.question}</div>
                            <pre style={{ ...codeBlock, fontSize: 10, padding: "4px 7px", color: C.amber.text }}>{ex.sparql}</pre>
                          </div>
                        ))}
                      </div>
                    </ConsoleDetail>
                  )}

                  {/* SPARQL */}
                  {msg.sparql && (
                    <ConsoleDetail label="Generated SPARQL" color={C.teal.text}>
                      <pre style={codeBlock}>{msg.sparql}</pre>
                    </ConsoleDetail>
                  )}

                  {/* Results summary */}
                  {msg.resultCount !== undefined && msg.resultCount > 0 && (
                    <ConsoleDetail label={`${msg.resultCount} result${msg.resultCount !== 1 ? "s" : ""}`} color={C.green.text}>
                      <pre style={{ ...codeBlock, maxHeight: 160, overflowY: "auto" }}>
                        {JSON.stringify(msg.results?.slice(0, 5), null, 2)}
                        {(msg.results?.length ?? 0) > 5 ? `\n… and ${(msg.results?.length ?? 0) - 5} more` : ""}
                      </pre>
                    </ConsoleDetail>
                  )}
                </div>

                {/* Meta row */}
                {msg.role === "assistant" && (
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 4, paddingLeft: 4 }}>
                    {msg.timingMs !== undefined && (
                      <span style={{ fontSize: 10, color: "#2a3045", fontFamily: "monospace" }}>{msg.timingMs}ms</span>
                    )}
                    {msg.sparql && !msg.confirmed && !msg.error && (
                      <button
                        onClick={() => confirmEntry(msg)}
                        disabled={!!msg.confirmPending}
                        style={{
                          display: "flex", alignItems: "center", gap: 4,
                          fontSize: 10, color: msg.confirmPending ? "#2a3045" : C.green.text,
                          background: "none", border: "none", cursor: "pointer", padding: 0,
                          fontFamily: "inherit",
                        }}
                      >
                        <ThumbsUp style={{ width: 9, height: 9 }} />
                        {msg.confirmPending ? "Saving…" : "Confirm to library"}
                      </button>
                    )}
                    {msg.confirmed && (
                      <span style={{ fontSize: 10, color: C.green.text, display: "flex", alignItems: "center", gap: 4 }}>
                        <Check style={{ width: 9, height: 9 }} /> Saved to few-shot library
                      </span>
                    )}
                  </div>
                )}
              </div>
            ))}

            {nlLoading && (
              <div style={{ display: "flex", alignItems: "center", gap: 8, paddingLeft: 2 }}>
                <Loader2 style={{ width: 13, height: 13, color: C.green.text, animation: "spin 1s linear infinite" }} />
                <span style={{ fontSize: 12, color: "#4a5370" }}>Querying graph…</span>
              </div>
            )}
          </div>

          {/* Input row */}
          <div style={{ borderTop: "1px solid #1e2740", padding: "12px 14px", display: "flex", gap: 8 }}>
            <input
              value={nlInput}
              onChange={e => setNlInput(e.target.value)}
              onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submitNL(); } }}
              placeholder={`Ask about ${plugin.domain_classes?.[0] || "artifacts"}, relationships, coverage…`}
              style={{
                flex: 1, padding: "8px 12px", borderRadius: 7,
                border: "1px solid #1e2740", background: "#0b0e18",
                color: "#e2e6f0", fontSize: 13, outline: "none",
                fontFamily: "inherit",
              }}
            />
            <button
              onClick={submitNL}
              disabled={!nlInput.trim() || nlLoading}
              style={{
                padding: "8px 14px", borderRadius: 7, border: "none",
                background: nlInput.trim() && !nlLoading ? C.green.text : "#1e2740",
                color: nlInput.trim() && !nlLoading ? "#0b0e18" : "#4a5370",
                cursor: nlInput.trim() && !nlLoading ? "pointer" : "not-allowed",
                display: "flex", alignItems: "center", gap: 5,
                fontSize: 12, fontWeight: 700, transition: "all 0.15s",
              }}
            >
              {nlLoading
                ? <Loader2 style={{ width: 13, height: 13, animation: "spin 1s linear infinite" }} />
                : <Send style={{ width: 13, height: 13 }} />
              }
            </button>
          </div>
        </div>
      )}

      {/* ── Tool call inspector ── */}
      {isAction && (
        <div style={{ ...panelBase }}>
          <div style={panelHeader}>
            <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <Wrench style={{ width: 11, height: 11 }} />
              Tool call inspector
            </span>
            <span style={{ fontSize: 10, color: "#2a3045" }}>
              {(plugin.generated_tools || []).length} tools available
            </span>
          </div>

          <div style={{ padding: "14px 16px", display: "flex", flexDirection: "column", gap: 14 }}>

            {/* Tool selector */}
            <div>
              <div style={{ fontSize: 10, fontWeight: 700, color: "#4a5370", marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.06em" }}>
                Tool
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
                {(plugin.generated_tools || []).map(t => {
                  const isCode = t.source === "code_analysis";
                  const isSel  = toolCall.toolName === t.name;
                  return (
                    <button
                      key={t.name}
                      onClick={() => setToolCall({
                        toolName: t.name,
                        args: Object.fromEntries(Object.keys(t.arg_types || {}).map(k => [k, ""])),
                      })}
                      style={{
                        padding: "4px 10px", borderRadius: 5, cursor: "pointer",
                        border: `1px solid ${isSel ? (isCode ? C.teal.border : C.green.border) : "#252b3d"}`,
                        background: isSel ? (isCode ? C.teal.bg : C.green.bg) : "#0f1522",
                        color: isSel ? (isCode ? C.teal.text : C.green.text) : "#4a5370",
                        fontSize: 11, fontFamily: "monospace", transition: "all 0.12s",
                        display: "flex", alignItems: "center", gap: 5,
                      }}
                    >
                      {isCode
                        ? <Terminal style={{ width: 9, height: 9 }} />
                        : <Code style={{ width: 9, height: 9 }} />
                      }
                      {t.name}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Signature preview */}
            {selectedTool && (
              <div>
                <div style={{ fontSize: 10, fontWeight: 700, color: "#4a5370", marginBottom: 5, textTransform: "uppercase", letterSpacing: "0.06em" }}>
                  Signature
                </div>
                <pre style={codeBlock}>{selectedTool.signature}</pre>
                {selectedTool.description && (
                  <p style={{ fontSize: 11, color: "#4a5370", margin: "5px 0 0", lineHeight: 1.5 }}>{selectedTool.description}</p>
                )}
              </div>
            )}

            {/* Argument inputs */}
            {selectedTool && Object.keys(selectedTool.arg_types || {}).length > 0 && (
              <div>
                <div style={{ fontSize: 10, fontWeight: 700, color: "#4a5370", marginBottom: 8, textTransform: "uppercase", letterSpacing: "0.06em" }}>
                  Arguments
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {Object.entries(selectedTool.arg_types || {}).map(([argName, argType]) => (
                    <div key={argName}>
                      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
                        <code style={{ fontSize: 11, color: C.green.text, fontFamily: "monospace" }}>{argName}</code>
                        <span style={{ fontSize: 10, color: "#2a3045", fontFamily: "monospace" }}>{argType}</span>
                      </div>
                      <input
                        value={toolCall.args[argName] ?? ""}
                        onChange={e => setToolCall(prev => ({ ...prev, args: { ...prev.args, [argName]: e.target.value } }))}
                        placeholder={`Enter ${argName}…`}
                        style={{
                          width: "100%", padding: "7px 11px", borderRadius: 6,
                          border: "1px solid #1e2740", background: "#0b0e18",
                          color: "#e2e6f0", fontSize: 12, outline: "none",
                          fontFamily: "monospace", boxSizing: "border-box",
                        }}
                      />
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Fire button */}
            <button
              onClick={submitAction}
              disabled={!toolCall.toolName || actionLoading}
              style={{
                padding: "9px 16px", borderRadius: 7, border: "none",
                background: toolCall.toolName && !actionLoading ? C.teal.text : "#1e2740",
                color: toolCall.toolName && !actionLoading ? "#0b0e18" : "#4a5370",
                cursor: toolCall.toolName && !actionLoading ? "pointer" : "not-allowed",
                fontSize: 12, fontWeight: 700,
                display: "flex", alignItems: "center", justifyContent: "center", gap: 6,
                transition: "all 0.15s",
              }}
            >
              {actionLoading
                ? <><Loader2 style={{ width: 13, height: 13, animation: "spin 1s linear infinite" }} /> Calling…</>
                : <><Play style={{ width: 11, height: 11 }} /> Call tool</>
              }
            </button>

            {/* Result panel */}
            {actionResult && (
              <div style={{
                borderRadius: 8, overflow: "hidden",
                border: `1px solid ${actionResult.error ? C.red.border : C.teal.border}`,
                background: actionResult.error ? C.red.bg : C.teal.bg,
              }}>
                <div style={{
                  padding: "8px 12px", borderBottom: `1px solid ${actionResult.error ? C.red.border : C.teal.border}`,
                  display: "flex", alignItems: "center", justifyContent: "space-between",
                }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                    {actionResult.error
                      ? <AlertTriangle style={{ width: 12, height: 12, color: C.red.text }} />
                      : <Check style={{ width: 12, height: 12, color: C.teal.text }} />
                    }
                    <code style={{ fontSize: 11, color: actionResult.error ? C.red.text : C.teal.text, fontFamily: "monospace" }}>
                      {actionResult.toolName}()
                    </code>
                  </div>
                  <span style={{ fontSize: 10, color: "#4a5370", fontFamily: "monospace" }}>
                    {actionResult.timingMs}ms
                  </span>
                </div>
                <div style={{ padding: "10px 12px" }}>
                  {actionResult.error && (
                    <div style={{ fontSize: 11, color: C.red.text, fontFamily: "monospace", marginBottom: 8 }}>
                      {actionResult.error}
                    </div>
                  )}
                  <div style={{ fontSize: 10, fontWeight: 700, color: "#4a5370", marginBottom: 5, textTransform: "uppercase", letterSpacing: "0.06em" }}>
                    {actionResult.error ? "Error detail" : "Response"}
                  </div>
                  <pre style={{ ...codeBlock, maxHeight: 240, overflowY: "auto", fontSize: 11 }}>
                    {typeof actionResult.rawResponse === "string"
                      ? actionResult.rawResponse
                      : JSON.stringify(actionResult.rawResponse, null, 2)}
                  </pre>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* If pure action mode, show endpoint reminder */}
      {plugin.mode === "action" && !isConversational && (
        <div style={{
          padding: "11px 14px", borderRadius: 8,
          border: "1px solid #1e2740", background: "#131929",
          fontSize: 12, color: "#4a5370", lineHeight: 1.6,
        }}>
          This agent is configured in <strong style={{ color: "#e2e6f0" }}>action mode</strong>. Use the tool inspector above to fire typed tool calls against <code style={{ fontFamily: "monospace", color: C.teal.text }}>POST /api/plugins/{plugin.id}/agent</code>. Switch to <em>hybrid</em> mode in the manifest to also enable the NL query interface.
        </div>
      )}
    </div>
  );
}

// ── Main ───────────────────────────────────────────────────────────────────

export default function PluginDashboard({ initialPluginId = null }: { initialPluginId?: string | null }) {
  const [plugins, setPlugins]       = useState<Plugin[]>([]);
  const [selected, setSelected]     = useState<Plugin | null>(null);
  const [tab, setTab]               = useState<Tab>("overview");
  const [isLoading, setIsLoading]   = useState(true);
  const [proposals, setProposals]   = useState<Proposal[]>([]);
  const [metricsMap, setMetricsMap] = useState<Record<string, PerformanceMetric[]>>({});
  const [toolsMap, setToolsMap]     = useState<Record<string, ToolUsage[]>>({});
  const [execEvents, setExecEvents] = useState<ExecutionEvent[]>([]);
  const [historyVersions, setHistory] = useState<PromptVersion[]>([]);
  const didAutoSelect = useRef(false);

  useEffect(() => {
    fetch(`${API_BASE}/api/plugins`)
      .then(r => r.json())
      .catch(() => ({ plugins: [] }))
      .then(d => {
        const augmented: Plugin[] = (d.plugins || []).map((p: Plugin, i: number) => {
          const domainClasses = p.collections?.length ? p.collections : ["LibraryModule", "TTP"];
          const mockTools = domainClasses.flatMap(cls => [
            {
              name: `get_${cls.toLowerCase()}_by_id`,
              signature: `get_${cls.toLowerCase()}_by_id(key: str) -> Optional[${cls}]`,
              description: `Retrieve a single ${cls} artifact by its graph key.`,
              arg_types: { key: "str" },
              return_type: `Optional[${cls}]`,
              source: "ontology" as const,
            },
            {
              name: `list_${cls.toLowerCase()}s`,
              signature: `list_${cls.toLowerCase()}s(limit: int = 25) -> List[${cls}]`,
              description: `List all ${cls} artifacts.`,
              arg_types: { limit: "int" },
              return_type: `List[${cls}]`,
              source: "ontology" as const,
            },
          ]);
          if (i === 0) {
            mockTools.push({ name: "program_start", signature: "program_start() -> ExecutionStatus", description: "Start the registered program.", arg_types: {}, return_type: "ExecutionStatus", source: "code_analysis" as const });
          }
          return {
            ...p,
            mode: (i % 3 === 0 ? "action" : i % 3 === 1 ? "conversational" : "hybrid") as Plugin["mode"],
            llm_model: "llama3.3:70b",
            domain_classes: domainClasses,
            write_permissions: i % 2 === 0 ? ["propose_edge"] : [],
            session_cache_ttl: 300,
            system_prompt: "You are a domain specialist for the 318th RANS knowledge graph.\n\nAlways use graph tools.",
            has_code: i === 0, code_filename: i === 0 ? "kerberoast.py" : undefined,
            generated_tools: mockTools,
            improvement_policy: {
              enabled: i % 2 === 0,
              correction_threshold: 0.25, tool_usage_window_days: 7,
              prompt_revision_requires_review: true,
              track_execution_failures: true, auto_propose_tool_additions: false,
            },
          };
        });
        const mm: Record<string, PerformanceMetric[]> = {};
        const tm: Record<string, ToolUsage[]> = {};
        augmented.forEach(p => {
          mm[p.id] = mockMetrics(14);
          tm[p.id] = mockToolUsage(p.domain_classes || [], !!p.has_code);
        });
        setPlugins(augmented); setMetricsMap(mm); setToolsMap(tm);

        // Auto-select plugin from URL param on first load
        if (initialPluginId && !didAutoSelect.current) {
          const match = augmented.find(p => p.id === initialPluginId);
          if (match) {
            didAutoSelect.current = true;
            setSelected(match);
            setTab("console");
            setProposals(mockProposals());
            setExecEvents(mockExecLog());
            setHistory(mockHistory());
          }
        }
      })
      .finally(() => setIsLoading(false));
  }, [initialPluginId]);

  const selectPlugin = useCallback((p: Plugin) => {
    setSelected(p); setTab("overview");
    setProposals(mockProposals());
    setExecEvents(mockExecLog());
    setHistory(mockHistory());
  }, []);

  const handleToggle = (active: boolean) => {
    if (!selected) return;
    fetch(`${API_BASE}/api/plugins/${selected.id}/${active ? "activate" : "deactivate"}`, { method: "POST" }).catch(() => {});
    const updated = { ...selected, active };
    setSelected(updated);
    setPlugins(ps => ps.map(p => p.id === selected.id ? updated : p));
  };

  const handleProposalAction = (id: string, action: "approved" | "rejected") =>
    setProposals(ps => ps.map(p => p.id === id ? { ...p, status: action } : p));

  const pendingTotal = proposals.filter(p => p.status === "pending").length;

  const TABS: { id: Tab; label: string; icon: React.ReactNode; show: boolean; badge?: number }[] = [
    { id: "overview",    label: "Overview",       icon: <Activity    style={{ width: 13, height: 13 }} />, show: true },
    { id: "performance", label: "Performance",    icon: <TrendingUp  style={{ width: 13, height: 13 }} />, show: true },
    { id: "proposals",   label: "Proposals",      icon: <Brain       style={{ width: 13, height: 13 }} />, show: true, badge: pendingTotal },
    { id: "execution",   label: "Execution",      icon: <Terminal    style={{ width: 13, height: 13 }} />, show: !!selected?.has_code },
    { id: "history",     label: "Prompt history", icon: <History     style={{ width: 13, height: 13 }} />, show: !!selected?.improvement_policy?.enabled },
    { id: "console",     label: "Console",        icon: <MessageSquare style={{ width: 13, height: 13 }} />, show: true },
  ];

  return (
    <div style={{
      height: "100%", display: "flex", flexDirection: "column",
      background: "#0b0e18", color: "#e2e6f0",
      fontFamily: "'IBM Plex Mono', 'Fira Code', monospace",
    }}>

      {/* Header */}
      <div style={{ borderBottom: "1px solid #1e2740", background: "#10131f", padding: "13px 22px", flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 11 }}>
          {selected && (
            <button onClick={() => setSelected(null)} style={{ display: "flex", alignItems: "center", gap: 5, background: "none", border: "none", cursor: "pointer", color: "#4a5370", fontSize: 12, fontFamily: "inherit" }}>
              <ArrowLeft style={{ width: 14, height: 14 }} />
            </button>
          )}
          <div style={{ width: 30, height: 30, borderRadius: 7, fontSize: 14, display: "flex", alignItems: "center", justifyContent: "center", background: C.blue.bg, border: `1px solid ${C.blue.border}` }}>
            {selected ? selected.icon : "📊"}
          </div>
          <div>
            <h1 style={{ margin: 0, fontSize: 14, fontWeight: 700, color: "#e2e6f0", letterSpacing: "-0.01em", fontFamily: "inherit" }}>
              {selected ? selected.name : "Plugin Dashboard"}
            </h1>
            <p style={{ margin: 0, fontSize: 10, color: "#4a5370" }}>
              {selected ? `ATLAS · ${selected.id}` : `ATLAS · ${plugins.length} registered · ${plugins.filter(p => p.active).length} active`}
            </p>
          </div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          {selected && pendingTotal > 0 && (
            <div style={{ padding: "5px 12px", borderRadius: 6, display: "flex", alignItems: "center", gap: 6, background: C.amber.bg, border: `1px solid ${C.amber.border}`, fontSize: 12, color: C.amber.text, fontWeight: 600 }}>
              <Sparkles style={{ width: 12, height: 12 }} />
              {pendingTotal} proposal{pendingTotal !== 1 ? "s" : ""} pending
            </div>
          )}
          <button style={{ padding: "5px 10px", borderRadius: 6, border: "1px solid #1e2740", background: "#131929", color: "#4a5370", cursor: "pointer", display: "flex", alignItems: "center", gap: 5, fontSize: 12, fontFamily: "inherit" }}>
            <RefreshCw style={{ width: 12, height: 12 }} />
          </button>
        </div>
      </div>

      {/* Body */}
      {!selected ? (
        <div style={{ flex: 1, overflowY: "auto", padding: 22 }}>
          {isLoading ? (
            <div style={{ display: "flex", justifyContent: "center", paddingTop: 60 }}>
              <RefreshCw style={{ width: 20, height: 20, color: "#4a5370", animation: "spin 1s linear infinite" }} />
            </div>
          ) : plugins.length === 0 ? (
            <div style={{ textAlign: "center", paddingTop: 80 }}>
              <Zap style={{ width: 28, height: 28, color: "#1e2740", margin: "0 auto 12px" }} />
              <p style={{ fontSize: 14, color: "#4a5370", margin: "0 0 6px" }}>No plugins registered yet</p>
              <p style={{ fontSize: 12, color: "#2a3045", margin: 0 }}>Use the App Onboarding wizard to register your first application</p>
            </div>
          ) : (
            <>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 10, marginBottom: 22 }}>
                <StatCard label="Registered" value={plugins.length} color="green" />
                <StatCard label="Active"     value={plugins.filter(p => p.active).length} color="green" />
                <StatCard label="Learning"   value={plugins.filter(p => p.improvement_policy?.enabled).length} color="blue" />
                <StatCard label="Proposals"  value={mockProposals().filter(p => p.status === "pending").length} color="amber" />
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(290px,1fr))", gap: 12 }}>
                {plugins.map(p => (
                  <FleetCard
                    key={p.id}
                    plugin={p}
                    metrics={metricsMap[p.id] || []}
                    proposals={p.improvement_policy?.enabled ? mockProposals() : []}
                    onSelect={() => selectPlugin(p)}
                    onToggle={active => {
                      fetch(`${API_BASE}/api/plugins/${p.id}/${active ? "activate" : "deactivate"}`, { method: "POST" }).catch(() => {});
                      setPlugins(ps => ps.map(x => x.id === p.id ? { ...x, active } : x));
                    }}
                  />
                ))}
              </div>
            </>
          )}
        </div>
      ) : (
        <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
          {/* Tab bar */}
          <div style={{ borderBottom: "1px solid #1e2740", background: "#10131f", padding: "0 22px", display: "flex", alignItems: "center", gap: 2, flexShrink: 0 }}>
            {TABS.filter(t => t.show).map(t => (
              <button key={t.id} onClick={() => setTab(t.id)} style={{
                padding: "11px 14px", borderRadius: "6px 6px 0 0", cursor: "pointer",
                border: "none", borderBottom: tab === t.id ? `2px solid ${C.green.text}` : "2px solid transparent",
                background: tab === t.id ? "#131929" : "transparent",
                color: tab === t.id ? "#e2e6f0" : "#4a5370",
                fontSize: 12, fontWeight: tab === t.id ? 600 : 400,
                display: "flex", alignItems: "center", gap: 6,
                transition: "all 0.15s", fontFamily: "inherit",
              }}>
                {t.icon}{t.label}
                {t.badge !== undefined && t.badge > 0 && (
                  <span style={{ width: 16, height: 16, borderRadius: "50%", fontSize: 9, fontWeight: 700, background: C.amber.text, color: "#0b0e18", display: "flex", alignItems: "center", justifyContent: "center" }}>
                    {t.badge}
                  </span>
                )}
              </button>
            ))}
          </div>

          {/* Tab content */}
          <div style={{ flex: 1, overflowY: "auto", padding: 22 }}>
            <div style={{ maxWidth: tab === "console" ? 860 : 740, margin: "0 auto" }}>
              {tab === "overview"    && <TabOverview    plugin={selected} onToggle={handleToggle} />}
              {tab === "performance" && <TabPerformance plugin={selected} metrics={metricsMap[selected.id] || []} tools={toolsMap[selected.id] || []} />}
              {tab === "proposals"   && <TabProposals   proposals={proposals} onAction={handleProposalAction} />}
              {tab === "execution"   && <TabExecution   events={execEvents} />}
              {tab === "history"     && <TabHistory     versions={historyVersions} />}
              {tab === "console"     && <TabConsole     plugin={selected} />}
            </div>
          </div>
        </div>
      )}

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}