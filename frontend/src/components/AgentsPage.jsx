// Static, informational view of ARCAS's own architecture.

const AGENTS = [
  {
    icon: "review",
    name: "Code Review Agent",
    desc: "Runs a ReAct reasoning loop over Tree-sitter AST output to flag structural and quality issues, grounded in deterministic parse facts rather than guesswork.",
  },
  {
    icon: "metrics",
    name: "Metrics Agent",
    desc: "Computes cyclomatic complexity, Halstead volume, maintainability index, and comment density - deterministic, model-free measurement.",
  },
  {
    icon: "security",
    name: "Security Analysis Agent",
    desc: "Calls Semgrep's semantic static analysis to surface OWASP-aligned vulnerabilities, then explains each finding in plain language.",
  },
  {
    icon: "risk",
    name: "Risk Agent",
    desc: "Fuses static findings with AI-discovered issues into a single composite risk score, weighing severity, confidence, and blast radius.",
  },
  {
    icon: "refactor",
    name: "Refactoring Agent",
    desc: "Proposes context-aware refactors and emits a unified diff that's validated against the original AST before it's ever shown to you.",
  },
  {
    icon: "doc",
    name: "Documentation Agent",
    desc: "Writes docstrings and inline comments that follow the existing codebase's conventions and style guide.",
  },
  {
    icon: "test",
    name: "Test Generation Agent",
    desc: "Synthesises unit tests targeting the code paths the review just analysed, including edge cases and boundary conditions.",
  },
];

const LAYERS = [
  ["Presentation", "This web client - Monaco editor, live agent trace, and report viewer."],
  ["API Gateway", "FastAPI with JWT/OAuth2 auth and per-user rate limiting."],
  ["Input Guardrails", "PII redaction (Presidio), prompt-injection classification (Rebuff), syntax and language checks."],
  ["Orchestration", "LangGraph stateful multi-agent engine routing each request to the right agent(s)."],
  ["Agent Pool", "The seven specialist agents listed above."],
  ["Tool Layer", "Tree-sitter, Semgrep, Pylint, ESLint, Black and Prettier as callable, audited tools."],
  ["Knowledge & RAG", "ChromaDB vector store of code patterns, OWASP guidance, and language style guides."],
  ["Output Guardrails", "Diff/AST validation, hallucination detection (SelfCheckGPT), security-regression filtering, confidence scoring."],
  ["Persistence", "PostgreSQL for review history, Redis for session state."],
];

function AgentIcon({ name, size = 18 }) {
  const common = {
    width: size, height: size, viewBox: "0 0 24 24",
    fill: "none", stroke: "currentColor",
    strokeWidth: 1.8, strokeLinecap: "round", strokeLinejoin: "round",
  };
  switch (name) {
    case "review":
      return <svg {...common}><path d="M3 6h18M3 12h18M3 18h12" /></svg>;
    case "metrics":
      return <svg {...common}><path d="M4 19V5M10 19V9M16 19v-7M22 19H2" /></svg>;
    case "security":
      return <svg {...common}><path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z" /><path d="M9 12l2 2 4-4" /></svg>;
    case "risk":
      return <svg {...common}><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0zM12 9v4M12 17h.01" /></svg>;
    case "refactor":
      return <svg {...common}><path d="M15 4V2M15 16v-2M8 9h2M20 9h2M17.8 11.8 19 13M15 9l-6 6M17.8 6.2 19 5M3 21l9-9" /></svg>;
    case "doc":
      return <svg {...common}><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><path d="M14 2v6h6M16 13H8M16 17H8M10 9H8" /></svg>;
    case "test":
      return <svg {...common}><path d="M9 2v6l-5 9a2 2 0 0 0 1.8 3h12.4A2 2 0 0 0 20 17l-5-9V2M8 2h8M7 14h10" /></svg>;
    default:
      return null;
  }
}

export default function AgentsPage() {
  return (
    <div className="agents-page">
      <div className="agents-intro">
        <h2>Agent Pipeline</h2>
        <p>
          ARCAS coordinates seven specialist agents through a LangGraph
          orchestration engine. Two of them - metrics and risk - run
          deterministic, model-free analysis so every recommendation from
          the language-model agents is grounded in measurable facts rather
          than unverified judgment.
        </p>
      </div>

      <div className="agents-grid">
        {AGENTS.map((a) => (
          <div className="agent-card" key={a.name}>
            <div className="agent-card-head">
              <div className="agent-icon-wrap">
                <AgentIcon name={a.icon} />
              </div>
              <h3>{a.name}</h3>
            </div>
            <p>{a.desc}</p>
          </div>
        ))}
      </div>

      <div className="layers-section">
        <h2>9-Layer Architecture</h2>
        <p style={{ fontSize: 13, color: "var(--text-2)", marginBottom: 16, marginTop: -8 }}>
          The full request path each review travels through, end to end.
        </p>
        <div className="layers-list">
          {LAYERS.map(([title, desc], i) => (
            <div className="layer-row" key={title}>
              <span className="layer-num">{String(i + 1).padStart(2, "0")}</span>
              <div>
                <div className="layer-name">{title}</div>
                <div className="layer-desc">{desc}</div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
