// ARCAS API client (JavaScript).

const API_BASE = "/api/v1";

const TOKEN_KEY = "arcas_token";

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY) || "";
  } catch {
    return "";
  }
}

export function setToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    // ignore storage errors
  }
}

function authHeaders(extra = {}) {
  const token = getToken();
  return token ? { ...extra, Authorization: `Bearer ${token}` } : extra;
}

async function handle(response) {
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") {
        detail = body.detail;
      } else if (body.detail && body.detail.message) {
        detail = body.detail.message;
        if (Array.isArray(body.detail.violations)) {
          detail += ": " + body.detail.violations.join(" ");
        }
      }
    } catch {
      // ignore body parse errors
    }
    const err = new Error(detail);
    err.status = response.status;
    throw err;
  }
  return response.json();
}

// Authentication

export async function login(username, password) {
  const body = new URLSearchParams();
  body.set("username", username);
  body.set("password", password);
  const response = await fetch(`${API_BASE}/auth/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  const data = await handle(response);
  if (data.access_token) setToken(data.access_token);
  return data;
}

export async function register(username, password) {
  const response = await fetch(`${API_BASE}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  return handle(response);
}

export async function currentUser() {
  const response = await fetch(`${API_BASE}/auth/me`, {
    headers: authHeaders(),
  });
  return handle(response);
}

export function logout() {
  setToken("");
}

// Review pipeline

export async function reviewCode(
  code,
  language,
  intent = "full_review",
  requestText = ""
) {
  const body = { code, language, intent };
  if (requestText) body.request_text = requestText;
  const response = await fetch(`${API_BASE}/review`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  });
  return handle(response);
}

export async function fetchReviews() {
  const response = await fetch(`${API_BASE}/reviews`, {
    headers: authHeaders(),
  });
  return handle(response);
}

export async function fetchReport(sessionId) {
  const response = await fetch(`${API_BASE}/report/${sessionId}`, {
    headers: authHeaders(),
  });
  return handle(response);
}

export async function fetchReviewRestore(sessionId) {
  const response = await fetch(
    `${API_BASE}/review/${sessionId}/restore`,
    { headers: authHeaders() }
  );
  return handle(response);
}

// Submit thumbs up/down feedback on a review or a specific agent.
export async function submitFeedback(sessionId, rating, comment = "", agent = "") {
  const body = { rating };
  if (comment) body.comment = comment;
  if (agent) body.agent = agent;
  const response = await fetch(
    `${API_BASE}/review/${sessionId}/feedback`,
    {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(body),
    }
  );
  return handle(response);
}

export async function fetchHealth() {
  const response = await fetch(`/health`);
  return handle(response);
}

// Workspace management

export async function updateWorkspaceName(sessionId, name) {
  const response = await fetch(`${API_BASE}/review/${sessionId}/name`, {
    method: "PATCH",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ name }),
  });
  return handle(response);
}


export function streamReview(code, language, handlers = {}, intent = "full_review", requestText = "") {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  const token = getToken();
  const qs = token ? `?token=${encodeURIComponent(token)}` : "";
  const url = `${proto}://${window.location.host}${API_BASE}/review/stream${qs}`;

  let socket;
  try {
    socket = new WebSocket(url);
  } catch (e) {
    handlers.onError && handlers.onError(e);
    return { close() {} };
  }

  socket.onopen = () => {
    const payload = { code, language, intent };
    if (requestText) payload.request_text = requestText;
    socket.send(JSON.stringify(payload));
    handlers.onOpen && handlers.onOpen();
  };

  socket.onmessage = (event) => {
    let msg;
    try {
      msg = JSON.parse(event.data);
    } catch {
      return;
    }
    if (msg.stage === "complete") {
      handlers.onComplete && handlers.onComplete(msg.data);
      socket.close();
    } else if (msg.stage === "error") {
      handlers.onError && handlers.onError(new Error(msg.message || "error"));
      socket.close();
    } else {
      handlers.onStage && handlers.onStage(msg);
    }
  };

  socket.onerror = (e) => handlers.onError && handlers.onError(e);
  socket.onclose = () => handlers.onClose && handlers.onClose();

  return {
    close() {
      try {
        socket.close();
      } catch {
        // ignore
      }
    },
  };
}
