// LibraryModuleWizard.tsx
// Click-driven wizard for authoring LibraryModule artifacts in ProtoGraph.
// No JSON or Robot syntax knowledge required from the operator.
//
// Renders in place of the generic form when selectedType === 'LibraryModule'
// in DataIngestionModal step 2.
//
// Props:
//   onCommit(payload, ttl) — write payload JSON + GraphDB triples
//   onCancel              — back to type selection

import { useState, useCallback } from "react";

// ─── Token types ──────────────────────────────────────────────────────────────
// These are the typed "ports" that connect modules in Lumen.
// A module's INPUTS declare what must already exist on the canvas.
// A module's OUTPUTS declare what this module makes available to downstream nodes.

const TOKEN_TYPES = [
  { id: "C2_Server",      label: "C2 Server",       icon: "🖥️", color: "#f59e0b", description: "Teamserver initialized and connected" },
  { id: "Listener",       label: "Listener",         icon: "📡", color: "#3b82f6", description: "Active C2 listener on teamserver" },
  { id: "Agent_Session",  label: "Beacon Session",   icon: "👾", color: "#22c55e", description: "Active beacon running on a target host" },
  { id: "Credentials",    label: "Credentials",      icon: "🔑", color: "#a855f7", description: "Dumped credentials (NTLM, plaintext, tickets)" },
  { id: "File",           label: "File",             icon: "📄", color: "#06b6d4", description: "File on operator machine (payload, exfil, etc.)" },
  { id: "SSH_Connection", label: "SSH Connection",   icon: "🔌", color: "#f97316", description: "SSH access established to a target" },
] as const;

type TokenId = typeof TOKEN_TYPES[number]["id"];

// ─── Command patterns ─────────────────────────────────────────────────────────

const COMMAND_PATTERNS = [
  { id: "direct",     label: "Direct Keyword", icon: "⚡", description: "Calls a Robot keyword directly with parameters", example: "Create Listener    ${name}    ${port}" },
  { id: "shell",      label: "Shell Command",  icon: "💻", description: "Runs a shell command via active beacon",          example: "Issue Shell Cmd    ${session}    dir ${dir}" },
  { id: "powershell", label: "PowerShell",     icon: "⚙️", description: "Runs PowerShell via active beacon",              example: "Issue Powershell Cmd    ${session}    ..." },
  { id: "capture",    label: "Output Capture", icon: "📋", description: "Calls keyword and captures return value",         example: "${output}=    Run Mimikatz    ${session}" },
  { id: "lateral",    label: "Lateral Move",   icon: "🚀", description: "Moves to a new target via bjump",                 example: "${result}=    Run Bjump    ${session}    psexec64    ${target_ip}" },
  { id: "initial",    label: "Initial Access", icon: "🚪", description: "Establishes first beacon via SCP+SSH",            example: "Initial Access    ${target_ip}    ${username}    ${password}    ${beacon}" },
] as const;

type PatternId = typeof COMMAND_PATTERNS[number]["id"];

// ─── Parameter palette ────────────────────────────────────────────────────────

