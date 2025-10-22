from __future__ import annotations
from typing import Iterable, List, Dict, Any
import time

from django.db import transaction, OperationalError
from django.utils import timezone
from django.conf import settings

from .models import Repository, Issue, Comment, ModelLanguage, IssuePrediction
from .ml import get_classifier
from .githubsync import (
    fetch_all_open_issues,
    fetch_issue_comments,
    fetch_issues_since,
)
from .signal_guard import suppress_issue_signals

# ---------- util: reintentos anti "database is locked" ----------
def _with_retry(fn, *args, **kwargs):
    delay = 0.15
    for _ in range(6):
        try:
            return fn(*args, **kwargs)
        except OperationalError as e:
            if "locked" in str(e).lower():
                time.sleep(delay)
                delay = min(delay * 2, 1.0)
                continue
            raise

def _iter_chunks(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i:i+size]

# ---------- settings tunables ----------
CHUNK_SIZE = int(getattr(settings, "SEED_CHUNK_SIZE", 40))
INFER_BATCH_SIZE = int(getattr(settings, "INFER_BATCH_SIZE", 16))
BULK_DB_BATCH = int(getattr(settings, "BULK_DB_BATCH", 256))

# ---------- modelo por repo ----------
def _ensure_repo_model(repo: Repository) -> ModelLanguage:
    if getattr(repo, "model_id", None):
        ml = repo.model
        if not ml.active:
            ml.active = True
            _with_retry(ml.save, update_fields=["active"])
        return ml
    clf = get_classifier()
    ml = ModelLanguage.objects.create(
        name=getattr(clf, "model_name", "roberta-large"),
        device=getattr(clf, "device", "cpu"),
        active=True,
    )
    return ml

# ---------- seed (SOLO limitado) ----------
def seed_repository(repo: Repository) -> int:
    """
    Seed inicial: trae issues ABIERTOS por 'updated desc' limitado por MAX_SEED_ISSUES.
    No hay poda posterior: a partir de aquí el conjunto podrá crecer.
    """
    open_issues = fetch_all_open_issues(repo.full_name)
    created_total = 0

    from .jobs import enqueue_issue  # import perezoso

    for chunk in _iter_chunks(open_issues, CHUNK_SIZE):
        chunk_ids: List[int] = []

        def _tx():
            nonlocal created_total
            with suppress_issue_signals():
                with transaction.atomic():
                    for it in chunk:
                        issue, created = Issue.objects.update_or_create(
                            repo=repo,
                            number=it["number"],
                            defaults={
                                "title": it.get("title") or "",
                                "body": it.get("body") or "",
                                "user": it.get("user") or "",
                                "created_at_github": it.get("created_at") or None,
                                "updated_at_github": it.get("updated_at") or None,
                            },
                        )
                        if created:
                            created_total += 1

                        if (it.get("comments") or 0) > 0:
                            comments = fetch_issue_comments(repo.full_name, issue.number)
                            for c in comments:
                                Comment.objects.update_or_create(
                                    issue=issue,
                                    external_id=c.get("id"),
                                    defaults={
                                        "body": c.get("body") or "",
                                        "user": c.get("user") or "",
                                        "created_at_github": c.get("created_at") or None,
                                        "updated_at_github": c.get("updated_at") or None,
                                    },
                                )
                        chunk_ids.append(issue.id)

        _with_retry(_tx)
        for iid in chunk_ids:
            enqueue_issue(iid)

    # marca sync al final
    repo.last_synced = timezone.now()
    _with_retry(repo.save, update_fields=["last_synced"])

    return created_total

