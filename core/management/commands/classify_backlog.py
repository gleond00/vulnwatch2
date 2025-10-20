from django.core.management.base import BaseCommand
from core.models import Issue
from core.services import schedule_classify_issue

class Command(BaseCommand):
    help = "Reclasifica todos los issues (útil si cambias de modelo)."

    def handle(self, *args, **opts):
        n = 0
        for it in Issue.objects.all().only("id"):
            schedule_classify_issue(it.id)
            n += 1
        self.stdout.write(self.style.SUCCESS(f"Reclasificados: {n}"))
