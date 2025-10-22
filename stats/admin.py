from django.contrib import admin
from django.db.models import Count
from django.urls import path
from django.http import HttpRequest, HttpResponse
from django.template.response import TemplateResponse

from core.models import Repository, Issue, IssuePrediction, ModelLanguage
from .models import SiteStats

@admin.register(SiteStats)
class SiteStatsAdmin(admin.ModelAdmin):
    change_list_template = "admin/stats/stats.html"

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return True
    def has_delete_permission(self, request, obj=None): return False

    def get_urls(self):
        urls = super().get_urls()
        custom = [path("", self.admin_site.admin_view(self.stats_view), name="stats_sitestats_changelist")]
        return custom + urls

    def stats_view(self, request: HttpRequest) -> HttpResponse:
        repos_total = Repository.objects.count()
        repos_with_vuln = Repository.objects.filter(issues__prediction__bin_is_vuln=True).distinct().count()

        top_vuln = (
            IssuePrediction.objects.filter(bin_is_vuln=True)
            .values("issue__repo__full_name")
            .annotate(cnt=Count("id"))
            .order_by("-cnt")[:10]
        )
        top_repos_labels = [r["issue__repo__full_name"] for r in top_vuln]
        top_repos_counts = [r["cnt"] for r in top_vuln]

        issues_total = Issue.objects.count()
        issues_with_pred = IssuePrediction.objects.count()
        issues_vuln = IssuePrediction.objects.filter(bin_is_vuln=True).count()

        sev_rows = (
            IssuePrediction.objects.exclude(severity_label__isnull=True)
            .values("severity_label").annotate(cnt=Count("id")).order_by("severity_label")
        )
        sev_labels = [str(r["severity_label"]) for r in sev_rows]
        sev_counts = [r["cnt"] for r in sev_rows]

        # --- NUEVO: distribución por tipos de vulnerabilidad ---
        # types_pred es una lista de strings; agregamos en Python (portátil para SQLite).
        type_counts = {}
        for p in IssuePrediction.objects.filter(bin_is_vuln=True).only("types_pred"):
            for t in (p.types_pred or []):
                type_counts[t] = type_counts.get(t, 0) + 1
        type_labels = sorted(type_counts.keys())
        type_values = [type_counts[k] for k in type_labels]

        ml_total = ModelLanguage.objects.count()
        ml_active = ModelLanguage.objects.filter(active=True).count()

        cov_pct = round((issues_with_pred / issues_total) * 100, 1) if issues_total else 0.0
        vuln_rate_pct = round((issues_vuln / max(issues_with_pred, 1)) * 100, 1) if issues_with_pred else 0.0

        ctx = dict(
            self.admin_site.each_context(request),
            title="Estadísticas",
            repos_total=repos_total, repos_with_vuln=repos_with_vuln,
            top_repos_labels=top_repos_labels, top_repos_counts=top_repos_counts,
            issues_total=issues_total, issues_with_pred=issues_with_pred, issues_vuln=issues_vuln,
            sev_labels=sev_labels, sev_counts=sev_counts,
            type_labels=type_labels, type_values=type_values,  # <- NUEVO
            ml_total=ml_total, ml_active=ml_active,
            cov_pct=cov_pct, vuln_rate_pct=vuln_rate_pct,
        )
        return TemplateResponse(request, "admin/stats/stats.html", ctx)
