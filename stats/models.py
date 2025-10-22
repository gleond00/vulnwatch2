from django.db import models
from core.models import Repository

class SiteStats(Repository):
    class Meta:
        proxy = True
        app_label = "stats"
        verbose_name = "Estadísticas"
        verbose_name_plural = "Estadísticas"
