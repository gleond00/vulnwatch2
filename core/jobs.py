from __future__ import annotations
import threading, queue, time
from typing import Set, List
from django import db
from django.conf import settings

_queue: "queue.Queue[int]" = queue.Queue()
_seen: Set[int] = set()
_started = False

# Configurables por settings/env
BATCH_SIZE = int(getattr(settings, "JOBS_BATCH_SIZE", 32))
BATCH_MAX_WAIT = float(getattr(settings, "JOBS_MAX_WAIT_MS", 150)) / 1000.0  # ms -> s
POST_BATCH_SLEEP = float(getattr(settings, "JOBS_POST_BATCH_SLEEP_MS", 5)) / 1000.0  # cede CPU

def start_jobs_worker():
    global _started
    if _started:
        return
    _started = True
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    print(f"[jobs] worker iniciado ✅ (batch={BATCH_SIZE}, wait={int(BATCH_MAX_WAIT*1000)}ms)", flush=True)

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
            from .services import classify_issue_batch
            classify_issue_batch(batch)
        except Exception as e:
            print(f"[jobs] classify error: {e}", flush=True)
        finally:
            for iid in set([issue_id, *batch[1:]]):
                _seen.discard(iid)
                _queue.task_done()
            if POST_BATCH_SLEEP > 0:
                time.sleep(POST_BATCH_SLEEP)

def enqueue_issue(issue_id: int):
    if issue_id in _seen:
        return
    _seen.add(issue_id)
    _queue.put(issue_id)