const PARAM_PALETTE = [
  { id: "session",          label: "Beacon Session",    type: "string", default: "${session}",          placeholder: "${session}",           globalSetting: false },
  { id: "target_ip",        label: "Target IP",         type: "string", default: "",                    placeholder: "192.168.1.10",         globalSetting: false },
  { id: "listener_name",    label: "Listener Name",     type: "string", default: "HTTP",                placeholder: "HTTP",                 globalSetting: false },
  { id: "listener_port",    label: "Listener Port",     type: "number", default: 80,                    placeholder: "80",                   globalSetting: false },
  { id: "listener_type",    label: "Listener Type",     type: "select", default: "Beacon_HTTP",         placeholder: "",                     globalSetting: false, options: ["Beacon_HTTP","Beacon_HTTPS","Beacon_SMB"] },
  { id: "payload_name",     label: "Payload Name",      type: "string", default: "beacon",              placeholder: "beacon",               globalSetting: false },
  { id: "payload_template", label: "Payload Template",  type: "select", default: "exe",                 placeholder: "",                     globalSetting: false, options: ["exe","dll","ps1","raw","hta","svc_exe"] },
  { id: "payload_path",     label: "Payload Path",      type: "string", default: "${WORKDIR}update.exe",placeholder: "${WORKDIR}update.exe", globalSetting: false },
  { id: "username",         label: "Username",          type: "string", default: "",                    placeholder: "Administrator",        globalSetting: false },
  { id: "password",         label: "Password",          type: "string", default: "",                    placeholder: "P@ssw0rd",             globalSetting: false },
  { id: "domain",           label: "Domain",            type: "string", default: "",                    placeholder: "WORKGROUP",            globalSetting: false },
  { id: "directory",        label: "Directory Path",    type: "string", default: "C:\\",                placeholder: "C:\\Users\\Public",    globalSetting: false },
  { id: "filename",         label: "File Name / Path",  type: "string", default: "",                    placeholder: "C:\\Temp\\file.exe",   globalSetting: false },
  { id: "registry_path",    label: "Registry Path",     type: "string", default: "",                    placeholder: "HKCU\\Software\\...",  globalSetting: false },
  { id: "service_name",     label: "Service Name",      type: "string", default: "",                    placeholder: "wuauserv",             globalSetting: false },
  { id: "pid",              label: "Process ID",        type: "number", default: 0,                     placeholder: "1234",                 globalSetting: false },
  { id: "arch",             label: "Architecture",      type: "select", default: "x64",                 placeholder: "",                     globalSetting: false, options: ["x64","x86"] },
  { id: "sleep_seconds",    label: "Sleep (seconds)",   type: "number", default: 60,                    placeholder: "60",                   globalSetting: false },
  { id: "jitter_percent",   label: "Jitter %",          type: "number", default: 0,                     placeholder: "0",                    globalSetting: false },
  { id: "source_directory", label: "Source Directory",  type: "string", default: "",                    placeholder: "C:\\Users\\Public",    globalSetting: false },
  { id: "destination",      label: "Destination Path",  type: "string", default: "",                    placeholder: "C:\\Temp\\data.zip",   globalSetting: false },
  { id: "target_file",      label: "Target File",       type: "string", default: "",                    placeholder: "C:\\Temp\\loot.zip",   globalSetting: false },
  { id: "reference_file",   label: "Reference File",    type: "string", default: "",                    placeholder: "C:\\Windows\\notepad.exe", globalSetting: false },
  { id: "beacon_location",  label: "Beacon Location",   type: "string", default: "",                    placeholder: "C:\\Temp\\update.exe", globalSetting: false },
  { id: "current_location", label: "Source Path",       type: "string", default: "",                    placeholder: "C:\\Temp\\beacon.exe", globalSetting: false },
  { id: "new_location",     label: "Destination Path",  type: "string", default: "",                    placeholder: "C:\\Users\\Public\\beacon.exe", globalSetting: false },
  { id: "target_range",     label: "Target Range",      type: "string", default: "",                    placeholder: "192.168.1.0/24",       globalSetting: false },
  { id: "ports",            label: "Ports",             type: "string", default: "22,80,443,445",       placeholder: "22,80,443,445",        globalSetting: false },
  { id: "scan_method",      label: "Scan Method",       type: "select", default: "icmp",                placeholder: "",                     globalSetting: false, options: ["icmp","arp","none"] },
  { id: "cs_ip",            label: "CS Teamserver IP",  type: "string", default: "${CS_IP}",            placeholder: "${CS_IP}",             globalSetting: true,  globalKey: "CS_IP" },
  { id: "workdir",          label: "Work Directory",    type: "string", default: "${WORKDIR}",          placeholder: "${WORKDIR}",           globalSetting: true,  globalKey: "WORKDIR" },
] as const;

type ParamId = typeof PARAM_PALETTE[number]["id"];

// ─── Classification options ───────────────────────────────────────────────────

const TACTICS = [
  { id: "TA0001", label: "Initial Access",       icon: "🚪" },
  { id: "TA0002", label: "Execution",            icon: "⚡" },
  { id: "TA0003", label: "Persistence",          icon: "🔒" },
  { id: "TA0004", label: "Privilege Escalation", icon: "👑" },
  { id: "TA0005", label: "Defense Evasion",      icon: "🛡️" },
  { id: "TA0006", label: "Credential Access",    icon: "🔑" },
  { id: "TA0007", label: "Discovery",            icon: "🔍" },
  { id: "TA0008", label: "Lateral Movement",     icon: "🚀" },
  { id: "TA0009", label: "Collection",           icon: "📦" },
  { id: "TA0010", label: "Exfiltration",         icon: "📤" },
  { id: "TA0011", label: "Command & Control",    icon: "📡" },
  { id: "TA0042", label: "Resource Development", icon: "🏗️" },
];

