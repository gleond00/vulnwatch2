from __future__ import annotations
import threading
from contextlib import contextmanager

_local = threading.local()

def are_signals_suppressed() -> bool:
    return bool(getattr(_local, "suppress_issue_signals", False))

@contextmanager
def suppress_issue_signals():
    prev = are_signals_suppressed()
    _local.suppress_issue_signals = True
    try:
        yield
    finally:
        _local.suppress_issue_signals = prev