# ---------- sync (INCREMENTAL sin límite; borra cerrados; NO poda) ----------
def sync_repository(repo: Repository) -> Dict[str, Any]:
    """
    Incremental:
      - Trae issues (state=all) actualizados desde last_synced.
      - Upsert de abiertos; si llega 'closed' => delete.
      - SIN poda: el conjunto puede crecer por encima del seed.
    """
    since_iso = _to_github_iso(repo.last_synced) or _to_github_iso(
        timezone.now() - timezone.timedelta(days=3650)
    )
    updates = fetch_issues_since(repo.full_name, since_iso)

    touched_ids: List[int] = []
    deleted_closed = 0

    def _tx_apply():
        nonlocal deleted_closed, touched_ids
        with suppress_issue_signals():
            with transaction.atomic():
                for it in updates:
                    num = it["number"]
                    state = (it.get("state") or "open").lower()
                    if state == "closed":
                        deleted, _ = Issue.objects.filter(repo=repo, number=num).delete()
                        if deleted:
                            deleted_closed += deleted
                        continue

                    issue, _ = Issue.objects.update_or_create(
                        repo=repo,
                        number=num,
                        defaults={
                            "title": it.get("title") or "",
                            "body": it.get("body") or "",
                            "user": it.get("user") or "",
                            "created_at_github": it.get("created_at") or None,
                            "updated_at_github": it.get("updated_at") or None,
                        },
                    )
                    if (it.get("comments") or 0) > 0:
                        comments = fetch_issue_comments(repo.full_name, issue.number)
                        for c in comments:
                            Comment.objects.update_or_create(
                                issue=issue,
                                external_id=c.get("id"),
                                defaults={
                                    "body": c.get("body") or "",
                                    "user": c.get("user") or "",
                                    "created_at_github": c.get("created_at") or None,
                                    "updated_at_github": c.get("updated_at") or None,
                                },
                            )
                    touched_ids.append(issue.id)

    _with_retry(_tx_apply)

    # cola de clasificación
    from .jobs import enqueue_issue
    for iid in touched_ids:
        enqueue_issue(iid)

    # marca sync al final
    repo.last_synced = timezone.now()
    _with_retry(repo.save, update_fields=["last_synced"])

    return {"updated": len(touched_ids), "deleted_closed": deleted_closed}

def _to_github_iso(dt) -> str | None:
    if not dt:
        return None
    try:
        import datetime
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return str(dt)

# ---------- clasificación (tu versión original, predict uno-a-uno, robusta) ----------
def classify_issue_batch(issue_ids: Iterable[int]) -> int:
    ids = list({int(i) for i in issue_ids if i})
    if not ids:
        return 0

    qs = (Issue.objects
          .select_related("repo")
          .prefetch_related("comments")
          .filter(id__in=ids)
          .order_by("id"))
    issues = list(qs)
    if not issues:
        return 0

    clf = get_classifier()
    updated = 0

    for it in issues:
        parts = [p for p in [(it.title or ""), (it.body or "")] if p]
        parts += [c.body for c in it.comments.all().order_by("id") if c.body]
        text = "\n\n".join(parts).strip()
        if not text:
            continue

        out = clf.predict(text)
        lm = _ensure_repo_model(it.repo)

        bin_is_vuln = bool(out.get("bin_is_vuln"))
        try:
            bin_score = float(out.get("bin_score")) if out.get("bin_score") is not None else 0.0
        except Exception:
            bin_score = 0.0

        sev_raw = out.get("severity_pred")
        try:
            severity_label = int(sev_raw) if sev_raw is not None else None
        except Exception:
            severity_label = None

        severity_probs = out.get("severity_probs")
        if isinstance(severity_probs, list):
            try:
                severity_probs = [None if v is None else float(v) for v in severity_probs]
            except Exception:
                severity_probs = None
        else:
            severity_probs = None

        types_pred = out.get("types_pred") or []
        types_probs = out.get("types_probs") or {}

        if not bin_is_vuln:
            severity_label = None
            severity_probs = None
            types_pred = []
            types_probs = {}

        def _upsert():
            pred, created = IssuePrediction.objects.get_or_create(
                issue=it,
                defaults={
                    "model": lm,
                    "bin_is_vuln": bin_is_vuln,
                    "bin_score": bin_score,
                    "severity_label": severity_label,
                    "severity_probs": severity_probs,
                    "types_pred": types_pred,
                    "types_probs": types_probs,
                    "updated_at": timezone.now(),
                },
            )
            if not created:
                if pred.model_id != lm.id:
                    pred.model = lm
                pred.bin_is_vuln = bin_is_vuln
                pred.bin_score = bin_score
                pred.severity_label = severity_label
                pred.severity_probs = severity_probs
                pred.types_pred = types_pred
                pred.types_probs = types_probs
                pred.updated_at = timezone.now()
                pred.save()

        _with_retry(_upsert)
        updated += 1

    return updated

def schedule_classify_issue(issue_id: int) -> dict:
    n = classify_issue_batch([issue_id])
    return {"ok": True, "count": n}

# ---------- usado por el scheduler ----------
def sync_all_repos() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for repo in Repository.objects.filter(is_own=False):
        try:
            res = sync_repository(repo)
            out.append({"repo": repo.full_name, **res})
        except Exception as e:
            out.append({"repo": repo.full_name, "ok": False, "error": str(e)})
    return out
