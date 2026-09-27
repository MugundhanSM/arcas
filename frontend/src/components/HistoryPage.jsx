import { useMemo, useState, useRef } from "react";

function riskClass(level) {
  const l = (level || "").toUpperCase();
  if (l === "CRITICAL") return "CRITICAL";
  if (l === "HIGH") return "HIGH";
  if (l === "MEDIUM") return "MEDIUM";
  return "LOW";
}

function timeAgo(iso) {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return iso;
  const diff = Math.max(0, Date.now() - then);
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(iso).toLocaleDateString();
}

const INTENT_LABEL = {
  full_review:     "Full review",
  security_audit:  "Security audit",
  refactor:        "Refactor",
  documentation:   "Documentation",
  test_generation: "Tests",
  metrics:         "Metrics",
  auto:            "Auto",
};

// Inline rename component
function WorkspaceName({ name, onRename }) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(name || "Untitled Workspace");
  const inputRef = useRef(null);

  const commit = () => {
    setEditing(false);
    const trimmed = value.trim() || "Untitled Workspace";
    setValue(trimmed);
    onRename(trimmed);
  };

  if (editing) {
    return (
      <input
        ref={inputRef}
        className="history-name-input"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") commit();
          if (e.key === "Escape") {
            setEditing(false);
            setValue(name || "Untitled Workspace");
          }
          e.stopPropagation();  // don't bubble to card button
        }}
        onClick={(e) => e.stopPropagation()}
        maxLength={60}
        autoFocus
      />
    );
  }

  return (
    <div className="history-name-row" onClick={(e) => {
      e.stopPropagation();
      setEditing(true);
      setTimeout(() => inputRef.current?.select(), 10);
    }}>
      <span className="history-name-text">{value}</span>
      <svg width="11" height="11" viewBox="0 0 24 24" fill="none"
        stroke="currentColor" strokeWidth="2" strokeLinecap="round"
        strokeLinejoin="round" className="history-name-edit-icon">
        <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
        <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
      </svg>
    </div>
  );
}

export default function HistoryPage({
  reviews = [],
  loading,
  busyId,
  onRestore,
  onRename,
}) {
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return reviews;
    return reviews.filter((r) => {
      const hay = [
        r.session_id,
        r.language,
        r.intent,
        r.source_preview,
        r.risk_level,
        r.workspace_name,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return hay.includes(q);
    });
  }, [reviews, query]);

  return (
    <div className="history-page">
      <div className="history-toolbar">
        <div className="history-search">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="11" cy="11" r="7" />
            <path d="m21 21-4.3-4.3" />
          </svg>
          <input
            value={query}
            placeholder="Search history by name, language, intent, code…"
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <span className="mono" style={{ color: "var(--text-muted)" }}>
          {filtered.length} review{filtered.length === 1 ? "" : "s"}
        </span>
      </div>

      {loading && (
        <div className="history-grid">
          {Array.from({ length: 4 }).map((_, i) => (
            <div className="history-card" key={i} style={{ cursor: "default" }}>
              <div className="skeleton" style={{ height: 18, width: "55%" }} />
              <div className="skeleton" style={{ height: 70 }} />
              <div className="skeleton" style={{ height: 14, width: "40%" }} />
            </div>
          ))}
        </div>
      )}

      {!loading && filtered.length === 0 && (
        <div className="placeholder">
          <svg width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="9" />
            <path d="M12 7v5l4 2" />
          </svg>
          <div>
            {query
              ? "No reviews match your search."
              : "No reviews yet. Run your first analysis to see it here."}
          </div>
        </div>
      )}

      {!loading && filtered.length > 0 && (
        <div className="history-grid">
          {filtered.map((r, i) => {
            const findings = r.finding_count ?? 0;
            const isBusy = busyId === r.session_id;
            return (
              <button
                className="history-card"
                key={r.session_id}
                style={{ animationDelay: `${Math.min(i * 40, 320)}ms` }}
                onClick={() => onRestore(r.session_id)}
                disabled={isBusy}
                title="Open this review"
              >
                {/* Workspace name - double-click or pencil to rename */}
                <WorkspaceName
                  name={r.workspace_name}
                  onRename={(newName) => onRename?.(r.session_id, newName)}
                />

                <div className="history-card-top">
                  <div className="history-card-meta">
                    <span className="badge LOW">{r.language}</span>
                    <span className="intent-badge">
                      {INTENT_LABEL[r.intent] || r.intent || "Review"}
                    </span>
                  </div>
                  <span className={`badge ${riskClass(r.risk_level)}`}>
                    {(r.risk_level || "-").toUpperCase()}
                  </span>
                </div>

                <pre className="preview">
                  {(r.source_preview || "// (source unavailable)").slice(0, 240)}
                </pre>

                <div className="history-card-foot">
                  <span className="history-stat">
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z" />
                    </svg>
                    {findings} finding{findings === 1 ? "" : "s"}
                  </span>
                  {typeof r.maintainability_index === "number" && (
                    <span className="history-stat">MI {r.maintainability_index}</span>
                  )}
                  <span>{isBusy ? "Opening…" : timeAgo(r.created_at)}</span>
                </div>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
