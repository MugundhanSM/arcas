import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import RiskGauge from "./RiskGauge.jsx";
import SecurityTable from "./SecurityTable.jsx";
import StructureView from "./StructureView.jsx";
import DiffView from "./DiffView.jsx";
import GuardrailPanel from "./GuardrailPanel.jsx";
import CodeBlock from "./CodeBlock.jsx";
import ReasoningTrace from "./ReasoningTrace.jsx";
import { submitFeedback } from "../api.js";
import { useToast } from "../context/ToastContext.jsx";

const MD_COMPONENTS = { pre: CodeBlock };

const INTENT_LABEL = {
  full_review:    "Full Review",
  security_audit: "Security Audit",
  refactor:       "Refactor",
  documentation:  "Documentation",
  test_generation:"Tests",
  metrics:        "Metrics",
  auto:           "Auto",
};

// Clamp + percentage helper
function pctBar(value, min, max) {
  if (value == null) return 0;
  return Math.round(Math.max(0, Math.min(100, ((value - min) / (max - min)) * 100)));
}

// Maintainability index bar class
function miClass(val) {
  if (val == null) return "accent";
  if (val >= 70)  return "success";
  if (val >= 40)  return "warn";
  return "danger";
}
function ccClass(val) {
  if (val == null) return "accent";
  if (val <= 5)  return "success";
  if (val <= 15) return "warn";
  return "danger";
}

// Small inline icon
function Icon({ name, size = 14, color }) {
  const p = {
    width: size, height: size, viewBox: "0 0 24 24",
    fill: "none", stroke: color || "currentColor",
    strokeWidth: 1.8, strokeLinecap: "round", strokeLinejoin: "round",
  };
  switch (name) {
    case "shield":  return <svg {...p}><path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z" /></svg>;
    case "code":    return <svg {...p}><path d="M9 6 4 12l5 6M15 6l5 6-5 6M13 4l-2 16" /></svg>;
    case "metric":  return <svg {...p}><path d="M4 19V5M10 19V9M16 19v-7M22 19H2" /></svg>;
    case "check":   return <svg {...p}><path d="M20 6 9 17l-5-5" /></svg>;
    case "up":      return <svg {...p}><path d="M7 10v12M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H7a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h2.76a2 2 0 0 0 1.79-1.11L14 2a3 3 0 0 1 1 3.88z" /></svg>;
    case "down":    return <svg {...p}><path d="M17 14V2M9 18.12 10 14H4.17a2 2 0 0 1-1.92-2.56l2.33-8A2 2 0 0 1 6.5 2H17a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2.76a2 2 0 0 0-1.79 1.11L10 22a3 3 0 0 1-1-3.88z" /></svg>;
    default:        return <svg {...p}><circle cx="12" cy="12" r="9" /></svg>;
  }
}

