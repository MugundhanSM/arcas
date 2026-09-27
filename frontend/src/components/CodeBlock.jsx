import { useRef, useState } from "react";

export default function CodeBlock({ children, ...props }) {
  const preRef = useRef(null);
  const [state, setState] = useState("idle");  // "idle" | "copied" | "error"

  const handleCopy = () => {
    const text =
      preRef.current?.innerText ?? preRef.current?.textContent ?? "";

    if (!navigator.clipboard) {
      // Fallback for environments without the Clipboard API.
      try {
        const ta = document.createElement("textarea");
        ta.value = text;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.focus();
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
        setState("copied");
        setTimeout(() => setState("idle"), 2000);
      } catch {
        setState("error");
        setTimeout(() => setState("idle"), 2000);
      }
      return;
    }

    navigator.clipboard.writeText(text).then(
      () => {
        setState("copied");
        setTimeout(() => setState("idle"), 2000);
      },
      () => {
        setState("error");
        setTimeout(() => setState("idle"), 2000);
      }
    );
  };

  const label =
    state === "copied" ? "✓ Copied" : state === "error" ? "✕ Failed" : "Copy";

  return (
    <div className="code-block-wrapper">
      <button
        className={`copy-btn copy-btn--${state}`}
        onClick={handleCopy}
        aria-label="Copy code to clipboard"
        title="Copy code"
      >
        {label}
      </button>
      <pre ref={preRef} {...props}>
        {children}
      </pre>
    </div>
  );
}
