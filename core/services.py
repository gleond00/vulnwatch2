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
MAX_ISSUES = int(getattr(settings, "MAX_ISSUES_PER_REPO", 0))        # 0 = sin ventana
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

# ---------- seed ----------
def seed_repository(repo: Repository) -> int:
    """
    Seed inicial: trae issues ABIERTOs ordenados por updated desc.
    Respeta MAX_ISSUES_PER_REPO si está configurado (>0).
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

    # si hay ventana, aseguramos que solo queden los top N por updated_at_github
    if MAX_ISSUES > 0:
        _prune_window(repo)

    return created_total

# ---------- sync ----------
def sync_repository(repo: Repository) -> Dict[str, Any]:
    """
    Si MAX_ISSUES_PER_REPO > 0 => modo ventana:
      - Trae SOLO issues (state=all) actualizados desde last_synced.
      - Upsert de abiertos y borrado inmediato de los que llegan cerrados.
      - Poda a los N más recientes por updated_at_github.
    Si MAX_ISSUES_PER_REPO == 0 => modo completo (open set + delete cerrados).
    """
    if MAX_ISSUES > 0:
        return _sync_window(repo)
    else:
        return _sync_full(repo)

def _sync_full(repo: Repository) -> Dict[str, Any]:
    open_issues = fetch_all_open_issues(repo.full_name)
    open_numbers = {it["number"] for it in open_issues}
    deleted_closed = 0

    def _tx_delete():
        nonlocal deleted_closed
        with suppress_issue_signals():
            with transaction.atomic():
                existing_numbers = set(
                    Issue.objects.filter(repo=repo).values_list("number", flat=True)
                )
                closed_numbers = existing_numbers - open_numbers
                if closed_numbers:
                    deleted_closed = Issue.objects.filter(
                        repo=repo, number__in=closed_numbers
                    ).delete()[0]
    _with_retry(_tx_delete)

    from .jobs import enqueue_issue
    for chunk in _iter_chunks(open_issues, CHUNK_SIZE):
        chunk_ids: List[int] = []

        def _tx_upsert():
            with suppress_issue_signals():
                with transaction.atomic():
                    for it in chunk:
                        issue, _ = Issue.objects.update_or_create(
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

        _with_retry(_tx_upsert)
        for iid in chunk_ids:
            enqueue_issue(iid)

    repo.last_synced = timezone.now()
    _with_retry(repo.save, update_fields=["last_synced"])
    return {"open_count": len(open_numbers), "deleted_closed": deleted_closed}

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

def _sync_window(repo: Repository) -> Dict[str, Any]:
    """
    Incremental por 'updated_since' y poda a N más recientes.
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

    if MAX_ISSUES > 0:
        _prune_window(repo)

    from .jobs import enqueue_issue
    for iid in touched_ids:
        enqueue_issue(iid)

    repo.last_synced = timezone.now()
    _with_retry(repo.save, update_fields=["last_synced"])

    return {"updated": len(touched_ids), "deleted_closed": deleted_closed}

def _prune_window(repo: Repository):
    """
    Mantiene solo los MAX_ISSUES más recientes (updated_at_github desc).
    """
    if MAX_ISSUES <= 0:
        return

    qs = (
        Issue.objects.filter(repo=repo)
        .order_by("-updated_at_github", "-id")
        .values_list("id", flat=True)
    )
    ids = list(qs)
    if len(ids) <= MAX_ISSUES:
        return
    to_delete = ids[MAX_ISSUES:]

    def _tx_del():
        with suppress_issue_signals():
            with transaction.atomic():
                Issue.objects.filter(id__in=to_delete).delete()

    _with_retry(_tx_del)

