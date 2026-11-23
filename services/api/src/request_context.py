"""Per-request context shared with services (correlates audit events with request logs)."""
from contextvars import ContextVar
from typing import Optional

request_id_var: ContextVar[Optional[str]] = ContextVar("medchain_request_id", default=None)


def current_request_id() -> Optional[str]:
    return request_id_var.get()