// Feedback thumbs
function FeedbackBar({ sessionId, agent }) {
  const [rating, setRating] = useState(0);
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  const send = async (value) => {
    if (busy || !sessionId) return;
    setBusy(true);
    const next = rating === value ? 0 : value;
    setRating(next);
    try {
      if (next !== 0) {
        await submitFeedback(sessionId, next, "", agent || "");
        toast.success("Thanks for the feedback", "It helps improve ARCAS.");
      }
    } catch (err) {
      toast.error("Could not send feedback", err.message || "");
      setRating(0);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="feedback-bar">
      <span>Was this helpful?</span>
      <button
        className={`feedback-btn up ${rating === 1 ? "active up" : ""}`}
        onClick={() => send(1)}
        disabled={busy}
        aria-label="Helpful"
      >
        <Icon name="up" size={12} />
        Yes
      </button>
      <button
        className={`feedback-btn down ${rating === -1 ? "active down" : ""}`}
        onClick={() => send(-1)}
        disabled={busy}
        aria-label="Not helpful"
      >
        <Icon name="down" size={12} />
        No
      </button>
    </div>
  );
}

// Quick-stat card with progress bar
function QSCard({ label, value, sub, barPct, barClass }) {
  return (
    <div className="qs-card">
      <div className="qs-label">{label}</div>
      <div className="qs-value">{value ?? "-"}</div>
      {sub && <div className="qs-sub">{sub}</div>}
      {typeof barPct === "number" && (
        <div className="qs-bar">
          <div className={`qs-bar-fill ${barClass || "accent"}`} style={{ width: `${barPct}%` }} />
        </div>
      )}
    </div>
  );
}

// Overview tab content
function OverviewTab({ result, risk_analysis, metrics, security_findings }) {
  const intentConfPct =
    typeof result.intent_confidence === "number"
      ? Math.round(result.intent_confidence * 100)
      : null;

  const total = risk_analysis.finding_count ?? security_findings.length;
  const aiCount = risk_analysis.ai_finding_count || 0;

  const riskColor = {
    CRITICAL: "var(--risk-critical)",
    HIGH: "var(--risk-high)",
    MEDIUM: "var(--risk-medium)",
    LOW: "var(--risk-low)",
  }[risk_analysis.risk_level?.toUpperCase()] || "var(--info)";

  return (
    <div className="overview-section">
      {/* Risk overview card */}
      <div className="overview-risk-row">
        <RiskGauge
          score={risk_analysis.risk_score}
          level={risk_analysis.risk_level}
        />
        <div className="overview-risk-info">
          <div className="overview-risk-label">Overall Risk Score</div>
          <div className="overview-risk-level" style={{ color: riskColor }}>
            {risk_analysis.risk_level || "-"}
          </div>
          <div className="overview-risk-meta">
            {result.intent && (
              <span className="intent-badge">
                {INTENT_LABEL[result.intent] || result.intent}
                {intentConfPct !== null && (
                  <span style={{ opacity: 0.7 }}> · {intentConfPct}%</span>
                )}
              </span>
            )}
            <span style={{ color: "var(--text-4)" }}>·</span>
            <span>
              {total} finding{total !== 1 ? "s" : ""}
              {aiCount > 0 && (
                <span style={{ opacity: 0.65 }}>
                  {" "}({security_findings.length} static · {aiCount} AI)
                </span>
              )}
            </span>
            {metrics.maintainability_rating && (
              <>
                <span style={{ color: "var(--text-4)" }}>·</span>
                <span>
                  Maintainability{" "}
                  <span className={`badge ${metrics.maintainability_rating}`}>
                    {metrics.maintainability_rating}
                  </span>
                </span>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Quick stats */}
      <div className="overview-quick-stats">
        <QSCard
          label="Lines of Code"
          value={metrics.code_lines}
          sub={`${metrics.total_lines} total incl. blanks`}
          barPct={pctBar(metrics.code_lines, 0, 500)}
          barClass="accent"
        />
        <QSCard
          label="Complexity"
          value={metrics.cyclomatic_complexity}
          sub={`${metrics.avg_complexity_per_function ?? "-"}/fn avg`}
          barPct={pctBar(metrics.cyclomatic_complexity, 0, 30)}
          barClass={ccClass(metrics.cyclomatic_complexity)}
        />
        <QSCard
          label="Maintainability"
          value={metrics.maintainability_index}
          sub={`Rating: ${metrics.maintainability_rating || "-"}`}
          barPct={pctBar(metrics.maintainability_index, 0, 100)}
          barClass={miClass(metrics.maintainability_index)}
        />
        <QSCard
          label="Functions"
          value={metrics.function_count}
          sub={`${metrics.class_count ?? 0} class${metrics.class_count !== 1 ? "es" : ""}`}
          barPct={pctBar(metrics.function_count, 0, 20)}
          barClass="accent"
        />
        <QSCard
          label="Comment Ratio"
          value={`${Math.round((metrics.comment_ratio || 0) * 100)}%`}
          sub={`${metrics.comment_lines ?? 0} comment lines`}
          barPct={Math.round((metrics.comment_ratio || 0) * 100)}
          barClass="success"
        />
        <QSCard
          label="Security Issues"
          value={total}
          sub={`${aiCount > 0 ? aiCount + " AI-identified" : "Static analysis"}`}
          barPct={pctBar(total, 0, 10)}
          barClass={total > 4 ? "danger" : total > 1 ? "warn" : "success"}
        />
      </div>

      {/* Security table preview */}
      {security_findings.length > 0 && (
        <div>
          <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.07em", textTransform: "uppercase", color: "var(--text-3)", marginBottom: 8 }}>
            Security Findings
          </div>
          <SecurityTable findings={security_findings.slice(0, 5)} />
          {security_findings.length > 5 && (
            <div style={{ fontSize: 11, color: "var(--text-3)", textAlign: "center", padding: "8px 0" }}>
              +{security_findings.length - 5} more - see the Security tab
            </div>
          )}
        </div>
      )}

      <FeedbackBar sessionId={result.session_id} />
    </div>
  );
}

// Main ResultsPanel
export default function ResultsPanel({ result, onApplyRefactor }) {
  const [tab, setTab] = useState("overview");
  const {
    risk_analysis  = {},
    metrics        = {},
    security_findings = [],
    warnings          = [],
    react_traces      = {},
    workspace_warnings= [],
  } = result;
  const guardrail    = result.output_guardrail || {};
  const confidencePct =
    typeof guardrail.confidence === "number"
      ? Math.round(guardrail.confidence * 100)
      : null;
  const traceCount = react_traces ? Object.keys(react_traces).length : 0;

  const TABS = [
    { id: "overview",   label: "Overview" },
    { id: "security",   label: "Security",  count: security_findings.length },
    { id: "structure",  label: "Structure" },
    { id: "refactor",   label: "Refactor" },
    { id: "diff",       label: "Diff" },
    { id: "reasoning",  label: "Reasoning", count: traceCount || undefined },
    { id: "docs",       label: "Docs" },
    { id: "tests",      label: "Tests" },
    { id: "guardrails", label: "Guardrails" },
  ];

  return (
    <div className="results">
      {/* Warning banners */}
      {warnings?.length > 0 && (
        <div className="warning-banner">
          {warnings.map((w, i) => <div key={i}>⚠ {w}</div>)}
        </div>
      )}
      {guardrail.security_regressions?.length > 0 && (
        <div className="error-banner">
          <strong>Output guardrails flagged the AI suggestion:</strong>
          {guardrail.security_regressions.map((r, i) => (
            <div key={i}>• {r}</div>
          ))}
        </div>
      )}

      {/* Metric strip cards */}
      <div className="cards">
        {[
          { label: "LOC",         value: metrics.code_lines,            sub: `${metrics.total_lines ?? "-"} total` },
          { label: "Complexity",  value: metrics.cyclomatic_complexity,  sub: `${metrics.avg_complexity_per_function ?? "-"}/fn` },
          { label: "Maintain.",   value: metrics.maintainability_index,  sub: `rating ${metrics.maintainability_rating ?? "-"}` },
          { label: "Functions",   value: metrics.function_count,         sub: `${metrics.class_count ?? 0} classes` },
          { label: "Comments",    value: `${Math.round((metrics.comment_ratio || 0) * 100)}%`, sub: `${metrics.comment_lines ?? 0} lines` },
          ...(confidencePct !== null
            ? [{ label: "AI Conf.", value: `${confidencePct}%`, sub: guardrail.passed ? "passed" : "review" }]
            : []),
        ].map(({ label, value, sub }, i) => (
          <div className="card" key={i}>
            <div className="label">{label}</div>
            <div className="value">{value ?? "-"}</div>
            <div className="sub">{sub}</div>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div className="tabs">
        {TABS.map(({ id, label, count }) => (
          <button
            key={id}
            className={`tab ${tab === id ? "active" : ""}`}
            onClick={() => setTab(id)}
          >
            {label}
            {count != null && count > 0 && (
              <span className="count">{count}</span>
            )}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div style={{ flex: 1 }}>
        {tab === "overview" && (
          <OverviewTab
            result={result}
            risk_analysis={risk_analysis}
            metrics={metrics}
            security_findings={security_findings}
          />
        )}

        {tab === "security" && (
          <div>
            <SecurityTable findings={security_findings} />
            <div style={{ padding: "0 16px" }}>
              <FeedbackBar sessionId={result.session_id} agent="security_agent" />
            </div>
          </div>
        )}

        {tab === "structure" && (
          <StructureView structure={result.review_findings} />
        )}

        {tab === "refactor" && (
          <div className="markdown">
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={MD_COMPONENTS}>
              {result.refactor_recommendations || "_No recommendations._"}
            </ReactMarkdown>
            <FeedbackBar sessionId={result.session_id} agent="refactor_agent" />
          </div>
        )}

        {tab === "diff" && (
          <DiffView
            original={result.source_code || ""}
            modified={result.refactored_code || ""}
            diff={result.refactor_diff}
            language={result.language}
            warnings={workspace_warnings}
            onApply={onApplyRefactor}
          />
        )}

        {tab === "reasoning" && (
          <ReasoningTrace traces={react_traces} />
        )}

        {tab === "docs" && (
          <div className="markdown">
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={MD_COMPONENTS}>
              {result.documentation || "_No documentation generated._"}
            </ReactMarkdown>
            <FeedbackBar sessionId={result.session_id} agent="documentation_agent" />
          </div>
        )}

        {tab === "tests" && (
          <div className="markdown">
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={MD_COMPONENTS}>
              {result.generated_tests || "_No tests generated._"}
            </ReactMarkdown>
            <FeedbackBar sessionId={result.session_id} agent="test_generation_agent" />
          </div>
        )}

        {tab === "guardrails" && (
          <GuardrailPanel warnings={warnings} guardrail={guardrail} />
        )}
      </div>
    </div>
  );
}
