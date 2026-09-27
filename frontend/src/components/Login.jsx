import { useState } from "react";
import { login, register } from "../api.js";
import { useToast } from "../context/ToastContext.jsx";

// Feature list shown in the hero
const FEATURES = [
  {
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
        strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="3" />
        <path d="M12 2v3M12 19v3M2 12h3M19 12h3" />
      </svg>
    ),
    title: "7 Specialist AI Agents",
    desc: "Structure · Metrics · Security · Risk · Refactor · Docs · Tests - each expert in its domain.",
  },
  {
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
        strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z" />
        <path d="M9 12l2 2 4-4" />
      </svg>
    ),
    title: "OWASP & CWE Grounded",
    desc: "Every finding cross-referenced to authoritative security standards with remediation guidance.",
  },
  {
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
        strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M9 3H5a2 2 0 0 0-2 2v4m6-6h10a2 2 0 0 1 2 2v4M9 3v18m0 0h10a2 2 0 0 0 2-2V9M9 21H5a2 2 0 0 1-2-2V9m0 0h18" />
      </svg>
    ),
    title: "Live Streaming Pipeline",
    desc: "Watch each agent execute in real-time with transparent ReAct reasoning traces.",
  },
];

// Agent pills for visual hero decoration
const AGENT_PILLS = [
  "Code Review", "Security Audit", "Risk Assessment",
  "Refactoring", "Documentation", "Test Generation", "Metrics",
];

export default function Login({ onAuthenticated }) {
  const [mode, setMode] = useState("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      if (mode === "register") {
        await register(username, password);
        toast.success("Account created", "Signing you in…");
      }
      await login(username, password);
      toast.success("Welcome to ARCAS", `Signed in as ${username}.`);
      onAuthenticated();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Authentication failed.";
      toast.error(
        mode === "register" ? "Registration failed" : "Sign in failed",
        msg
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-shell">
      {/* Hero Panel */}
      <div className="login-hero">
        <div className="login-hero-content">
          {/* Brand */}
          <div className="login-brand">
            <img className="login-brand-logo" src="/favicon.svg" alt="ARCAS" />
            <div>
              <div className="login-brand-name">
                ARCAS
                <span>Agentic Review &amp; Code Analysis</span>
              </div>
            </div>
          </div>

          {/* Headline */}
          <h1 className="login-hero-headline">
            Multi-agent<br />code review
          </h1>

          <p className="login-hero-sub">
            Specialised AI agents that review, secure, refactor,
            document and test your code, and show their reasoning
            at every step.
          </p>

          {/* Feature cards */}
          <div className="login-features">
            {FEATURES.map((f) => (
              <div className="login-feature" key={f.title}>
                <span className="lf-icon">{f.icon}</span>
                <div className="login-feature-text">
                  <h4>{f.title}</h4>
                  <p>{f.desc}</p>
                </div>
              </div>
            ))}
          </div>

          {/* Agent pills */}
          <div className="login-agents">
            {AGENT_PILLS.map((label) => (
              <span className="login-agent-pill" key={label}>
                <span className="lpill-dot" />
                {label}
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* Form Panel */}
      <div className="login-form-pane">
        <form className="login-form" onSubmit={submit}>
          <div className="login-form-header">
            <h2>
              {mode === "login" ? "Welcome back" : "Create account"}
            </h2>
            <p>
              {mode === "login"
                ? "Sign in to run the AI review pipeline."
                : "Register to start analysing code with ARCAS."}
            </p>
          </div>

          {/* Username */}
          <div className="float-field">
            <input
              id="login-username"
              type="text"
              placeholder=" "
              value={username}
              autoComplete="username"
              onChange={(e) => setUsername(e.target.value)}
              required
            />
            <label htmlFor="login-username">Username</label>
          </div>

          {/* Password */}
          <div className="float-field">
            <input
              id="login-password"
              type={showPw ? "text" : "password"}
              placeholder=" "
              value={password}
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
            <label htmlFor="login-password">Password</label>
            <button
              type="button"
              className="toggle-pw"
              onClick={() => setShowPw((s) => !s)}
              aria-label={showPw ? "Hide password" : "Show password"}
              tabIndex={-1}
            >
              {showPw ? (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M9.9 4.2A9.1 9.1 0 0 1 12 4c7 0 10 8 10 8a18 18 0 0 1-2.2 3.2M6.6 6.6A18 18 0 0 0 2 12s3 8 10 8a9 9 0 0 0 5.4-1.6M3 3l18 18M9.9 9.9a3 3 0 0 0 4.2 4.2" />
                </svg>
              ) : (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M2 12s3-8 10-8 10 8 10 8-3 8-10 8-10-8-10-8z" />
                  <circle cx="12" cy="12" r="3" />
                </svg>
              )}
            </button>
          </div>

          <button
            className="btn btn-primary"
            type="submit"
            disabled={busy || !username || !password}
            style={{ width: "100%", justifyContent: "center", padding: "12px 20px", fontSize: 14 }}
          >
            {busy ? (
              <><span className="spinner" /> Please wait…</>
            ) : mode === "login" ? (
              "Sign in to ARCAS"
            ) : (
              "Create account"
            )}
          </button>

          <div className="login-switch-row">
            {mode === "login" ? (
              <>
                No account?{" "}
                <button type="button" className="link" onClick={() => setMode("register")}>
                  Register
                </button>
              </>
            ) : (
              <>
                Already registered?{" "}
                <button type="button" className="link" onClick={() => setMode("login")}>
                  Sign in
                </button>
              </>
            )}
          </div>
        </form>
      </div>
    </div>
  );
}
