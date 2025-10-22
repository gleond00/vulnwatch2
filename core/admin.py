from django.contrib import admin
from django.db.models import Exists, OuterRef
from django import db
from django.db import transaction
import threading

from .models import Repository, Issue, Comment, ModelLanguage, IssuePrediction


# --- INLINE: todos los Issues dentro del Repo ---
class IssueInline(admin.TabularInline):
    model = Issue
    extra = 0
    can_delete = False
    show_change_link = True
    fields = ("number", "title_short", "bin_flag", "updated_at_github", "updated_at")
    readonly_fields = fields
    ordering = ("-updated_at_github",)  # por defecto

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related("prediction")
        order = (request.GET.get("issues_order") or "").lower()
        if order == "vuln":
            # vulnerables primero, y dentro por última actualización
            return qs.order_by("-prediction__bin_is_vuln", "-updated_at_github", "-id")
        # por defecto: últimas actualizaciones primero
        return qs.order_by("-updated_at_github", "-id")

    def bin_flag(self, obj: Issue):
        p = getattr(obj, "prediction", None)
        if p is None:
            return "—"
        return "✅" if p.bin_is_vuln else "❌"
    bin_flag.short_description = "Vuln"  # texto de cabecera

    def title_short(self, obj: Issue):
        return (obj.title or "")[:80]
    title_short.short_description = "Title"


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
    # NO cambiamos la plantilla. Sólo añadimos un JS estático con Media.
    list_display = ("full_name", "is_own", "model", "vuln_flag", "last_synced", "created_at")
    list_filter = ("is_own", "model")
    search_fields = ("full_name",)
    inlines = (IssueInline,)
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
            repo_id = obj.id

            def _bg(_repo_id: int):
                try:
                    db.close_old_connections()
                    from .models import Repository as _Repo
                    from .services import seed_repository
                    repo = _Repo.objects.get(id=_repo_id)
                    n = seed_repository(repo)
                    print(f"[seed] {repo.full_name}: abiertos importados={n}", flush=True)
                except Exception as e:
                    print(f"[seed] ERROR repo_id={_repo_id}: {e}", flush=True)

            transaction.on_commit(
                lambda: threading.Thread(target=_bg, args=(repo_id,), daemon=True).start()
            )

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

    @admin.action(description="Sync ahora (conjunto abierto / ventana)")
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

    class Media:
        # Incluimos un JS estático que vuelve la cabecera "Vuln" clicable.
        js = ("core/admin_sort_vuln.js",)


@admin.register(Issue)
class IssueAdmin(admin.ModelAdmin):
    # Oculto en el índice, pero accesible desde el inline
    def get_model_perms(self, request):
        return {}

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
