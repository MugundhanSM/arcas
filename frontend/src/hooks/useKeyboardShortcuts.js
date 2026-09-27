import { useEffect } from "react";

// Registers global keyboard shortcuts for the duration of the component.
export default function useKeyboardShortcuts(shortcuts, deps = []) {
  useEffect(() => {
    if (!shortcuts) return undefined;

    const normalized = Object.entries(shortcuts).map(([combo, handler]) => {
      const parts = combo.toLowerCase().split("+").map((p) => p.trim());
      return {
        key: parts[parts.length - 1],
        mod: parts.includes("mod") || parts.includes("ctrl") || parts.includes("cmd"),
        shift: parts.includes("shift"),
        alt: parts.includes("alt"),
        handler,
      };
    });

    const isTypingTarget = (el) => {
      if (!el) return false;
      const tag = (el.tagName || "").toLowerCase();
      return (
        tag === "input" ||
        tag === "textarea" ||
        tag === "select" ||
        el.isContentEditable
      );
    };

    const onKeyDown = (e) => {
      const mod = e.metaKey || e.ctrlKey;
      const key = (e.key || "").toLowerCase();

      for (const s of normalized) {
        if (s.key !== key) continue;
        if (s.mod && !mod) continue;
        if (!s.mod && mod) continue;
        if (s.shift && !e.shiftKey) continue;
        if (s.alt && !e.altKey) continue;

        if (!s.mod && isTypingTarget(e.target)) continue;

        const optOut = s.handler(e);
        if (optOut !== true) e.preventDefault();
        return;
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}
