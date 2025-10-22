# core/exporter.py
from __future__ import annotations
import csv
import json
import threading
import queue
from pathlib import Path
from typing import Dict, Any, Optional

from django.utils import timezone
from django.db import close_old_connections
from django.conf import settings


# -------- configuración / rutas --------
EXPORT_DIR = Path(getattr(settings, "EXPORT_DIR", str(Path.cwd() / "exports")))
EXPORT_DIR.mkdir(parents=True, exist_ok=True)
CSV_PATH = EXPORT_DIR / "issues_dataset.csv"

# -------- worker de exportación --------
_started = False
_q: "queue.Queue[Dict[str, Any]]" = queue.Queue()


def start_export_worker():
    """Arranca el hilo que escribe filas en CSV (idempotente)."""
    global _started
    if _started:
        return
    _started = True
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    print(f"[export] worker iniciado ✅ → {CSV_PATH}", flush=True)


def enqueue_export(issue_id: int, reason: str = "prediction") -> None:
    """Encola la exportación de un issue (por su ID)."""
    if not issue_id:
        return
    _q.put({"issue_id": int(issue_id), "reason": reason, "ts": timezone.now()})


def export_snapshot_all(to_path: Optional[str | Path] = None) -> str:
    """
    Exporta un snapshot COMPLETO de todas las predicciones actuales a un CSV NUEVO
    (no bloquea el worker incremental). Devuelve la ruta del fichero.
    """
    from core.models import IssuePrediction  # import perezoso
    to_path = Path(to_path) if to_path else (EXPORT_DIR / f"issues_dataset_snapshot_{timezone.now().strftime('%Y%m%d_%H%M%S')}.csv")
    rows = []
    for pred in (IssuePrediction.objects
                 .select_related("issue", "issue__repo", "model")
                 .all()
                 .order_by("issue_id")):
        row = _build_row_from_prediction(pred)
        rows.append(row)

    _write_rows(to_path, rows, ensure_header=True)
    return str(to_path)


# -------- internals --------
def _run():
    """Bucle del worker: consume jobs y escribe filas."""
    while True:
        job = _q.get()
        try:
            close_old_connections()
            issue_id = int(job.get("issue_id") or 0)
            if issue_id:
                row = _build_row_from_issue(issue_id)
                if row:
                    # Escritura incremental al CSV principal
                    _write_rows(CSV_PATH, [row], ensure_header=True)
        except Exception as e:
            print(f"[export] error: {e}", flush=True)
        finally:
            _q.task_done()


def _build_row_from_issue(issue_id: int) -> Optional[Dict[str, Any]]:
    """Carga Issue + Prediction y construye una fila plana. Devuelve None si no hay predicción aún."""
    from core.models import Issue, IssuePrediction  # import perezoso

    issue = (Issue.objects
             .select_related("repo")
             .prefetch_related("comments")
             .filter(id=issue_id)
             .first())
    if not issue:
        return None

    pred = IssuePrediction.objects.filter(issue_id=issue_id).select_related("model").first()
    if not pred:
        # Si aún no hay predicción, no exportamos (criterio: dataset de predicciones)
        return None

    return _build_row(issue, pred)


def _build_row_from_prediction(pred) -> Dict[str, Any]:
    """Construye fila a partir de un IssuePrediction ya cargado con select_related."""
    issue = getattr(pred, "issue", None)
    if issue is None:
        from core.models import Issue
        issue = Issue.objects.select_related("repo").prefetch_related("comments").get(id=pred.issue_id)
    return _build_row(issue, pred)


def _build_row(issue, pred) -> Dict[str, Any]:
    """Crea el dict plano para CSV usando issue + prediction."""
    repo = issue.repo
    model = pred.model

    title = issue.title or ""
    body = issue.body or ""
    comments_count = getattr(issue, "comments", None)
    if comments_count is not None and hasattr(comments_count, "all"):
        comments_count = issue.comments.count()
    else:
        comments_count = 0

    # Campos JSON compactos
    sev_probs_json = json.dumps(pred.severity_probs or [], ensure_ascii=False, separators=(",", ":"))
    types_pred_json = json.dumps(pred.types_pred or [], ensure_ascii=False, separators=(",", ":"))
    types_probs_json = json.dumps(pred.types_probs or {}, ensure_ascii=False, separators=(",", ":"))

    row = {
        "exported_at": timezone.now().isoformat(),
        "repo_full_name": repo.full_name,
        "repo_is_own": bool(repo.is_own),

        "issue_id": issue.id,
        "issue_number": issue.number,
        "issue_title": title,
        "issue_title_len": len(title),
        "issue_body_len": len(body),
        "issue_user": issue.user or "",
        "issue_created_at_github": issue.created_at_github.isoformat() if issue.created_at_github else "",
        "issue_updated_at_github": issue.updated_at_github.isoformat() if issue.updated_at_github else "",
        "issue_comments_count": comments_count,

        "model_name": getattr(model, "name", ""),
        "model_version": getattr(model, "version", "") or "",

        "bin_is_vuln": bool(pred.bin_is_vuln),
        "bin_score": float(pred.bin_score or 0.0),
        "severity_label": pred.severity_label if pred.severity_label is not None else "",
        "severity_probs_json": sev_probs_json,
        "types_pred_json": types_pred_json,
        "types_probs_json": types_probs_json,
    }
    return row


def _write_rows(path: Path, rows: list[Dict[str, Any]], ensure_header: bool = True) -> None:
    """Escribe filas en CSV (append). Crea cabecera si el fichero no existe o está vacío."""
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)

    need_header = ensure_header and (not path.exists() or path.stat().st_size == 0)
    fieldnames = [
        "exported_at",
        "repo_full_name", "repo_is_own",
        "issue_id", "issue_number", "issue_title", "issue_title_len", "issue_body_len", "issue_user",
        "issue_created_at_github", "issue_updated_at_github", "issue_comments_count",
        "model_name", "model_version",
        "bin_is_vuln", "bin_score",
        "severity_label", "severity_probs_json",
        "types_pred_json", "types_probs_json",
    ]
    with path.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        if need_header:
            w.writeheader()
        for r in rows:
            w.writerow(r)
