from __future__ import annotations
import threading, queue, time
from typing import Set, List
from django import db

_queue: "queue.Queue[int]" = queue.Queue()
_seen: Set[int] = set()
_started = False

BATCH_SIZE = 8
BATCH_MAX_WAIT = 0.15  # agrupa IDs unos ms para inferir en lote

def start_jobs_worker():
    global _started
    if _started:
        return
    _started = True
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    print("[jobs] worker iniciado ✅", flush=True)

def _drain_batch(first_id: int) -> List[int]:
    ids = [first_id]
    t0 = time.time()
    while len(ids) < BATCH_SIZE and (time.time() - t0) < BATCH_MAX_WAIT:
        try:
            nxt = _queue.get(timeout=0.02)
            ids.append(nxt)
        except queue.Empty:
            pass
    return ids

def _run():
    while True:
        issue_id = _queue.get()
        try:
            db.close_old_connections()
            batch = _drain_batch(issue_id)
            # import perezoso: evita ciclo jobs -> services a import-time
            from .services import classify_issue_batch
            classify_issue_batch(batch)
        except Exception as e:
            print(f"[jobs] classify error: {e}", flush=True)
        finally:
            for iid in set([issue_id, *batch[1:]]):
                _seen.discard(iid)
                _queue.task_done()

def enqueue_issue(issue_id: int):
    if issue_id in _seen:
        return
    _seen.add(issue_id)
    _queue.put(issue_id)
