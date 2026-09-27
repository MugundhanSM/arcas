"""Thread-safe substep event collector for real-time agent sub-progress."""

import contextvars
import threading
from typing import Callable, List, Optional, Tuple

# ContextVar holding the current substep callback, or None.
_emitter_var: contextvars.ContextVar[Optional[Callable[[str, str], None]]] = (
    contextvars.ContextVar("substep_emitter", default=None)
)


class SubstepCollector:
    """Thread-safe collector for substep messages from worker threads."""

    __slots__ = ("_messages", "_lock")

    def __init__(self) -> None:
        self._messages: List[dict] = []
        self._lock = threading.Lock()

    def add(self, stage: str, message: str) -> None:
        """Called from any thread - fully thread-safe."""
        with self._lock:
            self._messages.append(
                {"stage": stage, "status": "substep", "message": message}
            )

    def drain(self) -> List[dict]:
        """Called from the event-loop thread - returns and clears all pending messages."""
        with self._lock:
            msgs = self._messages[:]
            self._messages.clear()
        return msgs


def emit_substep(stage: str, message: str) -> None:
    """Emit a substep event from any thread."""
    fn = _emitter_var.get()
    if fn is not None:
        try:
            fn(stage, message)
        except Exception:  # noqa: BLE001
            pass


def install_emitter() -> Tuple[contextvars.Token, SubstepCollector]:
    """Install a substep collector for the current async context."""
    collector = SubstepCollector()
    token = _emitter_var.set(collector.add)
    return token, collector


def install_queue_emitter(loop, queue) -> contextvars.Token:
    """Install a live substep emitter backed by an asyncio.Queue."""
    def _emit(stage: str, message: str) -> None:
        item = {"stage": stage, "status": "substep", "message": message}
        try:
            loop.call_soon_threadsafe(queue.put_nowait, item)
        except RuntimeError:
            # Loop already closed (client disconnected / shutdown) - drop it.
            pass

    return _emitter_var.set(_emit)


def uninstall_emitter(token: contextvars.Token) -> None:
    """Restore the previous emitter."""
    try:
        _emitter_var.reset(token)
    except ValueError:
        pass
