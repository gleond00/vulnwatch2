# core/urls.py
from django.urls import path, include
from rest_framework.routers import SimpleRouter
from .views import (
    health, GitHubPingView, RepositoryViewSet, IssueViewSet, PredictView
)

router = SimpleRouter()
router.register(r"repos", RepositoryViewSet, basename="repos")
router.register(r"issues", IssueViewSet, basename="issues")

urlpatterns = [
    path("health/", health, name="health"),
    path("github/ping/", GitHubPingView.as_view(), name="github-ping"),
    path("predict/", PredictView.as_view(), name="predict"),
    path("", include(router.urls)),
]