const RISK_LEVELS = [
  { id: "low",      label: "Low",      color: "#22c55e" },
  { id: "medium",   label: "Medium",   color: "#f59e0b" },
  { id: "high",     label: "High",     color: "#f97316" },
  { id: "critical", label: "Critical", color: "#ef4444" },
];

const ICONS = ["⚡","📡","🔑","🔍","🚪","🔒","👑","🛡️","🚀","📦","💻","🏗️","🌐","🔀","⏱️","🗑️","📋","🔧","📤","👾","🖥️","📄","🔌","💾","🎯"];
const CATEGORIES = ["Cobalt Strike", "Sliver", "Havoc", "SSH", "Shell", "Custom"];

// ─── State ────────────────────────────────────────────────────────────────────

interface WizardForm {
  name: string; description: string; icon: string;
  tactic: string; category: string; subcategory: string;
  riskLevel: string; estimatedDuration: number; mitreId: string;
  executionType: string; pattern: PatternId;
  keywordName: string; shellCommand: string;
  selectedParams: ParamId[];
  inputs: TokenId[]; outputs: TokenId[];
  library: string;
}

const DEFAULT: WizardForm = {
  name: "", description: "", icon: "⚡",
  tactic: "TA0011", category: "Cobalt Strike", subcategory: "",
  riskLevel: "medium", estimatedDuration: 30, mitreId: "",
  executionType: "cobalt_strike", pattern: "direct",
  keywordName: "", shellCommand: "",
  selectedParams: [], inputs: [], outputs: [],
  library: "cobaltstrikec2/cobaltstrike.py",
};

// ─── Payload builder ──────────────────────────────────────────────────────────

function buildPayload(f: WizardForm): Record<string, unknown> {
  const key = f.name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  const allSelected = PARAM_PALETTE.filter((p) => f.selectedParams.includes(p.id as ParamId));
  const userParams = allSelected.filter((p) => !("globalKey" in p && p.globalKey));
  const globalParams = allSelected.filter((p) => "globalKey" in p && p.globalKey);

  const parameters = userParams
    .filter((p) => p.id !== "session")
    .map((p) => {
      const base: Record<string, unknown> = { id: p.id, label: p.label, type: p.type, required: true, placeholder: p.placeholder, default: p.default };
      if ("options" in p && p.options) base.options = [...p.options];
      return base;
    });

  // Template
  let robotTemplate = "";
  const paramStr = allSelected.map((p) => `\${${p.id}}`).join("    ");
  switch (f.pattern) {
    case "direct":     robotTemplate = `${f.keywordName}    ${paramStr}`; break;
    case "shell":      robotTemplate = `\${output}=    Issue Shell Cmd    \${session}    ${f.shellCommand}`; break;
    case "powershell": robotTemplate = `\${output}=    Issue Powershell Cmd    \${session}    ${f.shellCommand}`; break;
    case "capture":    robotTemplate = `\${output}=    ${f.keywordName}    \${session}    ${paramStr}`; break;
    case "lateral":    robotTemplate = `\${result}=    Run Bjump    \${session}    psexec64    \${target_ip}    \${listener_name}`; break;
    case "initial":    robotTemplate = `${f.keywordName}    \${target_ip}    \${username}    \${password}    \${payload_path}`; break;
  }

  // keywordArgs
  let pos = 1;
  const keywordArgs: unknown[] = [];
  if (["shell","powershell","capture","lateral"].includes(f.pattern)) keywordArgs.push({ position: pos++, param: "session" });
  userParams.forEach((p) => { if (p.id !== "session") keywordArgs.push({ position: pos++, param: p.id }); });
  globalParams.forEach((p) => { if ("globalKey" in p) keywordArgs.push({ position: pos++, globalSetting: p.globalKey }); });

  const variables = userParams
    .filter((p) => p.type === "string" && p.id !== "session")
    .map((p) => ({ name: p.id.toUpperCase(), fromParam: p.id, scope: "suite", default: String(p.default) }));

  const inputs = f.inputs.map((id) => {
    const tok = TOKEN_TYPES.find((t) => t.id === id)!;
    return { id: id.toLowerCase(), label: tok.label, type: id, required: true };
  });

  const outputs = f.outputs.map((id) => {
    const tok = TOKEN_TYPES.find((t) => t.id === id)!;
    return { id: id.toLowerCase(), label: tok.label, type: id };
  });

  const requirements: Record<string, unknown> = {};
  if (f.inputs.includes("C2_Server"))     requirements.c2Server = true;
  if (f.inputs.includes("Agent_Session")) requirements.activeBeacon = true;
  if (f.inputs.includes("SSH_Connection"))requirements.sshConnection = true;
  if (f.inputs.includes("Listener"))      requirements.listener = true;
  if (f.inputs.includes("Credentials"))   requirements.credentials = true;

  return {
    _key: key, name: f.name, description: f.description, icon: f.icon,
    tactic: f.tactic, category: f.category, subcategory: f.subcategory,
    riskLevel: f.riskLevel.charAt(0).toUpperCase() + f.riskLevel.slice(1),
    estimatedDuration: f.estimatedDuration, executionType: f.executionType,
    robotKeyword: f.keywordName || f.name, robotTemplate,
    inputs, outputs, parameters, requirements,
    robotFramework: {
      libraries: [f.library], keyword: f.keywordName || f.name,
      keywordArgs, variables, preKeywordLog: `Executing: ${f.name}`,
    },
  };
}

