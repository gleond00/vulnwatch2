from django.apps import AppConfig
import threading, time

class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self):
        import core.signals  # registra señales

        # PRAGMAs suaves para SQLite
        try:
            from django.db import connection
            if "sqlite3" in connection.settings_dict.get("ENGINE", ""):
                with connection.cursor() as c:
                    c.execute("PRAGMA journal_mode=WAL;")
                    c.execute("PRAGMA synchronous=NORMAL;")
                    c.execute("PRAGMA foreign_keys=ON;")
        except Exception:
            pass

        # worker de clasificación
        from .jobs import start_jobs_worker
        start_jobs_worker()

        # scheduler de sync (con guard para no duplicar en autoreload)
        if getattr(self, "_started", False):
            return
        self._started = True

        from django.conf import settings
        from core.services import sync_all_repos
        interval = int(getattr(settings, "SYNC_INTERVAL_MIN", 10)) * 60
        mins = max(1, interval // 60)

        def loop():
            print(f"[scheduler] hilo iniciado ✅ (cada {mins} min)", flush=True)
            while True:
                try:
                    sync_all_repos()
                except Exception as e:
                    print(f"[sync] loop error: {e}", flush=True)
                time.sleep(interval)

        threading.Thread(target=loop, daemon=True).start()
