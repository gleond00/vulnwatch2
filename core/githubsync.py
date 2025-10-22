# core/githubsync.py
from __future__ import annotations
import os, time
from typing import Dict, Any, List, Optional
import requests

API = "https://api.github.com"

def _token() -> str:
    try:
        from django.conf import settings
        tok = getattr(settings, "GITHUB_TOKEN", "") or ""
    except Exception:
        tok = ""
    tok = tok or os.getenv("GITHUB_TOKEN", "")
    return tok.strip().strip('"').strip("'")

def _headers() -> Dict[str, str]:
    tok = _token()
    h = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "VulnWatch-Django/0.1 (+local-dev)",
    }
    if tok:
        h["Authorization"] = f"token {tok}"
    return h

def _get(url: str, params: Optional[dict] = None) -> requests.Response:
    """
    GET con manejo de 401 y rate-limit (403 + Remaining=0).
    Si se llega al límite, espera hasta el reset y reintenta.
    """
    while True:
        r = requests.get(url, headers=_headers(), params=params, timeout=30)
        if r.status_code == 401:
            raise RuntimeError("GitHub 401 Unauthorized: revisa GITHUB_TOKEN (PAT con scope public_repo).")
        if r.status_code == 403 and r.headers.get("X-RateLimit-Remaining") == "0":
            reset = r.headers.get("X-RateLimit-Reset")
            try:
                reset_ts = int(reset)
            except Exception:
                reset_ts = int(time.time()) + 60
            wait = max(0, reset_ts - int(time.time())) + 1
            wait = min(wait, 900)  # máx 15 min
            print(f"[github] rate limit agotado. Espero {wait}s y continúo…", flush=True)
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r

def _seed_limit_cfg() -> int:
    """
    Límite SOLO para el SEED inicial.
    0 o <0 => sin límite en seed (no recomendado para repos gigantes).
    """
    try:
        from django.conf import settings
        n = int(getattr(settings, "MAX_SEED_ISSUES", 100))
        return max(0, n)
    except Exception:
        try:
            return max(0, int(os.getenv("MAX_SEED_ISSUES", "100")))
        except Exception:
            return 100

def _max_comments_cfg() -> Optional[int]:
    try:
        from django.conf import settings
        n = getattr(settings, "MAX_COMMENTS_PER_ISSUE", None)
        if n is None: return None
        n = int(n)
        return n if n > 0 else None
    except Exception:
        return None

def github_ping() -> Dict[str, Any]:
    return _get(f"{API}/rate_limit").json()

def fetch_all_open_issues(full_name: str) -> List[Dict[str, Any]]:
    """
    Issues ABIERTOS ordenados por 'updated desc' (paginado).
    Respeta MAX_SEED_ISSUES para el SEED inicial.
    """
    owner, repo = full_name.split("/", 1)
    limit = _seed_limit_cfg()
    per_page = 100 if (limit == 0 or limit >= 100) else limit

    url = f"{API}/repos/{owner}/{repo}/issues"
    params = {"state": "open", "sort": "updated", "direction": "desc", "per_page": per_page}
    out: List[Dict[str, Any]] = []

    while url:
        r = _get(url, params if "?" not in url else None)
        batch_raw = r.json()
        batch = [it for it in batch_raw if "pull_request" not in it]
        for it in batch:
            out.append({
                "number": it.get("number"),
                "title": it.get("title"),
                "body": it.get("body"),
                "user": (it.get("user") or {}).get("login"),
                "created_at": it.get("created_at"),
                "updated_at": it.get("updated_at"),
                "html_url": it.get("html_url"),
                "comments": it.get("comments", 0),
                "state": it.get("state", "open"),
            })
            if limit > 0 and len(out) >= limit:
                return out[:limit]
        url = r.links.get("next", {}).get("url")

    return out

def fetch_issues_since(full_name: str, since_iso: str) -> List[Dict[str, Any]]:
    """
    Issues (abiertos y cerrados) ACTUALIZADOS desde 'since_iso', 'updated desc'.
    Usado en sync incremental SIN límite (crecimiento libre).
    """
    owner, repo = full_name.split("/", 1)
    url = f"{API}/repos/{owner}/{repo}/issues"
    params = {
        "state": "all",
        "sort": "updated",
        "direction": "desc",
        "since": since_iso,
        "per_page": 100,
    }
    out: List[Dict[str, Any]] = []
    while url:
        r = _get(url, params if "?" not in url else None)
        batch_raw = r.json()
        batch = [it for it in batch_raw if "pull_request" not in it]
        for it in batch:
            out.append({
                "number": it.get("number"),
                "title": it.get("title"),
                "body": it.get("body"),
                "user": (it.get("user") or {}).get("login"),
                "created_at": it.get("created_at"),
                "updated_at": it.get("updated_at"),
                "html_url": it.get("html_url"),
                "comments": it.get("comments", 0),
                "state": it.get("state", "open"),
            })
        url = r.links.get("next", {}).get("url")
    return out

def fetch_issue_comments(full_name: str, number: int, max_count: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Comentarios de un issue concreto (paginado).
    max_count limita (opcional) por rendimiento.
    """
    owner, repo = full_name.split("/", 1)
    url = f"{API}/repos/{owner}/{repo}/issues/{number}/comments"
    params = {"per_page": 100}
    out: List[Dict[str, Any]] = []
    max_count = max_count if (max_count is not None) else _max_comments_cfg()

    while url:
        r = _get(url, params if "?" not in url else None)
        rows = r.json()
        for it in rows:
            out.append({
                "id": it.get("id"),
                "body": it.get("body"),
                "user": (it.get("user") or {}).get("login"),
                "created_at": it.get("created_at"),
                "updated_at": it.get("updated_at"),
                "html_url": it.get("html_url"),
            })
            if max_count is not None and len(out) >= max_count:
                return out[:max_count]
        url = r.links.get("next", {}).get("url")
    return out