# ---------- clasificación (batched + bulk upsert) ----------
def classify_issue_batch(issue_ids: Iterable[int]) -> int:
    """
    Clasifica issues por lote con inferencia batched y bulk upsert.
    Devuelve nº de issues (con texto) procesados.
    """
    ids = list({int(i) for i in issue_ids if i})
    if not ids:
        return 0

    qs = (
        Issue.objects.select_related("repo")
        .prefetch_related("comments")
        .filter(id__in=ids)
        .order_by("id")
    )
    issues_all = list(qs)
    if not issues_all:
        return 0

    # Montamos textos y filtramos vacíos
    issues: List[Issue] = []
    texts: List[str] = []
    for it in issues_all:
        parts = [p for p in [(it.title or ""), (it.body or "")] if p]
        parts += [c.body for c in it.comments.all().order_by("id") if c.body]
        text = "\n\n".join(parts).strip()
        if text:
            issues.append(it)
            texts.append(text)
    if not issues:
        return 0

    clf = get_classifier()

    # Inferencia por lotes
    preds: List[Dict[str, Any]] = []
    for i in range(0, len(texts), INFER_BATCH_SIZE):
        preds.extend(clf.predict_batch(texts[i : i + INFER_BATCH_SIZE]))

    # Cache de modelos activos por repo
    lm_cache: Dict[int, ModelLanguage] = {}

    def _lm(repo: Repository) -> ModelLanguage:
        rid = repo.id
        if rid not in lm_cache:
            lm_cache[rid] = _ensure_repo_model(repo)
        return lm_cache[rid]

    now = timezone.now()
    existing = {p.issue_id: p for p in IssuePrediction.objects.filter(issue__in=issues)}
    to_create: List[IssuePrediction] = []
    to_update: List[IssuePrediction] = []

    for it, out in zip(issues, preds):
        lm = _lm(it.repo)

        bin_is_vuln = bool(out.get("bin_is_vuln")) if out.get("bin_is_vuln") is not None else False
        try:
            bin_score = float(out.get("bin_score")) if out.get("bin_score") is not None else 0.0
        except Exception:
            bin_score = 0.0

        if not bin_is_vuln:
            severity_label = None
            severity_probs = None
            types_pred: List[str] = []
            types_probs: Dict[str, float] = {}
        else:
            sev_raw = out.get("severity_pred")
            severity_label = int(sev_raw) if sev_raw is not None else None
            sp = out.get("severity_probs")
            severity_probs = (
                [None if v is None else float(v) for v in sp] if isinstance(sp, list) else None
            )
            types_pred = out.get("types_pred") or []
            types_probs = out.get("types_probs") or {}

        pred = existing.get(it.id)
        if pred is None:
            to_create.append(
                IssuePrediction(
                    issue=it,
                    model=lm,
                    updated_at=now,
                    bin_is_vuln=bin_is_vuln,
                    bin_score=bin_score,
                    severity_label=severity_label,
                    severity_probs=severity_probs,
                    types_pred=types_pred,
                    types_probs=types_probs,
                )
            )
        else:
            if pred.model_id != lm.id:
                pred.model = lm
            pred.bin_is_vuln = bin_is_vuln
            pred.bin_score = bin_score
            pred.severity_label = severity_label
            pred.severity_probs = severity_probs
            pred.types_pred = types_pred
            pred.types_probs = types_probs
            pred.updated_at = now
            to_update.append(pred)

    def _tx_bulk():
        with transaction.atomic():
            if to_create:
                IssuePrediction.objects.bulk_create(to_create, batch_size=BULK_DB_BATCH)
            if to_update:
                IssuePrediction.objects.bulk_update(
                    to_update,
                    fields=[
                        "model",
                        "bin_is_vuln",
                        "bin_score",
                        "severity_label",
                        "severity_probs",
                        "types_pred",
                        "types_probs",
                        "updated_at",
                    ],
                    batch_size=BULK_DB_BATCH,
                )

    _with_retry(_tx_bulk)
    return len(issues)

# API compat
def schedule_classify_issue(issue_id: int) -> dict:
    n = classify_issue_batch([issue_id])
    return {"ok": True, "count": n}

# ---------- FALTABA: sync_all_repos (usado por el scheduler en apps.py) ----------
def sync_all_repos() -> List[Dict[str, Any]]:
    """
    Ejecuta sync_repository() para todos los repos externos (is_own=False).
    Respeta el modo ventana si MAX_ISSUES_PER_REPO > 0.
    """
    out: List[Dict[str, Any]] = []
    for repo in Repository.objects.filter(is_own=False):
        try:
            res = sync_repository(repo)
            out.append({"repo": repo.full_name, **res})
        except Exception as e:
            out.append({"repo": repo.full_name, "ok": False, "error": str(e)})
    return out
