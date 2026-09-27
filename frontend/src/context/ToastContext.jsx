import { createContext, useCallback, useContext, useRef, useState } from "react";
import Toast from "../components/Toast.jsx";

const ToastContext = createContext(null);

let _id = 0;

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const timers = useRef({});

  const dismiss = useCallback((id) => {
    setToasts((prev) =>
      prev.map((t) => (t.id === id ? { ...t, leaving: true } : t))
    );
    // Remove after the leave animation completes.
    window.setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 220);
    if (timers.current[id]) {
      window.clearTimeout(timers.current[id]);
      delete timers.current[id];
    }
  }, []);

  const push = useCallback(
    (type, title, message = "", duration = 4200) => {
      const id = ++_id;
      setToasts((prev) => [...prev, { id, type, title, message }]);
      if (duration > 0) {
        timers.current[id] = window.setTimeout(() => dismiss(id), duration);
      }
      return id;
    },
    [dismiss]
  );

  const api = {
    push,
    dismiss,
    success: (title, message, d) => push("success", title, message, d),
    error: (title, message, d) => push("error", title, message, d),
    warning: (title, message, d) => push("warning", title, message, d),
    info: (title, message, d) => push("info", title, message, d),
  };

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="toast-host" aria-live="polite" aria-atomic="false">
        {toasts.map((t) => (
          <Toast key={t.id} toast={t} onClose={() => dismiss(t.id)} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    // Fail-safe no-op so components never crash if used outside a provider.
    return {
      push: () => {},
      dismiss: () => {},
      success: () => {},
      error: () => {},
      warning: () => {},
      info: () => {},
    };
  }
  return ctx;
}
