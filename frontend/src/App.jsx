import { useEffect, useRef, useState, useCallback } from "react";
import Editor from "@monaco-editor/react";
import {
  reviewCode,
  fetchReviews,
  fetchReviewRestore,
  fetchHealth,
  streamReview,
  getToken,
  logout,
  currentUser,
  updateWorkspaceName,
} from "./api.js";
import ResultsPanel from "./components/ResultsPanel.jsx";
import Login from "./components/Login.jsx";
import Sidebar from "./components/Sidebar.jsx";
import AgentsPage from "./components/AgentsPage.jsx";
import ActivityFeed from "./components/ActivityFeed.jsx";
import HistoryPage from "./components/HistoryPage.jsx";
import { useToast } from "./context/ToastContext.jsx";
import useKeyboardShortcuts from "./hooks/useKeyboardShortcuts.js";

const LANGUAGES = [
  { id: "python",     label: "Python" },
  { id: "java",       label: "Java" },
  { id: "javascript", label: "JavaScript" },
  { id: "typescript", label: "TypeScript" },
  { id: "go",         label: "Go" },
  { id: "ruby",       label: "Ruby" },
  { id: "php",        label: "PHP" },
  { id: "c",          label: "C" },
  { id: "cpp",        label: "C++" },
  { id: "csharp",     label: "C#" },
];

const INTENTS = [
  { id: "auto",           label: "Auto-detect" },
  { id: "full_review",    label: "Full review" },
  { id: "security_audit", label: "Security audit" },
  { id: "refactor",       label: "Refactor" },
  { id: "documentation",  label: "Documentation" },
  { id: "test_generation",label: "Tests" },
  { id: "metrics",        label: "Metrics" },
];

const STAGE_ICON = {
  intent_classifier:     "thinking",
  input_guardrails:      "shield",
  review_agent:          "structure",
  metrics_agent:         "metrics",
  security_agent:        "shield",
  risk_agent:            "risk",
  refactor_agent:        "wand",
  output_guardrails:     "shield",
  documentation_agent:   "doc",
  test_generation_agent: "test",
  risk_finalize_agent:   "risk",
};