function buildTTL(payload: Record<string, unknown>, f: WizardForm): string {
  const key = payload._key as string;
  const catSlug = f.category.toLowerCase().replace(/\s+/g, "-");
  return `@prefix onto: <https://proto.atlas/ontology/> .
@prefix tax:  <https://proto.atlas/taxonomy/> .
@prefix data: <https://proto.atlas/data/> .
@prefix owl:  <http://www.w3.org/2002/07/owl#> .

data:${key}
    a onto:LibraryModule, onto:Artifact, onto:Thing, owl:Thing ;
    onto:name           "${f.name}" ;
    onto:description    "${f.description.replace(/"/g, '\\"')}" ;
    onto:tactic         tax:mitre-${f.tactic} ;
    onto:category       tax:c2-${catSlug} ;
    onto:riskLevel      tax:risk-${f.riskLevel} ;
    onto:status         tax:status-active ;
    onto:owner          tax:team-automation ;
    onto:mitreId        "${f.mitreId}" ;
    onto:executionType  "${f.executionType}" ;
    onto:robotKeyword   "${f.keywordName || f.name}" ;
    onto:robotTemplate  "${(payload.robotTemplate as string).replace(/"/g, '\\"')}" ;
    onto:payloadUrl     "/api/ingest/payloads/${key}.json" .
`;
}

// ─── Token picker ─────────────────────────────────────────────────────────────

