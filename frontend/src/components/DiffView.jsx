import { useState } from "react";
import { DiffEditor } from "@monaco-editor/react";

// Maps our language ids to Monaco's language ids where they differ.
const MONACO_LANG = {
  python: "python",
  java: "java",
  javascript: "javascript",
  typescript: "typescript",
  go: "go",
  ruby: "ruby",
  php: "php",
  c: "c",
  cpp: "cpp",
  csharp: "csharp",
};

// Fallback: render a unified-diff string with +/- colouring.
function UnifiedDiff({ diff }) {
  const lines = diff.split("\n");
  return (
    <pre className="diff">
      {lines.map((line, i) => {
        let cls = "diff-ctx";
        if (line.startsWith("+++") || line.startsWith("---")) cls = "diff-meta";
        else if (line.startsWith("@@")) cls = "diff-hunk";
        else if (line.startsWith("+")) cls = "diff-add";
        else if (line.startsWith("-")) cls = "diff-del";
        return (
          <div className={`diff-line ${cls}`} key={i}>
            {line || " "}
          </div>
        );
      })}
    </pre>
  );
}

// Side-by-side refactor diff.
export default function DiffView({
  original = "",
  modified = "",
  diff = "",
  language = "python",
  warnings = [],
  onApply,
}) {
  const [copied, setCopied] = useState(false);
  const [applied, setApplied] = useState(false);

  const hasMonacoDiff = Boolean(original && modified && original !== modified);
  const hasWarnings = Array.isArray(warnings) && warnings.length > 0;

  const copyDiff = () => {
    const text = diff || modified;
    if (!navigator.clipboard || !text) return;
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  const apply = () => {
    if (hasWarnings || !onApply) return;
    onApply(modified);
    setApplied(true);
    setTimeout(() => setApplied(false), 2400);
  };

  if (!hasMonacoDiff && (!diff || !diff.trim())) {
    return <p className="empty-note">No refactoring diff was produced.</p>;
  }

  return (
    <div>
      {hasWarnings && (
        <div className="workspace-banner">
          <strong>⚠ Workspace validation flagged this refactor</strong>
          {warnings.map((w, i) => (
            <div key={i}>• {w}</div>
          ))}
          <div style={{ color: "var(--text-muted)", marginTop: 4 }}>
            Apply is disabled until the refactor validates cleanly.
          </div>
        </div>
      )}

      {hasMonacoDiff ? (
        <div className="diff-editor-wrap">
          <div className="diff-editor-toolbar">
            <div className="legend">
              <span className="diff-legend-del">Original</span>
              <span className="diff-legend-add">Refactored (validated)</span>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <button className="btn btn-ghost" onClick={copyDiff}>
                {copied ? "✓ Copied" : "Copy"}
              </button>
              <button
                className="btn btn-primary"
                onClick={apply}
                disabled={hasWarnings || applied}
                title={
                  hasWarnings
                    ? "Resolve workspace warnings before applying"
                    : "Apply the refactored file to the editor"
                }
              >
                {applied ? "✓ Applied" : "Apply to editor"}
              </button>
            </div>
          </div>
          <div className="diff-editor-host">
            <DiffEditor
              height="100%"
              theme="vs-dark"
              original={original}
              modified={modified}
              language={MONACO_LANG[language] || "plaintext"}
              options={{
                renderSideBySide: true,
                readOnly: true,
                fontSize: 13,
                minimap: { enabled: false },
                scrollBeyondLastLine: false,
                automaticLayout: true,
                renderOverviewRuler: false,
              }}
            />
          </div>
        </div>
      ) : (
        <div className="code-block-wrapper">
          <button
            className={`copy-btn ${copied ? "copy-btn--copied" : ""}`}
            onClick={copyDiff}
            aria-label="Copy diff to clipboard"
          >
            {copied ? "✓ Copied" : "Copy diff"}
          </button>
          <UnifiedDiff diff={diff} />
        </div>
      )}
    </div>
  );
}
