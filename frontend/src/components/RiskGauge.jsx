const RISK_COLOR = {
  CRITICAL: "#f43f5e",
  HIGH:     "#f97316",
  MEDIUM:   "#f59e0b",
  LOW:      "#10b981",
  NONE:     "#38bdf8",
};

// Returns a gradient stop colour based on score 0-100.
function scoreColor(score, level) {
  if (level) return RISK_COLOR[level.toUpperCase()] || RISK_COLOR.NONE;
  if (score >= 80) return RISK_COLOR.CRITICAL;
  if (score >= 60) return RISK_COLOR.HIGH;
  if (score >= 40) return RISK_COLOR.MEDIUM;
  if (score >= 10) return RISK_COLOR.LOW;
  return RISK_COLOR.NONE;
}

// Convert polar to cartesian (for the semicircle path).
function polar(cx, cy, r, angleDeg) {
  const rad = ((angleDeg - 90) * Math.PI) / 180;
  return {
    x: cx + r * Math.cos(rad),
    y: cy + r * Math.sin(rad),
  };
}

// Build an SVG arc path descriptor.
function arc(cx, cy, r, startDeg, endDeg) {
  const s = polar(cx, cy, r, startDeg);
  const e = polar(cx, cy, r, endDeg);
  const large = endDeg - startDeg > 180 ? 1 : 0;
  return `M ${s.x} ${s.y} A ${r} ${r} 0 ${large} 1 ${e.x} ${e.y}`;
}

export default function RiskGauge({ score, level }) {
  const safeScore = typeof score === "number" ? Math.max(0, Math.min(100, score)) : 0;
  const color = scoreColor(safeScore, level);

  const START = -90;
  const SWEEP = 180;
  const endDeg = START + (safeScore / 100) * SWEEP;

  const W = 130;
  const H = 75;
  const CX = W / 2;
  const CY = H - 6;  // centre at bottom of the semicircle
  const R_OUTER = 54;
  const R_INNER = 38;  // track radius

  const trackPath  = arc(CX, CY, R_INNER, START, START + SWEEP);
  const fillPath   = safeScore > 0 ? arc(CX, CY, R_INNER, START, endDeg) : null;

  // Needle tip position
  const tip = polar(CX, CY, R_INNER - 6, endDeg);

  return (
    <div className="gauge" style={{ width: W, height: H }}>
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} overflow="visible">
        <defs>
          <linearGradient id="gauge-grad" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%"   stopColor="#10b981" />
            <stop offset="40%"  stopColor="#f59e0b" />
            <stop offset="70%"  stopColor="#f97316" />
            <stop offset="100%" stopColor="#f43f5e" />
          </linearGradient>
          <filter id="gauge-glow">
            <feGaussianBlur stdDeviation="2" result="blur" />
            <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>

        {/* Track (background arc) */}
        <path
          d={trackPath}
          fill="none"
          stroke="var(--border-1)"
          strokeWidth="8"
          strokeLinecap="round"
        />

        {/* Fill arc */}
        {fillPath && (
          <path
            d={fillPath}
            fill="none"
            stroke="url(#gauge-grad)"
            strokeWidth="8"
            strokeLinecap="round"
            filter="url(#gauge-glow)"
            style={{
              transition: "stroke-dashoffset 0.8s cubic-bezier(0.16,1,0.3,1)",
            }}
          />
        )}

        {/* Tip dot */}
        {fillPath && (
          <circle
            cx={tip.x}
            cy={tip.y}
            r="5"
            fill={color}
            filter="url(#gauge-glow)"
          />
        )}
      </svg>

      {/* Score label absolutely centred */}
      <div className="score">
        <b style={{ color }}>{safeScore}</b>
        <small>/ 100</small>
      </div>
    </div>
  );
}
