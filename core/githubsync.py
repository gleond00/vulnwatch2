# core/githubsync.py
from __future__ import annotations
import os
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
    r = requests.get(url, headers=_headers(), params=params, timeout=30)
    if r.status_code == 401:
        raise RuntimeError("GitHub 401 Unauthorized: revisa GITHUB_TOKEN (PAT con scope public_repo).")
    # manejo explícito de rate limit
    if r.status_code == 403:
        rem = r.headers.get("X-RateLimit-Remaining")
        if rem == "0":
            reset = r.headers.get("X-RateLimit-Reset")
            raise RuntimeError(f"GitHub rate limit excedido (X-RateLimit-Reset={reset}). Configura GITHUB_TOKEN.")
    r.raise_for_status()
    return r

def github_ping() -> Dict[str, Any]:
    return _get(f"{API}/rate_limit").json()

def fetch_all_open_issues(full_name: str) -> List[Dict[str, Any]]:
    """Todos los issues ABIERTOS (no PRs) con paginación."""
    owner, repo = full_name.split("/", 1)
    url = f"{API}/repos/{owner}/{repo}/issues"
    params = {"state": "open", "sort": "updated", "direction": "desc", "per_page": 100}
    out: List[Dict[str, Any]] = []
    while url:
        r = _get(url, params if "?" not in url else None)
        batch = [it for it in r.json() if "pull_request" not in it]
        for it in batch:
            out.append({
                "number": it.get("number"),
                "title": it.get("title"),
                "body": it.get("body"),
                "user": (it.get("user") or {}).get("login"),
                "created_at": it.get("created_at"),
                "updated_at": it.get("updated_at"),
                "html_url": it.get("html_url"),
            })
        url = r.links.get("next", {}).get("url")
    return out

def fetch_issue_comments(full_name: str, number: int) -> List[Dict[str, Any]]:
    """Comentarios de un issue concreto (paginado)."""
    owner, repo = full_name.split("/", 1)
    url = f"{API}/repos/{owner}/{repo}/issues/{number}/comments"
    params = {"per_page": 100}
    out: List[Dict[str, Any]] = []
    while url:
        r = _get(url, params if "?" not in url else None)
        for it in r.json():
            out.append({
                "id": it.get("id"),
                "body": it.get("body"),
                "user": (it.get("user") or {}).get("login"),
                "created_at": it.get("created_at"),
                "updated_at": it.get("updated_at"),
                "html_url": it.get("html_url"),
            })
        url = r.links.get("next", {}).get("url")
    return out