function TokenPicker({ label, hint, selected, onChange }: {
  label: string; hint: string; selected: TokenId[]; onChange: (ids: TokenId[]) => void;
}) {
  const toggle = (id: TokenId) =>
    onChange(selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id]);
  return (
    <div className="lmw-field">
      <div className="lmw-label">{label}</div>
      <div className="lmw-hint">{hint}</div>
      <div className="lmw-token-grid">
        {TOKEN_TYPES.map((t) => {
          const active = selected.includes(t.id);
          return (
            <button key={t.id} className={`lmw-token ${active ? "active" : ""}`}
              style={active ? { borderColor: t.color, background: t.color + "18", color: t.color } : {}}
              onClick={() => toggle(t.id)} title={t.description}>
              <span>{t.icon}</span>
              <span>{t.label}</span>
              {active && <span style={{ fontSize: 10 }}>✓</span>}
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ─── Param picker ─────────────────────────────────────────────────────────────

function ParamPicker({ selected, onChange }: { selected: ParamId[]; onChange: (ids: ParamId[]) => void }) {
  const toggle = (id: ParamId) =>
    onChange(selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id]);
  const userParams = PARAM_PALETTE.filter((p) => !("globalKey" in p && p.globalKey));
  const globals = PARAM_PALETTE.filter((p) => "globalKey" in p && p.globalKey);
  return (
    <div className="lmw-field">
      <div className="lmw-label">Parameters</div>
      <div className="lmw-hint">Select every value this command needs. Global settings are resolved automatically.</div>
      <div className="lmw-param-section-label">User inputs — appear as form fields in Lumen</div>
      <div className="lmw-param-grid">
        {userParams.map((p) => {
          const active = selected.includes(p.id as ParamId);
          return (
            <button key={p.id} className={`lmw-param-chip ${active ? "active" : ""}`} onClick={() => toggle(p.id as ParamId)}>
              <span className="lmw-param-chip-name">{p.label}</span>
              <span className="lmw-param-chip-type">{p.type}</span>
              {active && <span className="lmw-param-chip-check">✓</span>}
            </button>
          );
        })}
      </div>
      <div className="lmw-param-section-label" style={{ marginTop: 12 }}>Global settings — auto-resolved from ops config</div>
      <div className="lmw-param-grid">
        {globals.map((p) => {
          const active = selected.includes(p.id as ParamId);
          return (
            <button key={p.id} className={`lmw-param-chip global ${active ? "active" : ""}`} onClick={() => toggle(p.id as ParamId)}>
              <span className="lmw-param-chip-name">{p.label}</span>
              <span className="lmw-param-chip-type">{"globalKey" in p ? p.globalKey : ""}</span>
              {active && <span className="lmw-param-chip-check">✓</span>}
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ─── Main wizard ──────────────────────────────────────────────────────────────

interface Props {
  onCommit: (payload: Record<string, unknown>, ttl: string) => Promise<void>;
  onCancel: () => void;
}

export default function LibraryModuleWizard({ onCommit, onCancel }: Props) {
  const [form, setForm] = useState<WizardForm>(DEFAULT);
  const [committing, setCommitting] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null);
  const [showPreview, setShowPreview] = useState(false);

  const set = useCallback(<K extends keyof WizardForm>(key: K, value: WizardForm[K]) => {
    setForm((f) => ({ ...f, [key]: value }));
  }, []);

  const canCommit = form.name.trim() && form.description.trim() && form.keywordName.trim();
  const payload = buildPayload(form);
  const ttl = buildTTL(payload, form);

  const handleCommit = async () => {
    setCommitting(true);
    try {
      await onCommit(payload, ttl);
      setResult({ ok: true, message: `"${form.name}" committed to ProtoGraph.` });
    } catch (e: unknown) {
      setResult({ ok: false, message: e instanceof Error ? e.message : String(e) });
    } finally {
      setCommitting(false);
    }
  };

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=DM+Sans:wght@400;500;600&display=swap');

        .lmw { font-family: 'DM Sans', sans-serif; background: #0a0a0c; color: #d4d4d8; display: flex; flex-direction: column; height: 100%; min-height: 600px; }
        .lmw-head { padding: 18px 22px 14px; border-bottom: 1px solid #1e1e23; background: #0d0d10; }
        .lmw-head-eyebrow { font-family: 'Share Tech Mono', monospace; font-size: 9px; letter-spacing: 0.22em; text-transform: uppercase; color: #f59e0b; margin-bottom: 3px; }
        .lmw-head-title { font-size: 15px; font-weight: 600; color: #fafafa; }
        .lmw-body { flex: 1; overflow-y: auto; padding: 20px 22px; display: flex; flex-direction: column; gap: 22px; }
        .lmw-section { display: flex; flex-direction: column; gap: 14px; }
        .lmw-section-head { font-family: 'Share Tech Mono', monospace; font-size: 9px; letter-spacing: 0.2em; text-transform: uppercase; color: #52525b; padding-bottom: 8px; border-bottom: 1px solid #18181c; }
        .lmw-field { display: flex; flex-direction: column; gap: 5px; }
        .lmw-label { font-size: 11px; font-weight: 500; color: #71717a; letter-spacing: 0.03em; }
        .lmw-hint { font-size: 10px; color: #3f3f46; line-height: 1.5; font-family: 'Share Tech Mono', monospace; }
        .lmw-input, .lmw-select, .lmw-textarea { background: #13131a; border: 1px solid #27272a; border-radius: 6px; color: #e4e4e7; font-family: 'DM Sans', sans-serif; font-size: 13px; padding: 8px 11px; transition: border-color 0.12s; outline: none; width: 100%; box-sizing: border-box; }
        .lmw-input:focus, .lmw-select:focus, .lmw-textarea:focus { border-color: #f59e0b66; box-shadow: 0 0 0 2px #f59e0b18; }
        .lmw-input.mono { font-family: 'Share Tech Mono', monospace; font-size: 12px; }
        .lmw-textarea { min-height: 64px; resize: vertical; line-height: 1.5; }
        .lmw-grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
        .lmw-grid-3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; }

        /* Pattern picker */
        .lmw-pattern-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; }
        .lmw-pattern-card { padding: 10px 12px; border-radius: 8px; border: 1px solid #27272a; background: #13131a; cursor: pointer; transition: all 0.12s; text-align: left; }
        .lmw-pattern-card:hover { border-color: #3f3f46; }
        .lmw-pattern-card.active { border-color: #f59e0b; background: #f59e0b0f; }
        .lmw-pattern-icon { font-size: 18px; margin-bottom: 5px; display: block; }
        .lmw-pattern-name { font-size: 11px; font-weight: 600; color: #e4e4e7; display: block; margin-bottom: 2px; }
        .lmw-pattern-card.active .lmw-pattern-name { color: #fbbf24; }
        .lmw-pattern-desc { font-size: 10px; color: #52525b; line-height: 1.4; font-family: 'Share Tech Mono', monospace; }
        .lmw-template-preview { font-family: 'Share Tech Mono', monospace; font-size: 11px; color: #f59e0b99; padding: 8px 10px; background: #0d0d10; border-radius: 5px; border: 1px solid #1e1e23; margin-top: 4px; word-break: break-all; line-height: 1.6; }

        /* Tokens */
        .lmw-token-grid { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 6px; }
        .lmw-token { display: flex; align-items: center; gap: 6px; padding: 6px 11px; border-radius: 20px; border: 1px solid #27272a; background: #13131a; cursor: pointer; font-family: 'DM Sans', sans-serif; font-size: 11px; color: #71717a; transition: all 0.12s; font-weight: 500; }
        .lmw-token:hover { border-color: #3f3f46; color: #a1a1aa; }
        .lmw-token.active { font-weight: 600; }

        /* Param chips */
        .lmw-param-section-label { font-family: 'Share Tech Mono', monospace; font-size: 9px; letter-spacing: 0.15em; text-transform: uppercase; color: #3f3f46; margin-bottom: 6px; }
        .lmw-param-grid { display: flex; flex-wrap: wrap; gap: 6px; }
        .lmw-param-chip { display: flex; align-items: center; gap: 6px; padding: 5px 10px; border-radius: 6px; border: 1px solid #27272a; background: #13131a; cursor: pointer; font-family: 'DM Sans', sans-serif; font-size: 11px; color: #71717a; transition: all 0.12s; font-weight: 500; }
        .lmw-param-chip:hover { border-color: #3f3f46; color: #a1a1aa; }
        .lmw-param-chip.active { border-color: #22c55e66; background: #22c55e0d; color: #4ade80; }
        .lmw-param-chip.global.active { border-color: #3b82f666; background: #3b82f60d; color: #60a5fa; }
        .lmw-param-chip-name { font-weight: 600; }
        .lmw-param-chip-type { font-family: 'Share Tech Mono', monospace; font-size: 9px; opacity: 0.5; }
        .lmw-param-chip-check { font-size: 9px; }

        /* Classification pills */
        .lmw-pill-grid { display: flex; flex-wrap: wrap; gap: 6px; }
        .lmw-pill { padding: 5px 11px; border-radius: 5px; border: 1px solid #27272a; background: #13131a; cursor: pointer; font-size: 11px; font-weight: 500; color: #71717a; transition: all 0.12s; font-family: 'Share Tech Mono', monospace; }
        .lmw-pill:hover { border-color: #3f3f46; color: #a1a1aa; }
        .lmw-pill.active { border-color: #f59e0b88; background: #f59e0b12; color: #fbbf24; }

        /* Icon row */
        .lmw-icon-row { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 4px; }
        .lmw-icon-btn { width: 34px; height: 34px; border-radius: 7px; border: 1px solid #27272a; background: #13131a; font-size: 17px; cursor: pointer; display: flex; align-items: center; justify-content: center; transition: all 0.12s; }
        .lmw-icon-btn.active { border-color: #f59e0b; background: #f59e0b14; transform: scale(1.1); }
        .lmw-icon-btn:hover { border-color: #3f3f46; }

        /* Preview */
        .lmw-preview-toggle { font-family: 'Share Tech Mono', monospace; font-size: 10px; letter-spacing: 0.12em; text-transform: uppercase; color: #52525b; background: transparent; border: 1px solid #27272a; border-radius: 5px; padding: 5px 12px; cursor: pointer; transition: all 0.12s; align-self: flex-start; }
        .lmw-preview-toggle:hover { color: #a1a1aa; border-color: #3f3f46; }
        .lmw-preview { background: #060608; border: 1px solid #1e1e23; border-radius: 8px; padding: 14px; font-family: 'Share Tech Mono', monospace; font-size: 10px; color: #4ade80; white-space: pre-wrap; word-break: break-all; line-height: 1.7; max-height: 280px; overflow-y: auto; }

        .lmw-result { padding: 10px 14px; border-radius: 7px; font-size: 12px; font-weight: 500; }
        .lmw-result.ok { background: #22c55e12; border: 1px solid #22c55e30; color: #4ade80; }
        .lmw-result.err { background: #ef444412; border: 1px solid #ef444430; color: #f87171; }
        .lmw-divider { height: 1px; background: #18181c; }

        /* Footer */
        .lmw-footer { padding: 14px 22px; border-top: 1px solid #1e1e23; display: flex; align-items: center; justify-content: space-between; background: #0a0a0c; }
        .lmw-btn { font-family: 'DM Sans', sans-serif; font-size: 12px; font-weight: 600; padding: 8px 18px; border-radius: 7px; border: none; cursor: pointer; transition: all 0.12s; }
        .lmw-btn-ghost { background: transparent; color: #52525b; border: 1px solid #27272a; }
        .lmw-btn-ghost:hover { color: #a1a1aa; border-color: #3f3f46; }
        .lmw-btn-primary { background: #f59e0b; color: #09090b; }
        .lmw-btn-primary:hover { background: #fbbf24; }
        .lmw-btn-primary:disabled { opacity: 0.35; cursor: not-allowed; }
      `}</style>

      <div className="lmw">
        <div className="lmw-head">
          <div className="lmw-head-eyebrow">ProtoGraph · Library Module</div>
          <div className="lmw-head-title">New Module Wizard</div>
        </div>

        <div className="lmw-body">

          {/* Identity */}
          <div className="lmw-section">
            <div className="lmw-section-head">Identity</div>
            <div className="lmw-grid-2">
              <div className="lmw-field">
                <div className="lmw-label">Module Name *</div>
                <input className="lmw-input" value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="e.g. Lateral Move PsExec64" />
              </div>
              <div className="lmw-field">
                <div className="lmw-label">Robot Keyword *</div>
                <input className="lmw-input mono" value={form.keywordName} onChange={(e) => set("keywordName", e.target.value)} placeholder="e.g. Run Bjump" />
              </div>
            </div>
            <div className="lmw-field">
              <div className="lmw-label">Description *</div>
              <textarea className="lmw-textarea" value={form.description} onChange={(e) => set("description", e.target.value)} placeholder="One sentence: what does this module do?" />
            </div>
            <div className="lmw-field">
              <div className="lmw-label">Icon</div>
              <div className="lmw-icon-row">
                {ICONS.map((ico) => (
                  <button key={ico} className={`lmw-icon-btn ${form.icon === ico ? "active" : ""}`} onClick={() => set("icon", ico)}>{ico}</button>
                ))}
              </div>
            </div>
          </div>

          {/* Command pattern */}
          <div className="lmw-section">
            <div className="lmw-section-head">Command Pattern</div>
            <div className="lmw-pattern-grid">
              {COMMAND_PATTERNS.map((p) => (
                <button key={p.id} className={`lmw-pattern-card ${form.pattern === p.id ? "active" : ""}`} onClick={() => set("pattern", p.id)}>
                  <span className="lmw-pattern-icon">{p.icon}</span>
                  <span className="lmw-pattern-name">{p.label}</span>
                  <span className="lmw-pattern-desc">{p.description}</span>
                </button>
              ))}
            </div>
            {(form.pattern === "shell" || form.pattern === "powershell") && (
              <div className="lmw-field">
                <div className="lmw-label">Command template</div>
                <input className="lmw-input mono" value={form.shellCommand} onChange={(e) => set("shellCommand", e.target.value)} placeholder="dir ${directory}  or  net stop ${service_name}" />
                <div className="lmw-hint">Use $&#123;param_name&#125; for variables that must also be selected below.</div>
              </div>
            )}
            {form.keywordName && (
              <div className="lmw-template-preview">{payload.robotTemplate as string}</div>
            )}
          </div>

          {/* Parameters */}
          <div className="lmw-section">
            <div className="lmw-section-head">Parameters</div>
            <ParamPicker selected={form.selectedParams} onChange={(ids) => set("selectedParams", ids)} />
          </div>

          {/* Token prerequisite + output system */}
          <div className="lmw-section">
            <div className="lmw-section-head">Prerequisite Tokens</div>
            <TokenPicker
              label="Requires on canvas before this can run"
              hint="Lumen soft-warns on drop if missing. Validate hard-blocks export. These rules are stored in ProtoGraph."
              selected={form.inputs}
              onChange={(ids) => set("inputs", ids)}
            />
            <div className="lmw-divider" />
            <div className="lmw-section-head" style={{ marginTop: 4 }}>Output Tokens</div>
            <TokenPicker
              label="Produces — unlocks downstream modules that require these"
              hint="Downstream nodes needing these tokens become addable once this module is on the canvas."
              selected={form.outputs}
              onChange={(ids) => set("outputs", ids)}
            />
          </div>

          {/* Classification */}
          <div className="lmw-section">
            <div className="lmw-section-head">Classification</div>
            <div className="lmw-field">
              <div className="lmw-label">MITRE Tactic</div>
              <div className="lmw-pill-grid">
                {TACTICS.map((t) => (
                  <button key={t.id} className={`lmw-pill ${form.tactic === t.id ? "active" : ""}`} onClick={() => set("tactic", t.id)}>
                    {t.icon} {t.id}
                  </button>
                ))}
              </div>
            </div>
            <div className="lmw-grid-3">
              <div className="lmw-field">
                <div className="lmw-label">Category</div>
                <select className="lmw-select" value={form.category} onChange={(e) => set("category", e.target.value)}>
                  {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>
              <div className="lmw-field">
                <div className="lmw-label">Risk Level</div>
                <div className="lmw-pill-grid">
                  {RISK_LEVELS.map((r) => (
                    <button key={r.id} className={`lmw-pill ${form.riskLevel === r.id ? "active" : ""}`}
                      style={form.riskLevel === r.id ? { borderColor: r.color + "88", color: r.color, background: r.color + "14" } : {}}
                      onClick={() => set("riskLevel", r.id)}>
                      {r.label}
                    </button>
                  ))}
                </div>
              </div>
              <div className="lmw-field">
                <div className="lmw-label">Est. Duration (s)</div>
                <input className="lmw-input" type="number" value={form.estimatedDuration} onChange={(e) => set("estimatedDuration", Number(e.target.value))} />
              </div>
            </div>
            <div className="lmw-grid-2">
              <div className="lmw-field">
                <div className="lmw-label">Subcategory</div>
                <input className="lmw-input" value={form.subcategory} onChange={(e) => set("subcategory", e.target.value)} placeholder="Infrastructure, Enumeration…" />
              </div>
              <div className="lmw-field">
                <div className="lmw-label">MITRE Technique</div>
                <input className="lmw-input mono" value={form.mitreId} onChange={(e) => set("mitreId", e.target.value)} placeholder="T1046" />
              </div>
            </div>
          </div>

          {/* Preview */}
          <div className="lmw-section">
            <div className="lmw-section-head">Payload Preview</div>
            <button className="lmw-preview-toggle" onClick={() => setShowPreview((v) => !v)}>
              {showPreview ? "▲ Hide JSON" : "▼ Show generated JSON"}
            </button>
            {showPreview && <div className="lmw-preview">{JSON.stringify(payload, null, 2)}</div>}
          </div>

          {result && (
            <div className={`lmw-result ${result.ok ? "ok" : "err"}`}>
              {result.ok ? "✓ " : "✗ "}{result.message}
            </div>
          )}
        </div>

        <div className="lmw-footer">
          <button className="lmw-btn lmw-btn-ghost" onClick={onCancel}>Cancel</button>
          {!result?.ok ? (
            <button className="lmw-btn lmw-btn-primary" onClick={handleCommit} disabled={!canCommit || committing}>
              {committing ? "Committing…" : "Commit to ProtoGraph"}
            </button>
          ) : (
            <button className="lmw-btn lmw-btn-ghost" onClick={onCancel}>Done ✓</button>
          )}
        </div>
      </div>
    </>
  );
}