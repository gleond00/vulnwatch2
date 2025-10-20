# core/views.py
from __future__ import annotations
from typing import Any
import threading
from django import db

from django.utils import timezone as djtz
from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Repository, Issue
from .serializers import RepositorySerializer, IssueSerializer
from .services import sync_repository
from .ml import get_classifier
from .githubsync import github_ping


@api_view(["GET"])
def health(request):
    return Response({"ok": True, "now": djtz.now().isoformat()})


class GitHubPingView(APIView):
    def get(self, request):
        try:
            data = github_ping()
            return Response(data)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_502_BAD_GATEWAY)


class RepositoryViewSet(viewsets.ModelViewSet):
    queryset = Repository.objects.all().order_by("-id")
    serializer_class = RepositorySerializer

    def perform_create(self, serializer):
        """
        Guardamos el repo y lanzamos el seed en un hilo de fondo
        para NO bloquear la petición HTTP.
        """
        repo = serializer.save()

        if not repo.is_own:
            def _bg(repo_id: int):
                try:
                    # muy importante para no heredar conexiones en hilos
                    db.close_old_connections()
                    from .models import Repository as _Repo
                    from .services import seed_repository
                    r = _Repo.objects.get(id=repo_id)
                    n = seed_repository(r)  # trae TODOS los abiertos por tandas y encola clasificaciones
                    print(f"[seed_repository/bg] {r.full_name}: {n} issues abiertos importados", flush=True)
                except Exception as e:
                    print(f"[seed_repository/bg] ERROR: {e}", flush=True)

            threading.Thread(target=_bg, args=(repo.id,), daemon=True).start()

    @action(detail=True, methods=["POST"])
    def sync(self, request, pk=None):
        repo = self.get_object()
        try:
            out = sync_repository(repo)
            return Response(out)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_502_BAD_GATEWAY)


class IssueViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Issue.objects.select_related("repo").all().order_by("-updated_at")
    serializer_class = IssueSerializer

    @action(detail=False, methods=["GET"])
    def by_repo(self, request):
        repo_id = request.query_params.get("repo_id")
        if not repo_id:
            return Response({"error": "repo_id required"}, status=400)
        qs = self.get_queryset().filter(repo_id=repo_id)
        page = self.paginate_queryset(qs)
        if page is not None:
            ser = self.get_serializer(page, many=True)
            return self.get_paginated_response(ser.data)
        ser = self.get_serializer(qs, many=True)
        return Response(ser.data)


class PredictView(APIView):
    def post(self, request):
        text = (request.data or {}).get("text", "")
        if not text.strip():
            return Response({"error": "text required"}, status=400)
        clf = get_classifier()
        out = clf.predict(text)
        return Response(out)
