function Icon({ name, size = 18 }) {
  const p = {
    width: size, height: size, viewBox: "0 0 24 24",
    fill: "none", stroke: "currentColor",
    strokeWidth: 1.8, strokeLinecap: "round", strokeLinejoin: "round",
  };
  switch (name) {
    case "workspace":
      return (
        <svg {...p}>
          <rect x="3" y="3" width="8" height="8" rx="1.5" />
          <rect x="13" y="3" width="8" height="8" rx="1.5" />
          <rect x="3" y="13" width="8" height="8" rx="1.5" />
          <rect x="13" y="13" width="8" height="8" rx="1.5" />
        </svg>
      );
    case "new":
      return (
        <svg {...p}>
          <path d="M12 5v14M5 12h14" />
        </svg>
      );
    case "agents":
      return (
        <svg {...p}>
          <circle cx="12" cy="12" r="3" />
          <path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.93 4.93l2.12 2.12M16.95 16.95l2.12 2.12M4.93 19.07l2.12-2.12M16.95 7.05l2.12-2.12" />
        </svg>
      );
    case "history":
      return (
        <svg {...p}>
          <circle cx="12" cy="12" r="9" />
          <path d="M12 7v5l3.5 2" />
        </svg>
      );
    case "signout":
      return (
        <svg {...p}>
          <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
          <path d="M16 17l5-5-5-5M21 12H9" />
        </svg>
      );
    default:
      return (
        <svg {...p}><circle cx="12" cy="12" r="9" /></svg>
      );
  }
}

export default function Sidebar({
  view,
  onNavigate,
  onHistory,
  onSignOut,
  onNewWorkspace,
  signedIn,
  online,
  username,
}) {
  const initial = (username || "G").trim().charAt(0).toUpperCase();

  const statusClass =
    online === null ? "" : online ? "online" : "offline";
  const statusTip =
    online === null ? "Connecting…" : online ? "Backend online" : "Backend offline";

  return (
    <aside className="sidebar">
      {/* Logo */}
      <div className="sidebar-brand">
        <img className="brand-logo" src="/favicon.svg" alt="ARCAS" />
      </div>

      {/* Navigation */}
      <nav className="sidebar-nav">
        {/* New Workspace */}
        <button
          className="sidebar-link sidebar-link-new"
          onClick={onNewWorkspace}
          data-tooltip="New Workspace"
          aria-label="New Workspace"
          title="New Workspace"
        >
          <Icon name="new" />
        </button>

        <div className="sidebar-divider" />

        <button
          className={`sidebar-link ${view === "workspace" ? "active" : ""}`}
          onClick={() => onNavigate("workspace")}
          data-tooltip="Workspace"
          aria-label="Workspace"
        >
          <Icon name="workspace" />
        </button>

        <button
          className={`sidebar-link ${view === "agents" ? "active" : ""}`}
          onClick={() => onNavigate("agents")}
          data-tooltip="Agent Pipeline"
          aria-label="Agent Pipeline"
        >
          <Icon name="agents" />
        </button>

        <button
          className={`sidebar-link ${view === "history" ? "active" : ""}`}
          onClick={onHistory}
          data-tooltip="Review History"
          aria-label="Review History"
        >
          <Icon name="history" />
        </button>
      </nav>

      {/* Footer */}
      <div className="sidebar-foot">
        {/* Status dot with tooltip */}
        <button
          className="sidebar-link"
          style={{ pointerEvents: "none", cursor: "default" }}
          data-tooltip={statusTip}
          aria-label={statusTip}
        >
          <span className={`sidebar-status-dot ${statusClass}`} />
        </button>

        {/* User avatar - click to sign out */}
        {signedIn && (
          <button
            className="sidebar-link"
            onClick={onSignOut}
            data-tooltip={`Sign out${username ? ` (${username})` : ""}`}
            aria-label="Sign out"
          >
            <span className="sidebar-avatar">{initial}</span>
          </button>
        )}

        {/* Sign-out icon when user chip not shown */}
        {!signedIn && (
          <button
            className="sidebar-link"
            onClick={onSignOut}
            data-tooltip="Sign out"
            aria-label="Sign out"
          >
            <Icon name="signout" size={16} />
          </button>
        )}
      </div>
    </aside>
  );
}
