from django.core.management.base import BaseCommand, CommandParser
from core.models import Repository
from core.services import sync_repository, sync_all_repos

class Command(BaseCommand):
    help = "Sincroniza repos externos con GitHub."

    def add_arguments(self, parser: CommandParser):
        parser.add_argument("--repo", type=str, help="full_name del repo (owner/name). Si no, todos.")

    def handle(self, *args, **opts):
        full = opts.get("repo")
        if full:
            try:
                repo = Repository.objects.get(full_name=full)
            except Repository.DoesNotExist:
                self.stderr.write(self.style.ERROR(f"Repo {full} no existe"))
                return
            out = sync_repository(repo.id)
            self.stdout.write(self.style.SUCCESS(f"{full}: {out}"))
        else:
            out = sync_all_repos()
            self.stdout.write(self.style.SUCCESS(str(out)))
