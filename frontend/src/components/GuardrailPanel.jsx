// Visualises both input-guardrail warnings and output-guardrail signals.
export default function GuardrailPanel({ warnings, guardrail }) {
  const g = guardrail || {};
  const confidencePct =
    typeof g.confidence === "number" ? Math.round(g.confidence * 100) : null;

  return (
    <div className="guardrail-panel">
      <div className="struct-group">
        <h4>Input Guardrails (Layer 3)</h4>
        {warnings && warnings.length ? (
          <ul className="guard-list">
            {warnings.map((w, i) => (
              <li key={i} className="guard-warn">
                ⚠ {w}
              </li>
            ))}
          </ul>
        ) : (
          <p className="empty-note">
            No PII, prompt-injection or syntax issues detected on input.
          </p>
        )}
      </div>

      <div className="struct-group">
        <h4>Output Guardrails (Layer 8)</h4>
        {confidencePct !== null && (
          <div className="guard-confidence">
            <div className="label">AI Confidence</div>
            <div className="conf-bar">
              <div
                className="conf-fill"
                style={{
                  width: `${confidencePct}%`,
                  background:
                    confidencePct >= 70
                      ? "var(--ok)"
                      : confidencePct >= 40
                        ? "var(--warn)"
                        : "var(--danger)",
                }}
              />
            </div>
            <div className="sub">
              {confidencePct}% - {g.passed ? "guardrails passed" : "review needed"}
            </div>
          </div>
        )}

        {g.security_regressions && g.security_regressions.length > 0 && (
          <div className="error-banner" style={{ marginTop: 12 }}>
            <strong>Security regressions in suggestion:</strong>
            {g.security_regressions.map((r, i) => (
              <div key={i}>• {r}</div>
            ))}
          </div>
        )}

        {g.hallucination_warnings && g.hallucination_warnings.length > 0 && (
          <div className="warning-banner" style={{ marginTop: 12 }}>
            {g.hallucination_warnings.map((h, i) => (
              <div key={i}>⚠ {h}</div>
            ))}
          </div>
        )}

        {g.notes && g.notes.length > 0 && (
          <ul className="guard-list">
            {g.notes.map((n, i) => (
              <li key={i}>{n}</li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