function stageLabel(stage) {
  return stage
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

const SAMPLE = `import subprocess

def run(user_input):
    # Unsafe: command injection via shell=True
    return subprocess.call(user_input, shell=True)

password = "hardcoded-secret-123"
run(input("cmd> "))
`;

const VIEW_META = {
  workspace: {
    title: "Workspace",
    sub:   "Paste code and run the multi-agent review pipeline.",
  },
  agents: {
    title: "Agent Pipeline",
    sub:   "Architecture and responsibilities of each AI agent.",
  },
  history: {
    title: "Review History",
    sub:   "Browse and restore any previous analysis session.",
  },
};

function PlayIcon({ size = 14 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor">
      <polygon points="5 3 19 12 5 21 5 3" />
    </svg>
  );
}

function StopIcon({ size = 14 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor">
      <rect x="3" y="3" width="18" height="18" rx="2" />
    </svg>
  );
}

function PencilIcon({ size = 13 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
      <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
    </svg>
  );
}

// Workspace name storage (localStorage)
const WS_NAMES_KEY = "arcas_workspace_names";

function getStoredNames() {
  try { return JSON.parse(localStorage.getItem(WS_NAMES_KEY) || "{}"); }
  catch { return {}; }
}

function storeWorkspaceName(sessionId, name) {
  if (!sessionId) return;
  const names = getStoredNames();
  names[sessionId] = name;
  try { localStorage.setItem(WS_NAMES_KEY, JSON.stringify(names)); } catch {}
}

function getWorkspaceName(sessionId) {
  if (!sessionId) return null;
  return getStoredNames()[sessionId] || null;
}

export default function App() {
  const toast = useToast();
  const [authed,          setAuthed]          = useState(false);
  const [authRequired,    setAuthRequired]    = useState(false);
  const [forceLogin,      setForceLogin]      = useState(false);
  const [username,        setUsername]        = useState("");
  const [code,            setCode]            = useState(SAMPLE);
  const [language,        setLanguage]        = useState("python");
  const [intent,          setIntent]          = useState("auto");
  const [detectedIntent,  setDetectedIntent]  = useState(null);
  const [requestText,     setRequestText]     = useState("");
  const [streaming,       setStreaming]       = useState(true);
  const [loading,         setLoading]         = useState(false);
  const [result,          setResult]          = useState(null);
  const [error,           setError]           = useState(null);
  const [online,          setOnline]          = useState(null);
  const [history,         setHistory]         = useState([]);
  const [historyLoading,  setHistoryLoading]  = useState(false);
  const [restoringId,     setRestoringId]     = useState(null);
  const [pipelineEvents,  setPipelineEvents]  = useState([]);
  const [substeps,        setSubsteps]        = useState([]);
  const [view,            setView]            = useState("workspace");
  const [workspaceName,   setWorkspaceName]   = useState("Untitled Workspace");
  const [editingName,     setEditingName]     = useState(false);
  const [currentSessionId, setCurrentSessionId] = useState(null);
  const connRef = useRef(null);
  const nameInputRef = useRef(null);

  // Health check
  useEffect(() => {
    fetchHealth()
      .then((h) => {
        setOnline(true);
        setAuthRequired(Boolean(h.auth_required));
      })
      .catch(() => setOnline(false));
  }, []);

  const gateOpen = !forceLogin && (authed || getToken() || !authRequired);

  // Resolve username
  useEffect(() => {
    if (!getToken()) { setUsername(""); return; }
    currentUser()
      .then((u) => setUsername(u?.username || u?.sub || ""))
      .catch(() => setUsername(""));
  }, [authed]);

  // When session id changes, load its stored name
  useEffect(() => {
    if (currentSessionId) {
      const stored = getWorkspaceName(currentSessionId);
      if (stored) setWorkspaceName(stored);
    }
  }, [currentSessionId]);

  const loadHistory = async () => {
    setHistoryLoading(true);
    try { setHistory(await fetchReviews()); }
    catch { /* ignore */ }
    finally { setHistoryLoading(false); }
  };

  const finish = (res) => {
    setResult(res);
    setLoading(false);
    setPipelineEvents([]);
    setSubsteps([]);
    const sid = res?.session_id;
    setCurrentSessionId(sid);
    // Persist the workspace name for this session
    if (sid && workspaceName && workspaceName !== "Untitled Workspace") {
      storeWorkspaceName(sid, workspaceName);
      // Also try to save server-side
      updateWorkspaceName(sid, workspaceName).catch(() => {});
    }
    loadHistory();
    const findings = res?.security_findings?.length || 0;
    toast.success(
      "Analysis complete",
      `${findings} finding${findings === 1 ? "" : "s"} · ${res?.risk_analysis?.risk_level || "reviewed"}`
    );
  };

  const stopAnalysis = useCallback(() => {
    if (connRef.current) {
      connRef.current.close();
      connRef.current = null;
    }
    setLoading(false);
    setPipelineEvents([]);
    toast.info("Analysis stopped", "Pipeline was interrupted.");
  }, []);

  const newWorkspace = useCallback(() => {
    if (loading) stopAnalysis();
    setCode(SAMPLE);
    setResult(null);
    setError(null);
    setPipelineEvents([]);
    setDetectedIntent(null);
    setWorkspaceName("Untitled Workspace");
    setCurrentSessionId(null);
    setView("workspace");
    toast.info("New workspace", "Ready for a fresh analysis.");
  }, [loading, stopAnalysis]);

  const analyze = async () => {
    if (loading || !code.trim()) return;
    setLoading(true);
    setError(null);
    setResult(null);
    setPipelineEvents([]);
    setSubsteps([]);
    setDetectedIntent(null);

    if (streaming) {
      connRef.current = streamReview(
        code, language,
        {
          onStage: (msg) => {
            if (msg.stage === "intent_classifier") {
              setDetectedIntent(msg.intent || null);
              toast.info(
                "Intent detected",
                `${msg.intent} (${Math.round((msg.confidence || 0) * 100)}%)`
              );
            }
            if (msg.status === "substep") {
              setSubsteps((prev) => [
                ...prev,
                { stage: msg.stage, message: msg.message, id: prev.length },
              ]);
              setPipelineEvents((prev) => {
                const idx = prev.findIndex((e) => e.stage === msg.stage);
                if (idx >= 0) {
                  const next = [...prev];
                  const log = next[idx].substepLog || [];
                  next[idx] = { ...next[idx], substepLog: [...log, msg.message] };
                  return next;
                }
                return prev;
              });
              return;
            }
            setPipelineEvents((prev) => {
              const idx = prev.findIndex((e) => e.stage === msg.stage);
              if (idx >= 0) {
                const next = [...prev];
                next[idx] = {
                  ...next[idx],
                  status: msg.status || next[idx].status,
                  message: msg.message || next[idx].message,
                };
                return next;
              }
              return [
                ...prev,
                {
                  stage: msg.stage,
                  status: msg.status || "running",
                  icon: STAGE_ICON[msg.stage] || "default",
                  label: stageLabel(msg.stage),
                  message: msg.message || stageLabel(msg.stage),
                  substepLog: [],
                },
              ];
            });
          },
          onComplete: (res) => finish(res),
          onError: async () => {
            try { finish(await reviewCode(code, language, intent, requestText)); }
            catch (err) {
              const m = err instanceof Error ? err.message : "Analysis failed.";
              setError(m);
              setLoading(false);
              toast.error("Analysis failed", m);
            }
          },
          onClose: () => {
            setLoading((prev) => {
              if (prev) {
                setError("Connection closed before results arrived. Please try again.");
                toast.error("Connection lost", "The review stream closed unexpectedly.");
              }
              return false;
            });
          },
        },
        intent,
        requestText
      );
      return;
    }

    try { finish(await reviewCode(code, language, intent, requestText)); }
    catch (e) {
      const m = e instanceof Error ? e.message : "Analysis failed.";
      setError(m);
      setLoading(false);
      toast.error("Analysis failed", m);
    }
  };

  const restore = async (sessionId) => {
    setRestoringId(sessionId);
    try {
      const res = await fetchReviewRestore(sessionId);
      setResult(res);
      if (res.source_code) setCode(res.source_code);
      if (res.language)    setLanguage(res.language);
      if (res.intent)      setIntent(res.intent);
      setCurrentSessionId(sessionId);
      // Load stored workspace name
      const stored = getWorkspaceName(sessionId);
      setWorkspaceName(stored || res.workspace_name || "Untitled Workspace");
      setView("workspace");
      setError(null);
      toast.success("Review restored", "Loaded a previous analysis.");
    } catch (e) {
      toast.error("Could not restore review", e.message || "");
    } finally {
      setRestoringId(null);
    }
  };

  const handleNameSave = async () => {
    setEditingName(false);
    const trimmed = workspaceName.trim() || "Untitled Workspace";
    setWorkspaceName(trimmed);
    if (currentSessionId) {
      storeWorkspaceName(currentSessionId, trimmed);
      try {
        await updateWorkspaceName(currentSessionId, trimmed);
      } catch {}
    }
  };

  const applyRefactor = (modified) => {
    if (!modified) return;
    setCode(modified);
    setView("workspace");
    toast.success("Refactor applied", "The editor now holds the refactored code.");
  };

  // Rename workspace from history
  const handleRenameFromHistory = async (sessionId, newName) => {
    storeWorkspaceName(sessionId, newName);
    try {
      await updateWorkspaceName(sessionId, newName);
    } catch {}
    setHistory((prev) =>
      prev.map((r) =>
        r.session_id === sessionId ? { ...r, workspace_name: newName } : r
      )
    );
  };

  useKeyboardShortcuts(
    {
      "mod+enter": () => { if (view === "workspace") analyze(); },
      "Escape": () => { if (editingName) handleNameSave(); },
    },
    [view, code, language, intent, requestText, streaming, loading, editingName]
  );

  if (!gateOpen) {
    return (
      <Login
        onAuthenticated={() => {
          setAuthed(true);
          setForceLogin(false);
        }}
      />
    );
  }

  const meta = VIEW_META[view] || VIEW_META.workspace;

  return (
    <div className="app">
      <Sidebar
        view={view}
        onNavigate={setView}
        onHistory={() => { setView("history"); loadHistory(); }}
        onSignOut={() => {
          logout();
          setAuthed(false);
          setUsername("");
          setForceLogin(true);
          toast.info("Signed out", "You have been signed out.");
        }}
        onNewWorkspace={newWorkspace}
        signedIn={authed || Boolean(getToken())}
        online={online}
        username={username}
      />

      <div className="app-body">
        {/* Top header */}
        <header className="header">
          <div className="topbar-title">
            <h1>{meta.title}</h1>
            <p>{meta.sub}</p>
          </div>
          <div className="header-actions">
            {result && (
              <span className="header-chip mono">
                {result.session_id?.slice(0, 8)}
              </span>
            )}
            <span className="header-chip">
              <span className={`dot ${online === null ? "" : online ? "online" : "offline"}`} />
              {online === null ? "connecting" : online ? "online" : "offline"}
            </span>
          </div>
        </header>

        {/* View routing */}
        {view === "agents"  && <AgentsPage />}
        {view === "history" && (
          <HistoryPage
            reviews={history}
            loading={historyLoading}
            busyId={restoringId}
            onRestore={restore}
            onRename={handleRenameFromHistory}
          />
        )}

        {view === "workspace" && (
          <div className="main">
            {/* Editor panel */}
            <section className="panel">
              <div className="panel-head">
                {/* Editable workspace name */}
                <div className="workspace-name-wrap">
                  {editingName ? (
                    <input
                      ref={nameInputRef}
                      className="workspace-name-input"
                      value={workspaceName}
                      onChange={(e) => setWorkspaceName(e.target.value)}
                      onBlur={handleNameSave}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") handleNameSave();
                        if (e.key === "Escape") { setEditingName(false); }
                      }}
                      maxLength={60}
                    />
                  ) : (
                    <button
                      className="workspace-name-btn"
                      onClick={() => {
                        setEditingName(true);
                        setTimeout(() => nameInputRef.current?.select(), 20);
                      }}
                      title="Click to rename this workspace"
                    >
                      <span>{workspaceName}</span>
                      <PencilIcon size={12} />
                    </button>
                  )}
                </div>

                <div className="editor-toolbar">
                  <select
                    className="toolbar-select"
                    value={language}
                    onChange={(e) => setLanguage(e.target.value)}
                    aria-label="Language"
                  >
                    {LANGUAGES.map((l) => (
                      <option key={l.id} value={l.id}>{l.label}</option>
                    ))}
                  </select>

                  <select
                    className="toolbar-select"
                    value={intent}
                    onChange={(e) => setIntent(e.target.value)}
                    title="Analysis intent"
                    aria-label="Analysis intent"
                  >
                    {INTENTS.map((i) => (
                      <option key={i.id} value={i.id}>{i.label}</option>
                    ))}
                  </select>

                  <label className="stream-toggle" title="Stream agent progress live">
                    <input
                      type="checkbox"
                      checked={streaming}
                      onChange={(e) => setStreaming(e.target.checked)}
                    />
                    Live
                  </label>

                  {loading ? (
                    <button
                      className="btn btn-danger"
                      onClick={stopAnalysis}
                      title="Stop analysis"
                    >
                      <StopIcon size={12} /> Stop
                    </button>
                  ) : (
                    <button
                      className="btn btn-primary"
                      onClick={analyze}
                      disabled={!code.trim()}
                    >
                      <PlayIcon size={12} /> Run Review <span className="kbd">⌘↵</span>
                    </button>
                  )}
                </div>
              </div>

              {intent === "auto" && (
                <div className="auto-intent-row">
                  <input
                    className="auto-intent-input"
                    value={requestText}
                    placeholder="Optional: describe what you want (e.g. 'find security bugs', 'write tests')…"
                    onChange={(e) => setRequestText(e.target.value)}
                  />
                </div>
              )}

              <div className="editor-wrap">
                <Editor
                  height="100%"
                  language={language}
                  theme="vs-dark"
                  value={code}
                  onChange={(v) => setCode(v ?? "")}
                  options={{
                    fontSize: 13,
                    fontFamily: "'JetBrains Mono', 'Cascadia Code', monospace",
                    minimap: { enabled: false },
                    scrollBeyondLastLine: false,
                    automaticLayout: true,
                    padding: { top: 14, bottom: 14 },
                    lineNumbersMinChars: 3,
                    renderLineHighlight: "line",
                    cursorBlinking: "smooth",
                    smoothScrolling: true,
                    overviewRulerLanes: 0,
                    hideCursorInOverviewRuler: true,
                    glyphMargin: false,
                    folding: true,
                    scrollbar: { verticalScrollbarSize: 4 },
                  }}
                />
              </div>
            </section>

            {/* Results panel */}
            <section className="panel">
              <div className="panel-head">
                <h2>Analysis Report</h2>
                {loading && (
                  <span style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: "var(--accent)" }}>
                    <span className="spinner" style={{ borderTopColor: "var(--accent)", borderColor: "var(--accent-muted)", width: 10, height: 10 }} />
                    Running pipeline…
                  </span>
                )}
              </div>

              {error && (
                <div style={{ padding: 14 }}>
                  <div className="error-banner">{error}</div>
                </div>
              )}

              {loading && streaming && (
                <ActivityFeed
                  events={pipelineEvents}
                  substeps={substeps}
                  running={loading}
                  intent={detectedIntent || (intent === "auto" ? "full_review" : intent)}
                  language={language}
                />
              )}

              {!error && !result && !loading && (
                <div className="placeholder">
                  <svg width="60" height="60" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M9 6 4 12l5 6M15 6l5 6-5 6M13 4l-2 16" />
                  </svg>
                  <div>
                    Submit code to run the multi-agent review pipeline.
                    <br />
                    Structure → Metrics → Security → Risk → Refactor → Docs → Tests.
                  </div>
                </div>
              )}

              {!error && result && (
                <ResultsPanel result={result} onApplyRefactor={applyRefactor} />
              )}
            </section>
          </div>
        )}
      </div>
    </div>
  );
}
