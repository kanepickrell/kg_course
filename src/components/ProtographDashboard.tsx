import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";

// Ensure Outfit font is available
const _outfitLink = document.createElement("link");
_outfitLink.href = "https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap";
_outfitLink.rel = "stylesheet";
if (!document.head.querySelector('link[href*="Outfit"]')) document.head.appendChild(_outfitLink);

// ── Palette ──
const C = {
  bg: "#0a0a0a",
  card: "#121212",
  cardHover: "#1a1a1a",
  border: "#2d2d2d",
  borderHover: "#3d3d3d",
  green: "#829646",
  greenBright: "#6EBE46",
  olive: "#4B5A2D",
  amber: "#E6AA32",
  amberDim: "rgba(230,170,50,0.15)",
  tan: "#A09678",
  red: "#B43C3C",
  fg: "#ebebeb",
  muted: "#888888",
  subtle: "#555555",
};

// ── Tool definitions ──
const tools = [
  {
    id: "graph",
    label: "Graph Explorer",
    desc: "Navigate the knowledge graph — nodes, edges, clusters, and neural overlays",
    icon: "⬡",
    route: "/graph",
    accentColor: C.greenBright,
    stats: [
      { label: "Nodes", value: "—", key: "nodes" },
      { label: "Edges", value: "—", key: "edges" },
    ],
    statusEndpoint: "/api/graph/stats",
  },
  {
    id: "ontology",
    label: "Ontology Manager",
    desc: "SKOS taxonomies, OWL concepts, schema properties — the semantic backbone",
    icon: "◈",
    route: "/ontology",
    accentColor: C.amber,
    stats: [
      { label: "Taxonomies", value: "—", key: "taxonomies" },
      { label: "Concepts", value: "—", key: "concepts" },
    ],
    statusEndpoint: "/api/ontology/stats",
  },
  {
    id: "pipelines",
    label: "Pipeline Studio",
    desc: "Visual pipeline builder for data flows, transforms, and automation chains",
    icon: "⟁",
    route: "/pipelines",
    accentColor: C.tan,
    stats: [
      { label: "Pipelines", value: "—", key: "pipelines" },
      { label: "Active", value: "—", key: "active" },
    ],
    statusEndpoint: "/api/pipelines/stats",
  },
  {
    id: "upload",
    label: "Data Upload",
    desc: "Ingest artifacts with LLM-powered classification, schema mapping, and validation",
    icon: "⤓",
    route: "/upload",
    accentColor: C.green,
    stats: [
      { label: "Ingested", value: "—", key: "ingested" },
      { label: "Pending", value: "—", key: "pending" },
    ],
    statusEndpoint: "/api/upload/stats",
  },
];

