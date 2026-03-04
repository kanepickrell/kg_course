import { useState, useEffect, useRef } from "react";
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
  border: "#2d2d2d",
  green: "#829646",
  greenBright: "#6EBE46",
  olive: "#4B5A2D",
  amber: "#E6AA32",
  tan: "#A09678",
  red: "#B43C3C",
  fg: "#ebebeb",
  muted: "#888888",
  subtle: "#555555",
};

export default function ProtographLogin() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const canvasRef = useRef<HTMLCanvasElement>(null);

  // Redirect if already authenticated
  useEffect(() => {
    if (sessionStorage.getItem("protograph_authenticated") === "true") {
      navigate("/home", { replace: true });
    }
  }, [navigate]);

  // Animated graph background
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d")!;
    let animFrame: number;
    const nodes: { x: number; y: number; vx: number; vy: number; r: number; type: string }[] = [];

    const resize = () => {
      canvas.width = canvas.offsetWidth * 2;
      canvas.height = canvas.offsetHeight * 2;
      ctx.setTransform(2, 0, 0, 2, 0, 0);
    };
    resize();
    window.addEventListener("resize", resize);

    const w = canvas.offsetWidth;
    const h = canvas.offsetHeight;
    for (let i = 0; i < 40; i++) {
      nodes.push({
        x: Math.random() * w,
        y: Math.random() * h,
        vx: (Math.random() - 0.5) * 0.3,
        vy: (Math.random() - 0.5) * 0.3,
        r: Math.random() * 2.5 + 1,
        type: Math.random() > 0.6 ? "amber" : Math.random() > 0.3 ? "green" : "tan",
      });
    }

    const draw = () => {
      ctx.clearRect(0, 0, w, h);
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const dx = nodes[i].x - nodes[j].x;
          const dy = nodes[i].y - nodes[j].y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist < 120) {
            ctx.beginPath();
            ctx.moveTo(nodes[i].x, nodes[i].y);
            ctx.lineTo(nodes[j].x, nodes[j].y);
            ctx.strokeStyle = `rgba(130,150,70,${0.12 * (1 - dist / 120)})`;
            ctx.lineWidth = 0.5;
            ctx.stroke();
          }
        }
      }
      nodes.forEach((n) => {
        const color = n.type === "amber" ? C.amber : n.type === "green" ? C.green : C.tan;
        ctx.beginPath();
        ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.globalAlpha = 0.5;
        ctx.fill();
        ctx.globalAlpha = 1;
        n.x += n.vx;
        n.y += n.vy;
        if (n.x < 0 || n.x > w) n.vx *= -1;
        if (n.y < 0 || n.y > h) n.vy *= -1;
      });
      animFrame = requestAnimationFrame(draw);
    };
    draw();
    return () => {
      cancelAnimationFrame(animFrame);
      window.removeEventListener("resize", resize);
    };
  }, []);

  const handleSubmit = () => {
    if (!email || !password) {
      setError("Please enter credentials.");
      return;
    }
    setLoading(true);
    setError("");
    setTimeout(() => {
      sessionStorage.setItem("protograph_authenticated", "true");
      sessionStorage.setItem("protograph_user", email);
      setLoading(false);
      navigate("/home");
    }, 1400);
  };

  return (
    <div
      style={{
        position: "relative",
        width: "100vw",
        height: "100vh",
        background: C.bg,
        overflow: "hidden",
        fontFamily: "'Rajdhani', sans-serif",
      }}
    >
      <canvas
        ref={canvasRef}
        style={{ position: "absolute", inset: 0, width: "100%", height: "100%", zIndex: 0 }}
      />

      {/* Scanline overlay */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          background:
            "repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(130,150,70,0.015) 2px, rgba(130,150,70,0.015) 4px)",
          zIndex: 1,
          pointerEvents: "none",
        }}
      />

      {/* Dot grid overlay */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          zIndex: 1,
          pointerEvents: "none",
          opacity: 0.03,
          backgroundImage: `radial-gradient(circle, ${C.green} 1px, transparent 1px)`,
          backgroundSize: "30px 30px",
        }}
      />

      {/* Login card */}
      <div
        style={{
          position: "relative",
          zIndex: 10,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          height: "100%",
        }}
      >
        <div
          style={{
            width: 400,
            background: "rgba(12,12,12,0.92)",
            border: `2px solid ${C.border}`,
            borderRadius: 12,
            padding: "40px 36px 36px",
            backdropFilter: "blur(20px)",
            boxShadow: "0 0 60px rgba(130,150,70,0.06), 0 4px 30px rgba(0,0,0,0.5)",
          }}
        >
          {/* Logo */}
          <div style={{ textAlign: "center", marginBottom: 32 }}>
            <img src="/cactus.png" alt="318th RANS" style={{ width: 72, height: 72, objectFit: "contain", margin: "0 auto 12px" }} />
            <div
              style={{
                fontSize: 26,
                lineHeight: 1.1,
                marginBottom: 4,
                fontFamily: "'Outfit', sans-serif",
              }}
            >
              <span style={{ fontWeight: 400, color: C.fg }}>Proto</span>
              <span style={{ fontWeight: 600, color: C.greenBright }}>Graph</span>
            </div>
            <div
              style={{
                fontFamily: "'JetBrains Mono', monospace",
                fontSize: 11,
                color: C.muted,
                letterSpacing: 3,
                textTransform: "uppercase",
              }}
            >
              Data Intelligence Platform
            </div>
          </div>

          {/* Form fields */}
          <div>
            <label
              style={{
                display: "block",
                fontSize: 12,
                fontWeight: 600,
                color: C.tan,
                marginBottom: 6,
                letterSpacing: 1.5,
                textTransform: "uppercase",
                fontFamily: "'JetBrains Mono', monospace",
              }}
            >
              Email
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
              placeholder="operator@318rans.mil"
              style={{
                width: "100%",
                padding: "10px 14px",
                background: "rgba(0,0,0,0.5)",
                border: `1.5px solid ${C.border}`,
                borderRadius: 6,
                color: C.fg,
                fontSize: 14,
                fontFamily: "'JetBrains Mono', monospace",
                outline: "none",
                marginBottom: 18,
                boxSizing: "border-box",
              }}
            />

            <label
              style={{
                display: "block",
                fontSize: 12,
                fontWeight: 600,
                color: C.tan,
                marginBottom: 6,
                letterSpacing: 1.5,
                textTransform: "uppercase",
                fontFamily: "'JetBrains Mono', monospace",
              }}
            >
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
              placeholder="••••••••"
              style={{
                width: "100%",
                padding: "10px 14px",
                background: "rgba(0,0,0,0.5)",
                border: `1.5px solid ${C.border}`,
                borderRadius: 6,
                color: C.fg,
                fontSize: 14,
                fontFamily: "'JetBrains Mono', monospace",
                outline: "none",
                marginBottom: 24,
                boxSizing: "border-box",
              }}
            />

            {error && (
              <div
                style={{
                  color: C.red,
                  fontSize: 13,
                  marginBottom: 12,
                  fontFamily: "'JetBrains Mono', monospace",
                }}
              >
                {error}
              </div>
            )}

            <button
              onClick={handleSubmit}
              disabled={loading}
              style={{
                width: "100%",
                padding: "12px 0",
                background: loading
                  ? C.olive
                  : `linear-gradient(135deg, ${C.olive}, ${C.green})`,
                color: C.fg,
                border: `2px solid ${C.green}`,
                borderRadius: 8,
                fontSize: 15,
                fontWeight: 700,
                fontFamily: "'Rajdhani', sans-serif",
                letterSpacing: 2,
                textTransform: "uppercase",
                cursor: loading ? "wait" : "pointer",
                boxShadow: loading ? "none" : "0 0 20px rgba(110,190,70,0.15)",
              }}
            >
              {loading ? "AUTHENTICATING…" : "ACCESS SYSTEM"}
            </button>
          </div>

          <div
            style={{
              marginTop: 28,
              textAlign: "center",
              fontSize: 11,
              color: C.subtle,
              fontFamily: "'JetBrains Mono', monospace",
              letterSpacing: 1,
            }}
          >
            AUTHORIZED PERSONNEL ONLY • v2.4.0
          </div>
        </div>
      </div>
    </div>
  );
}