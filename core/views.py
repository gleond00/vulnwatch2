# core/views.py
from __future__ import annotations
from typing import Any

from django.db.models import Case, When, Value, IntegerField
from django.utils import timezone as djtz
from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.filters import OrderingFilter

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
        Guardamos el repo. (El seed en background ya lo tienes en admin/views con on_commit.)
        """
        serializer.save()

    @action(detail=True, methods=["POST"])
    def sync(self, request, pk=None):
        repo = self.get_object()
        try:
            out = sync_repository(repo)
            return Response(out)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_502_BAD_GATEWAY)


class IssueViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Listado de issues con soporte de ordenación DRF.
    - Campo virtual 'pred_vuln' = 1 si el issue es vulnerable, 0 si no.
    - Orden por defecto: últimas actualizaciones primero.
    - Orden disponibles: pred_vuln, updated_at_github, updated_at, number.
    """
    serializer_class = IssueSerializer
    filter_backends = (OrderingFilter,)
    ordering_fields = ("pred_vuln", "updated_at_github", "updated_at", "number")
    ordering = ("-updated_at_github",)

    def get_queryset(self):
        # Annotate: 1 si hay predicción binaria positiva, si no 0
        qs = (Issue.objects
              .select_related("repo")
              .annotate(
                  pred_vuln=Case(
                      When(prediction__bin_is_vuln=True, then=Value(1)),
                      default=Value(0),
                      output_field=IntegerField(),
                  )
              )
              .order_by(*self.ordering))
        return qs

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
