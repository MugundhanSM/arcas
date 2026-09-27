import { Fragment, useState } from "react";

function confidenceClass(pct) {
  if (pct >= 90) return "high";
  if (pct >= 70) return "medium";
  return "low";
}

function ConfidencePill({ value }) {
  if (typeof value !== "number") return null;
  const pct = value <= 1 ? Math.round(value * 100) : Math.round(value);
  return (
    <span className={`conf-pill ${confidenceClass(pct)}`} title="Detection confidence">
      {pct}%
    </span>
  );
}

export default function SecurityTable({ findings }) {
  const [open, setOpen] = useState({});

  if (!findings || !findings.length) {
    return (
      <p className="empty-note">
        No security findings were reported by the static analysis engine.
      </p>
    );
  }

  const toggle = (i) => setOpen((p) => ({ ...p, [i]: !p[i] }));

  return (
    <table>
      <thead>
        <tr>
          <th>Severity</th>
          <th>Lines</th>
          <th>Issue</th>
          <th>Standard</th>
          <th>Confidence</th>
        </tr>
      </thead>
      <tbody>
        {findings.map((f, i) => {
          const lines =
            `${f.start_line ?? ""}` +
            (f.end_line && f.end_line !== f.start_line ? `-${f.end_line}` : "");
          const hasDetail = f.explanation || f.remediation;
          const owasp = f.owasp_reference;
          const cwe = f.cwe_reference;
          return (
            <Fragment key={i}>
              <tr
                onClick={() => hasDetail && toggle(i)}
                style={{ cursor: hasDetail ? "pointer" : "default" }}
              >
                <td>
                  <span className={`badge ${f.severity || "INFO"}`}>
                    {f.severity || "INFO"}
                  </span>
                </td>
                <td className="mono">{lines || "-"}</td>
                <td>
                  {f.message || "-"}
                  {hasDetail && (
                    <span style={{ color: "var(--text-muted)", marginLeft: 6 }}>
                      {open[i] ? "▾" : "▸"}
                    </span>
                  )}
                </td>
                <td className="mono" style={{ color: "var(--text-dim)" }}>
                  {owasp || cwe ? (
                    <span style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                      {owasp && <span>{owasp}</span>}
                      {cwe && <span>{cwe}</span>}
                    </span>
                  ) : (
                    (f.check_id && f.check_id.split(".").pop()) || "-"
                  )}
                </td>
                <td>
                  <ConfidencePill value={f.confidence} />
                </td>
              </tr>
              {hasDetail && open[i] && (
                <tr key={`${i}-detail`} className="finding-detail-row">
                  <td colSpan={5}>
                    <div className="finding-detail">
                      {f.explanation && (
                        <div className="fd-block">
                          <span className="fd-label">Why it matters</span>
                          <p>{f.explanation}</p>
                        </div>
                      )}
                      {f.remediation && (
                        <div className="fd-block">
                          <span className="fd-label">Remediation</span>
                          <p>{f.remediation}</p>
                        </div>
                      )}
                      {f.check_id && (
                        <div className="fd-rule mono">{f.check_id}</div>
                      )}
                    </div>
                  </td>
                </tr>
              )}
            </Fragment>
          );
        })}
      </tbody>
    </table>
  );
}
