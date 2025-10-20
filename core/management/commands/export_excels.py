# core/management/commands/export_excels.py
from django.core.management.base import BaseCommand
from django.conf import settings
from core.models import Repository, Artifact
import pandas as pd
from pathlib import Path

class Command(BaseCommand):
    help = "Exporta repos y artifacts a Excel"

    def handle(self, *args, **options):
        outdir = Path(settings.EXPORT_DIR); outdir.mkdir(parents=True, exist_ok=True)
        df_repos = pd.DataFrame([{
            "id": r.id, "full_name": r.full_name, "last_synced": r.last_synced
        } for r in Repository.objects.all()])
        df_repos.to_excel(outdir/"repos.xlsx", index=False)

        rows=[]
        for a in Artifact.objects.select_related("repo").prefetch_related("predictions"):
            last = a.predictions.order_by("-created_at").first()
            rows.append({
                "artifact_id": a.id, "repo": a.repo.full_name, "kind": a.kind,
                "number": a.number, "title": a.title, "updated_at": a.updated_at,
                "html_url": a.html_url,
                "bin_is_vuln": last.bin_is_vuln if last else None,
                "bin_score": last.bin_score if last else None,
                "types_pred": ",".join(last.types_pred) if (last and last.types_pred) else "",
                "severity_label": last.severity_label if last else None,
            })
        pd.DataFrame(rows).to_excel(outdir/"artifacts.xlsx", index=False)
        self.stdout.write(f"Exportado a {outdir}")
