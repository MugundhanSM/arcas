import { useEffect, useRef } from "react";


const STAGE_LABEL = {
  intent_classifier:     "Intent",
  input_guardrails:      "Input Guard",
  review_agent:          "Code Review",
  metrics_agent:         "Metrics",
  security_agent:        "Security",
  risk_agent:            "Risk",
  refactor_agent:        "Refactor",
  output_guardrails:     "Output Guard",
  documentation_agent:   "Docs",
  test_generation_agent: "Tests",
  risk_finalize_agent:   "Risk Final",
};

const STAGE_DESC = {
  intent_classifier:     "Inferring analysis intent from the request",
  input_guardrails:      "Sanitising and validating source code",
  review_agent:          "Detecting code smells and anti-patterns",
  metrics_agent:         "Computing complexity and maintainability",
  security_agent:        "Scanning for OWASP vulnerabilities",
  risk_agent:            "Calculating composite risk score",
  refactor_agent:        "Generating SOLID-compliant refactor diff",
  output_guardrails:     "Verifying response schema and safety",
  documentation_agent:   "Writing docstrings and module summary",
  test_generation_agent: "Scaffolding unit tests and edge cases",
  risk_finalize_agent:   "Folding LLM findings into the final risk score",
};

const INTENT_PIPELINE = {
  full_review: [
    "input_guardrails", "review_agent", "metrics_agent", "security_agent",
    "risk_agent", "refactor_agent", "output_guardrails",
    "documentation_agent", "test_generation_agent", "risk_finalize_agent",
  ],
  security_audit:  ["input_guardrails", "security_agent", "risk_agent", "refactor_agent", "risk_finalize_agent", "output_guardrails"],
  refactor:        ["input_guardrails", "review_agent", "refactor_agent", "risk_finalize_agent", "output_guardrails"],
  documentation:   ["input_guardrails", "review_agent", "documentation_agent", "output_guardrails"],
  test_generation: ["input_guardrails", "review_agent", "test_generation_agent", "output_guardrails"],
  metrics:         ["input_guardrails", "metrics_agent", "output_guardrails"],
};

const INTENT_LABEL = {
  full_review:     "Full Review",
  security_audit:  "Security Audit",
  refactor:        "Refactor",
  documentation:   "Documentation",
  test_generation: "Test Generation",
  metrics:         "Metrics",
};

// Stage icons
function StageIcon({ name, size = 14 }) {
  const p = {
    width: size, height: size, viewBox: "0 0 24 24",
    fill: "none", stroke: "currentColor",
    strokeWidth: 2, strokeLinecap: "round", strokeLinejoin: "round",
  };
  switch (name) {
    case "intent_classifier":
      return <svg {...p}><circle cx="12" cy="12" r="9" /><path d="M9 9a3 3 0 0 1 5.12 2.12c0 2-3 2.5-3 4.5M12 17h.01" /></svg>;
    case "input_guardrails":
    case "output_guardrails":
      return <svg {...p}><path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z" /></svg>;
    case "review_agent":
      return <svg {...p}><path d="M3 6h18M3 12h18M3 18h12" /></svg>;
    case "metrics_agent":
      return <svg {...p}><path d="M4 19V5M10 19V9M16 19v-7M22 19H2" /></svg>;
    case "security_agent":
      return <svg {...p}><path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z" /><path d="M9 12l2 2 4-4" /></svg>;
    case "risk_agent":
      return <svg {...p}><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0zM12 9v4M12 17h.01" /></svg>;
    case "refactor_agent":
      return <svg {...p}><path d="M15 4V2M15 16v-2M8 9h2M20 9h2M17.8 11.8 19 13M15 9l-6 6M17.8 6.2 19 5M3 21l9-9" /></svg>;
    case "documentation_agent":
      return <svg {...p}><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><path d="M14 2v6h6M16 13H8M16 17H8" /></svg>;
    case "test_generation_agent":
      return <svg {...p}><path d="M9 2v6l-5 9a2 2 0 0 0 1.8 3h12.4A2 2 0 0 0 20 17l-5-9V2M8 2h8M7 14h10" /></svg>;
    case "risk_finalize_agent":
      return <svg {...p}><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0zM12 9v4M12 17h.01" /><path d="M5 21h14" /></svg>;
    default:
      return <svg {...p}><circle cx="12" cy="12" r="9" /></svg>;
  }
}

function CheckIcon({ size = 14 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M20 6 9 17l-5-5" />
    </svg>
  );
}

// Animated thinking dots
function ThinkingDots() {
  return (
    <span className="thinking-dots">
      <span /><span /><span />
    </span>
  );
}

