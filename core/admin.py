from django.contrib import admin
from django.db.models import Exists, OuterRef, Count
from django.urls import path
from django.utils.safestring import mark_safe
from django.http import HttpRequest, HttpResponse
from django.template.response import TemplateResponse
from django import db
import threading

from .models import Repository, Issue, Comment, ModelLanguage, IssuePrediction
from django.db import models


class VulnerableIssueInline(admin.TabularInline):
    model = Issue
    extra = 0
    can_delete = False
    fields = ("number", "title", "bin_flag", "updated_at_github")
    readonly_fields = fields
    show_change_link = True
    verbose_name_plural = "Issues vulnerables"

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related("prediction")
        return qs.filter(prediction__bin_is_vuln=True)

    def bin_flag(self, obj: Issue):
        p = getattr(obj, "prediction", None)
        return "✅" if (p and p.bin_is_vuln) else "❌"
    bin_flag.short_description = "Vuln"


class IssuePredictionInline(admin.StackedInline):
    model = IssuePrediction
    extra = 0
    can_delete = False
    max_num = 1
    readonly_fields = (
        "bin_is_vuln", "bin_score", "severity_label", "severity_probs",
        "types_pred", "types_probs", "updated_at",
    )


class CommentInline(admin.TabularInline):
    model = Comment
    extra = 0
    can_delete = False
    fields = ("user", "body", "created_at_github", "updated_at_github", "created_at")
    readonly_fields = fields


@admin.register(Repository)
class RepositoryAdmin(admin.ModelAdmin):
    list_display = ("full_name", "is_own", "model", "vuln_flag", "last_synced", "created_at")
    list_filter = ("is_own", "model")
    search_fields = ("full_name",)
    inlines = (VulnerableIssueInline,)
    actions = ("seed_open_set", "sync_now")
    actions_on_top = True
    actions_on_bottom = True

    fieldsets = (
        (None, {"fields": ("full_name", "is_own", "model")}),
        ("Estado", {"fields": ("default_branch", "last_synced", "created_at")}),
    )
    readonly_fields = ("created_at",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        sub = IssuePrediction.objects.filter(issue__repo=OuterRef("pk"), bin_is_vuln=True)
        return qs.annotate(_has_vuln=Exists(sub))

    def vuln_flag(self, obj: Repository):
        return "✅" if getattr(obj, "_has_vuln", False) else "❌"
    vuln_flag.short_description = "Vuln"

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not obj.is_own and not change:
            # seed en background (no bloquea UI)
            def _bg(repo_id: int):
                try:
                    db.close_old_connections()
                    from .models import Repository as _Repo
                    from .services import seed_repository
                    repo = _Repo.objects.get(id=repo_id)
                    n = seed_repository(repo)
                    print(f"[seed] {repo.full_name}: abiertos importados={n}", flush=True)
                except Exception as e:
                    print(f"[seed] ERROR {obj.full_name}: {e}", flush=True)
            threading.Thread(target=_bg, args=(obj.id,), daemon=True).start()

    @admin.action(description="Traer TODOS los issues abiertos (seed)")
    def seed_open_set(self, request, queryset):
        def _bg(repo_id: int):
            try:
                db.close_old_connections()
                from .models import Repository as _Repo
                from .services import seed_repository
                repo = _Repo.objects.get(id=repo_id)
                seed_repository(repo)
            except Exception as e:
                print(f"[seed] ERROR repo_id={repo_id}: {e}", flush=True)
        for repo in queryset:
            threading.Thread(target=_bg, args=(repo.id,), daemon=True).start()
        self.message_user(request, "Seed lanzado en segundo plano.")

    @admin.action(description="Sync ahora (conjunto abierto)")
    def sync_now(self, request, queryset):
        def _bg(repo_id: int):
            try:
                db.close_old_connections()
                from .models import Repository as _Repo
                from .services import sync_repository
                repo = _Repo.objects.get(id=repo_id)
                sync_repository(repo)
            except Exception as e:
                print(f"[sync] ERROR repo_id={repo_id}: {e}", flush=True)
        for repo in queryset:
            threading.Thread(target=_bg, args=(repo.id,), daemon=True).start()
        self.message_user(request, "Sync lanzado en segundo plano.")


@admin.register(Issue)
class IssueAdmin(admin.ModelAdmin):
    list_display = ("number", "repo", "title_short", "bin_flag", "updated_at_github", "updated_at")
    list_filter = ("repo",)
    search_fields = ("title", "body", "user")
    list_select_related = ("repo", "prediction")
    inlines = (IssuePredictionInline, CommentInline)
    readonly_fields = ("created_at_github", "updated_at_github", "created_at", "updated_at")
    actions = ("reclassify_now",)

    def bin_flag(self, obj: Issue):
        p = getattr(obj, "prediction", None)
        if not p:
            return "—"
        return "✅" if p.bin_is_vuln else "❌"
    bin_flag.short_description = "Vuln"

    def title_short(self, obj: Issue):
        return (obj.title or "")[:80]
    title_short.short_description = "Title"

    @admin.action(description="Reclasificar seleccionados")
    def reclassify_now(self, request, queryset):
        from .jobs import enqueue_issue
        for issue in queryset:
            enqueue_issue(issue.id)
        self.message_user(request, f"Encolados {queryset.count()} issues para reclasificación")


@admin.register(ModelLanguage)
class ModelLanguageAdmin(admin.ModelAdmin):
    list_display = (
        "name", "device", "active",
        "binary_f1", "binary_precision", "binary_recall",
        "severity_acc", "types_map", "version", "trained_at",
    )
    list_filter = ("active",)
    search_fields = ("name", "version")


class SiteStats(Repository):
    class Meta:
        proxy = True
        verbose_name = "Estadísticas"
        verbose_name_plural = "Estadísticas"


@admin.register(SiteStats)
class SiteStatsAdmin(admin.ModelAdmin):
    change_list_template = "admin/core/stats.html"
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return True
    def has_delete_permission(self, request, obj=None): return False

    def get_urls(self):
        urls = super().get_urls()
        custom = [path("", self.admin_site.admin_view(self.stats_view), name="core_sitestats_changelist")]
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
        ml_total = ModelLanguage.objects.count()
        ml_active = ModelLanguage.objects.filter(active=True).count()

        # KPIs derivados
        cov_pct = round((issues_with_pred / issues_total) * 100, 1) if issues_total else 0.0
        vuln_rate_pct = round((issues_vuln / max(issues_with_pred, 1)) * 100, 1) if issues_with_pred else 0.0

        ctx = dict(
            self.admin_site.each_context(request),
            title="Estadísticas",
            repos_total=repos_total, repos_with_vuln=repos_with_vuln,
            top_repos_labels=top_repos_labels, top_repos_counts=top_repos_counts,
            issues_total=issues_total, issues_with_pred=issues_with_pred, issues_vuln=issues_vuln,
            sev_labels=sev_labels, sev_counts=sev_counts,
            ml_total=ml_total, ml_active=ml_active,
            cov_pct=cov_pct, vuln_rate_pct=vuln_rate_pct,
        )
        return TemplateResponse(request, "admin/core/stats.html", ctx)
