import { useState } from "react";

const AGENT_LABEL = {
  review_agent: "Code Review Agent",
  security_agent: "Security Agent",
  refactor_agent: "Refactor Agent",
  metrics_agent: "Metrics Agent",
  risk_agent: "Risk Agent",
  documentation_agent: "Documentation Agent",
  test_generation_agent: "Test Generation Agent",
};

const TYPE_LABEL = {
  thought: "Thought",
  action: "Action",
  observation: "Observation",
  final: "Answer",
};

function stepBody(step) {
  switch (step.type) {
    case "action":
      return `${step.tool || "tool"}(${step.input || ""})`;
    case "observation":
      return step.result || "(no output)";
    case "thought":
    case "final":
    default:
      return step.content || "";
  }
}

function AgentTrace({ name, steps, defaultOpen }) {
  const [open, setOpen] = useState(defaultOpen);
  const label = AGENT_LABEL[name] || name;
  const count = Array.isArray(steps) ? steps.length : 0;

  return (
    <div className={`reasoning-agent ${open ? "open" : ""}`}>
      <div className="reasoning-agent-head" onClick={() => setOpen((o) => !o)}>
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="3" />
          <path d="M12 2v3M12 19v3M2 12h3M19 12h3" />
        </svg>
        {label}
        <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: "var(--fs-xs)" }}>
          {count} step{count === 1 ? "" : "s"}
        </span>
        <svg className="chev" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="m9 18 6-6-6-6" />
        </svg>
      </div>
      {open && (
        <div className="reasoning-steps">
          {count === 0 && (
            <div className="empty-note">No reasoning steps recorded.</div>
          )}
          {Array.isArray(steps) &&
            steps.map((step, i) => (
              <div
                key={i}
                className={`reasoning-step ${step.type || "thought"}`}
                style={{ animationDelay: `${Math.min(i * 30, 240)}ms` }}
              >
                <span className="rs-type">
                  {TYPE_LABEL[step.type] || step.type}
                </span>
                <span className="rs-body">{stepBody(step)}</span>
              </div>
            ))}
        </div>
      )}
    </div>
  );
}

export default function ReasoningTrace({ traces }) {
  const agents = traces && typeof traces === "object" ? Object.keys(traces) : [];

  if (agents.length === 0) {
    return (
      <p className="empty-note">
        No reasoning traces were captured for this review. Reasoning traces are
        produced when the LLM agents run their ReAct loop.
      </p>
    );
  }

  return (
    <div>
      <p style={{ color: "var(--text-secondary)", marginTop: 0 }}>
        Step-by-step ReAct reasoning each agent followed - its thoughts, the
        tools it called, and what it observed before answering.
      </p>
      {agents.map((name, idx) => (
        <AgentTrace
          key={name}
          name={name}
          steps={traces[name]}
          defaultOpen={idx === 0}
        />
      ))}
    </div>
  );
}