// Pipeline node
function PipelineNode({ stageKey, status, isFirst }) {
  const state =
    status === "done" || status === "complete" ? "done" :
    status === "running" ? "running" :
    status === "failed"  ? "failed" : "pending";

  return (
    <div className="pipeline-node-wrap">
      {!isFirst && (
        <div className={`pipeline-connector ${state === "done" ? "done" : state === "running" ? "running" : ""}`} />
      )}
      <div className={`pipeline-node ${state}`}>
        <div className="pipeline-node-icon">
          <div className="pipeline-node-ring" />
          {state === "done"
            ? <CheckIcon size={14} />
            : <StageIcon name={stageKey} size={14} />
          }
        </div>
        <span className="pipeline-node-label">
          {STAGE_LABEL[stageKey] || stageKey}
        </span>
      </div>
    </div>
  );
}

// Main ActivityFeed
export default function ActivityFeed({ events, substeps = [], running, intent, language }) {
  const pipeline = INTENT_PIPELINE[intent] || INTENT_PIPELINE.full_review;
  const flowRef  = useRef(null);

  // Build status map from events
  const statusMap = {};
  for (const ev of events) {
    if (ev.status !== "substep") statusMap[ev.stage] = ev.status;
  }

  // Currently running stage
  const runningEvent = events.find((e) => e.status === "running");
  const runningStage = runningEvent?.stage || events[events.length - 1]?.stage;

  // Progress counting
  const doneCount = events.filter(
    (e) => (e.status === "done" || e.status === "complete") && pipeline.includes(e.stage)
  ).length;
  const totalCount = pipeline.length;
  const pct = totalCount ? Math.min(100, Math.round((doneCount / totalCount) * 100)) : 0;

  // Completed stages chips
  const completedStages = events.filter(
    (e) => e.status === "done" || e.status === "complete"
  );

  // Auto-scroll running node into view
  useEffect(() => {
    if (!flowRef.current || !runningStage) return;
    const el = flowRef.current.querySelector(".pipeline-node.running");
    if (el) el.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });
  }, [runningStage]);

  return (
    <div className="pipeline-shell">
      {/* Header */}
      <div className="pipeline-header">
        <div className="pipeline-intent-label">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" strokeWidth="2" strokeLinecap="round"
            strokeLinejoin="round" style={{ color: "var(--accent)" }}>
            <circle cx="12" cy="12" r="3" />
            <path d="M12 2v3M12 19v3M2 12h3M19 12h3" />
          </svg>
          {INTENT_LABEL[intent] || "Running Pipeline"}
        </div>
        <span className="pipeline-lang-badge">
          {(language || "code").toUpperCase()}
        </span>
      </div>

      {/* Overall progress bar */}
      <div className="pipeline-progress-wrap">
        <div className="pipeline-progress-label">
          <span>Pipeline progress</span>
          <span>{pct}%</span>
        </div>
        <div className="pipeline-progress-track">
          <div className="pipeline-progress-fill" style={{ width: `${pct}%` }} />
        </div>
      </div>

      {/* Node flow */}
      <div className="pipeline-flow" ref={flowRef}>
        {pipeline.map((stageKey, i) => (
          <PipelineNode
            key={stageKey}
            stageKey={stageKey}
            status={statusMap[stageKey] || "pending"}
            isFirst={i === 0}
          />
        ))}
      </div>

      {running && runningStage && (() => {
        const RECENT = 8;
        const recent = substeps.slice(-RECENT);
        const headStage =
          recent.length > 0 ? recent[recent.length - 1].stage : runningStage;

        return (
          <div className="stage-detail-box">
            <div className="stage-detail-title">
              <div className="stage-detail-icon">
                <StageIcon name={headStage} size={15} />
              </div>
              <div>
                <div style={{ fontWeight: 600, fontSize: 13 }}>
                  {STAGE_LABEL[headStage] || headStage}
                </div>
                <div className="stage-detail-desc">
                  {STAGE_DESC[headStage] || ""}
                </div>
              </div>
            </div>

            {recent.length > 0 && (
              <div className="stage-substeps">
                {recent.map((s, i) => {
                  const isLast = i === recent.length - 1;
                  const showTag =
                    i === 0 || recent[i - 1].stage !== s.stage;
                  return (
                    <div
                      key={s.id ?? `${s.stage}-${i}`}
                      className={`stage-substep ${isLast ? "active" : "done"}`}
                    >
                      <span className="stage-substep-dot" />
                      <span>
                        {showTag && (
                          <span className="stage-substep-tag">
                            {STAGE_LABEL[s.stage] || s.stage}
                          </span>
                        )}
                        {s.message}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}

            {recent.length === 0 && (
              <div className="stage-live-substep stage-live-substep--idle">
                <ThinkingDots />
                <span>{STAGE_DESC[headStage] || "Thinking…"}</span>
              </div>
            )}
          </div>
        );
      })()}

      {/* Completed agents chips */}
      {completedStages.length > 0 && (
        <div>
          <div style={{
            fontSize: 10, fontWeight: 700, letterSpacing: "0.06em",
            textTransform: "uppercase", color: "var(--text-4)", marginBottom: 6,
          }}>
            Completed
          </div>
          <div className="completed-agents">
            {completedStages.map((e) => (
              <span className="completed-agent-chip" key={e.stage}>
                <CheckIcon size={10} />
                {STAGE_LABEL[e.stage] || e.stage}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
