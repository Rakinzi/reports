from __future__ import annotations

import logging
import queue
import weakref
from collections import deque
from pathlib import Path

from .runtime import get_app_data_dir

LOGGER_NAME = "reports"

# In-memory ring buffer — keeps the last 500 log lines for /logs
_log_buffer: deque[str] = deque(maxlen=500)
# Live SSE subscribers — each is a queue.Queue that receives new lines
_subscribers: list[weakref.ref[queue.Queue[str]]] = []


def _add_subscriber(q: "queue.Queue[str]") -> None:
    _subscribers.append(weakref.ref(q))


def _broadcast(line: str) -> None:
    _log_buffer.append(line)
    dead = []
    for ref in _subscribers:
        q = ref()
        if q is None:
            dead.append(ref)
        else:
            try:
                q.put_nowait(line)
            except queue.Full:
                pass
    for ref in dead:
        _subscribers.remove(ref)


class _BroadcastHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            _broadcast(self.format(record))
        except Exception:
            pass


def get_log_path() -> Path:
    return get_app_data_dir() / "app.log"


def configure_logging() -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    if logger.handlers:
        return logger

    log_path = get_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    broadcast_handler = _BroadcastHandler()
    broadcast_handler.setFormatter(formatter)
    logger.addHandler(broadcast_handler)

    logger.propagate = False
    return logger


def read_recent_logs(limit: int = 200) -> list[str]:
    # Prefer in-memory buffer (always up to date); fall back to file
    if _log_buffer:
        lines = list(_log_buffer)
        return lines[-limit:]
    log_path = get_log_path()
    if not log_path.exists():
        return []
    with log_path.open("r", encoding="utf-8", errors="replace") as handle:
        return list(deque(handle, maxlen=limit))


def stream_logs():
    """Generator that yields new log lines as SSE events. Registers as a live subscriber."""
    import time
    q: queue.Queue[str] = queue.Queue(maxsize=200)
    _add_subscriber(q)
    # Send recent history first
    for line in list(_log_buffer):
        yield f"data: {line.rstrip()}\n\n"
    # Then stream new lines as they arrive
    while True:
        try:
            line = q.get(timeout=15)
            yield f"data: {line.rstrip()}\n\n"
        except queue.Empty:
            yield ": keep-alive\n\n"