// ── Tool Card ──
function ToolCard({
  tool,
  index,
  hovered,
  onHover,
  onClick,
}: {
  tool: (typeof tools)[0];
  index: number;
  hovered: string | null;
  onHover: (id: string | null) => void;
  onClick: () => void;
}) {
  const isHovered = hovered === tool.id;
  return (
    <div
      onMouseEnter={() => onHover(tool.id)}
      onMouseLeave={() => onHover(null)}
      onClick={onClick}
      style={{
        background: isHovered ? C.cardHover : C.card,
        border: `2px solid ${isHovered ? tool.accentColor + "66" : C.border}`,
        borderRadius: 10,
        padding: "24px 22px 20px",
        cursor: "pointer",
        transition: "all 0.25s ease",
        transform: isHovered ? "translateY(-2px)" : "none",
        boxShadow: isHovered
          ? `0 8px 30px rgba(0,0,0,0.4), 0 0 20px ${tool.accentColor}10`
          : `3px 3px 0px ${C.bg}`,
        position: "relative",
        overflow: "hidden",
      }}
    >
      {/* Accent bar */}
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          right: 0,
          height: 2,
          background: isHovered
            ? `linear-gradient(90deg, transparent, ${tool.accentColor}, transparent)`
            : "transparent",
          transition: "background 0.3s",
        }}
      />

      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12 }}>
        <span
          style={{
            fontSize: 22,
            color: tool.accentColor,
            filter: isHovered ? `drop-shadow(0 0 6px ${tool.accentColor}60)` : "none",
            transition: "filter 0.3s",
          }}
        >
          {tool.icon}
        </span>
        <span
          style={{
            fontFamily: "'Rajdhani', sans-serif",
            fontSize: 18,
            fontWeight: 700,
            color: C.fg,
            letterSpacing: 0.5,
          }}
        >
          {tool.label}
        </span>
      </div>

      <p
        style={{
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: 11.5,
          color: C.muted,
          lineHeight: 1.5,
          marginBottom: 16,
          minHeight: 36,
        }}
      >
        {tool.desc}
      </p>

      {/* Stat pills */}
      <div style={{ display: "flex", gap: 10 }}>
        {tool.stats.map((s) => (
          <div
            key={s.label}
            style={{
              flex: 1,
              background: "rgba(0,0,0,0.3)",
              border: `1px solid ${C.border}`,
              borderRadius: 6,
              padding: "6px 10px",
              textAlign: "center",
            }}
          >
            <div
              style={{
                fontFamily: "'Orbitron', sans-serif",
                fontSize: 16,
                fontWeight: 700,
                color: tool.accentColor,
              }}
            >
              {s.value}
            </div>
            <div
              style={{
                fontFamily: "'JetBrains Mono', monospace",
                fontSize: 9,
                color: C.subtle,
                textTransform: "uppercase",
                letterSpacing: 1,
                marginTop: 2,
              }}
            >
              {s.label}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Status Footer ──
function StatusFooter({ apiStatus, dbStatus }: { apiStatus: string; dbStatus: string }) {
  const items = [
    { label: "API", status: apiStatus, color: apiStatus === "online" ? C.greenBright : C.red },
    { label: "ArangoDB", status: dbStatus, color: dbStatus === "online" ? C.greenBright : C.red },
    { label: "Neural Engine", status: "standby", color: C.amber },
  ];

  return (
    <div
      style={{
        position: "fixed",
        bottom: 0,
        left: 0,
        right: 0,
        height: 36,
        background: "rgba(8,8,8,0.95)",
        borderTop: `1px solid ${C.border}`,
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "0 24px",
        fontFamily: "'JetBrains Mono', monospace",
        fontSize: 10,
        color: C.muted,
        zIndex: 100,
        backdropFilter: "blur(10px)",
      }}
    >
      <div style={{ display: "flex", gap: 20 }}>
        {items.map((it) => (
          <div key={it.label} style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <div
              style={{
                width: 6,
                height: 6,
                borderRadius: "50%",
                background: it.color,
                boxShadow: `0 0 6px ${it.color}60`,
              }}
            />
            <span style={{ letterSpacing: 1, textTransform: "uppercase" }}>
              {it.label}: {it.status}
            </span>
          </div>
        ))}
      </div>
      <div style={{ letterSpacing: 1.5, color: C.subtle }}>
        PROTOGRAPH v2.4.0 • CACTUS FRAMEWORK
      </div>
    </div>
  );
}

// ── Dashboard ──
export default function ProtographDashboard() {
  const navigate = useNavigate();
  const [hovered, setHovered] = useState<string | null>(null);
  const [apiStatus, setApiStatus] = useState("checking…");
  const [dbStatus, setDbStatus] = useState("checking…");
  const [toolStats, setToolStats] = useState<Record<string, any>>({});
  const [recentActivity, setRecentActivity] = useState<any[]>([]);

  const user = sessionStorage.getItem("protograph_user") || "operator";
  const API = import.meta.env?.VITE_API_URL || "http://localhost:8000";

  useEffect(() => {
    // Health check
    (async () => {
      try {
        const res = await fetch(`${API}/api/health`, { signal: AbortSignal.timeout(4000) });
        if (res.ok) {
          const data = await res.json();
          setApiStatus("online");
          setDbStatus(data.arango || data.database ? "online" : "degraded");
        } else {
          setApiStatus("degraded");
          setDbStatus("unknown");
        }
      } catch {
        setApiStatus("offline");
        setDbStatus("offline");
      }
    })();

    // Tool stats
    tools.forEach(async (tool) => {
      try {
        const res = await fetch(`${API}${tool.statusEndpoint}`, {
          signal: AbortSignal.timeout(4000),
        });
        if (res.ok) {
          const data = await res.json();
          setToolStats((prev) => ({ ...prev, [tool.id]: data }));
        }
      } catch {
        // leave defaults
      }
    });

    // Recent activity
    (async () => {
      try {
        const res = await fetch(`${API}/api/graph/recent?limit=5`, {
          signal: AbortSignal.timeout(4000),
        });
        if (res.ok) {
          const data = await res.json();
          setRecentActivity(data.items || data.results || []);
        }
      } catch {}
    })();
  }, [API]);

  const handleLogout = () => {
    sessionStorage.removeItem("protograph_authenticated");
    sessionStorage.removeItem("protograph_user");
    navigate("/login");
  };

  // Enrich tools with live stats
  const enrichedTools = tools.map((t) => {
    const data = toolStats[t.id];
    if (!data) return t;
    return {
      ...t,
      stats: t.stats.map((s) => ({
        ...s,
        value: data[s.key] != null ? String(data[s.key]) : s.value,
      })),
    };
  });

  return (
    <div
      style={{
        width: "100vw",
        minHeight: "100vh",
        background: C.bg,
        fontFamily: "'Rajdhani', sans-serif",
        color: C.fg,
        paddingBottom: 50,
      }}
    >
      {/* Top bar */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "16px 28px",
          borderBottom: `1px solid ${C.border}`,
          background: "rgba(12,12,12,0.9)",
          backdropFilter: "blur(12px)",
          position: "sticky",
          top: 0,
          zIndex: 50,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <img src="/cactus.png" alt="318th RANS" style={{ width: 48, height: 48, objectFit: "contain" }} />
          <div>
            <div style={{ fontSize: 18, lineHeight: 1.1, fontFamily: "'Outfit', sans-serif" }}>
              <span style={{ fontWeight: 400, color: "#fff" }}>Proto</span>
              <span style={{ fontWeight: 600, color: C.greenBright }}>Graph</span>
            </div>
            <div
              style={{
                fontSize: 10,
                color: "#fff",
                fontWeight: 600,
                letterSpacing: 1.2,
                textTransform: "uppercase",
              }}
            >
              Range Intelligence
            </div>
          </div>
          <span
            style={{
              fontFamily: "'JetBrains Mono', monospace",
              fontSize: 10,
              letterSpacing: 2,
              marginLeft: 4,
              padding: "2px 8px",
              background: C.amberDim,
              borderRadius: 4,
              border: `1px solid ${C.amber}40`,
              color: C.amber,
            }}
          >
            DASHBOARD
          </span>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <span
            style={{
              fontFamily: "'JetBrains Mono', monospace",
              fontSize: 11,
              color: C.muted,
            }}
          >
            {user}
          </span>
          <button
            onClick={handleLogout}
            style={{
              padding: "6px 14px",
              background: "transparent",
              border: `1px solid ${C.border}`,
              borderRadius: 6,
              color: C.muted,
              fontSize: 11,
              fontFamily: "'JetBrains Mono', monospace",
              cursor: "pointer",
              letterSpacing: 1,
            }}
          >
            LOGOUT
          </button>
        </div>
      </div>

      {/* Hero */}
      <div style={{ padding: "48px 28px 24px", maxWidth: 1100, margin: "0 auto" }}>
        <h1
          style={{
            fontFamily: "'Orbitron', sans-serif",
            fontSize: 32,
            fontWeight: 900,
            letterSpacing: 2,
            marginBottom: 8,
          }}
        >
          Mission <span style={{ color: C.greenBright }}>Control</span>
        </h1>
        <p
          style={{
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: 13,
            color: C.muted,
            lineHeight: 1.6,
            maxWidth: 600,
          }}
        >
          Knowledge graph operations, ontology management, and pipeline automation — select a tool
          to begin.
        </p>
      </div>

      {/* Tool grid */}
      <div
        style={{
          maxWidth: 1100,
          margin: "0 auto",
          padding: "0 28px",
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
          gap: 18,
          marginBottom: 40,
        }}
      >
        {enrichedTools.map((tool, i) => (
          <ToolCard
            key={tool.id}
            tool={tool}
            index={i}
            hovered={hovered}
            onHover={setHovered}
            onClick={() => navigate(tool.route)}
          />
        ))}
      </div>

      {/* Recent activity */}
      <div style={{ maxWidth: 1100, margin: "0 auto", padding: "0 28px" }}>
        <div
          style={{
            background: C.card,
            border: `2px solid ${C.border}`,
            borderRadius: 10,
            padding: "20px 22px",
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              marginBottom: 16,
            }}
          >
            <div
              style={{
                fontFamily: "'Rajdhani', sans-serif",
                fontSize: 16,
                fontWeight: 700,
                letterSpacing: 1,
                color: C.fg,
                display: "flex",
                alignItems: "center",
                gap: 8,
              }}
            >
              <span style={{ color: C.amber }}>◉</span> Recent Activity
            </div>
            <span
              style={{
                fontFamily: "'JetBrains Mono', monospace",
                fontSize: 10,
                color: C.subtle,
                letterSpacing: 1,
              }}
            >
              LAST 5 OPERATIONS
            </span>
          </div>

          {recentActivity.length === 0 ? (
            <div
              style={{
                textAlign: "center",
                padding: "20px 0",
                fontFamily: "'JetBrains Mono', monospace",
                fontSize: 12,
                color: C.subtle,
              }}
            >
              No recent activity — connect to API to populate
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {recentActivity.slice(0, 5).map((item: any, i: number) => (
                <div
                  key={i}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 12,
                    padding: "8px 12px",
                    background: "rgba(0,0,0,0.25)",
                    borderRadius: 6,
                    border: `1px solid ${C.border}`,
                    fontFamily: "'JetBrains Mono', monospace",
                    fontSize: 11,
                    color: C.muted,
                  }}
                >
                  <span style={{ color: C.green }}>●</span>
                  <span style={{ flex: 1 }}>{item.label || item.id || "—"}</span>
                  <span style={{ color: C.subtle, fontSize: 10 }}>
                    {item.type || "artifact"}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <StatusFooter apiStatus={apiStatus} dbStatus={dbStatus} />
    </div>
  );
}