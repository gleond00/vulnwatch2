from __future__ import annotations
from django.db import models
from django.utils import timezone

class ModelLanguage(models.Model):
    name = models.CharField(max_length=120, unique=True)
    device = models.CharField(max_length=20, default="cpu")
    active = models.BooleanField(default=False)

    binary_f1 = models.FloatField(null=True, blank=True)
    binary_precision = models.FloatField(null=True, blank=True)
    binary_recall = models.FloatField(null=True, blank=True)
    severity_acc = models.FloatField(null=True, blank=True)
    types_map = models.FloatField(null=True, blank=True)
    metrics = models.JSONField(null=True, blank=True)
    trained_at = models.DateTimeField(null=True, blank=True)
    version = models.CharField(max_length=50, null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["active"])]

    def __str__(self):
        return f"{self.name} ({'active' if self.active else 'inactive'})"

class Repository(models.Model):
    full_name = models.CharField(max_length=200, unique=True)
    is_own = models.BooleanField(default=False)
    default_branch = models.CharField(max_length=100, null=True, blank=True)
    last_synced = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    model = models.ForeignKey(
        ModelLanguage, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="repositories"
    )

    class Meta:
        indexes = [models.Index(fields=["full_name"])]

    def __str__(self):
        return f"{self.full_name} ({'own' if self.is_own else 'ext'})"

class Issue(models.Model):
    repo = models.ForeignKey(Repository, on_delete=models.CASCADE, related_name="issues")
    number = models.IntegerField(null=True, blank=True)
    title = models.CharField(max_length=400)
    body = models.TextField(null=True, blank=True)
    user = models.CharField(max_length=120, null=True, blank=True)

    created_at_github = models.DateTimeField(null=True, blank=True)
    updated_at_github = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["repo", "number"]),
            models.Index(fields=["updated_at_github"]),
            models.Index(fields=["updated_at"]),
        ]
        unique_together = (("repo", "number"),)

    def __str__(self):
        return f"[{self.repo.full_name}] #{self.number if self.number else 'own'} - {self.title[:32]}"

class Comment(models.Model):
    issue = models.ForeignKey(Issue, on_delete=models.CASCADE, related_name="comments")
    external_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    body = models.TextField(null=True, blank=True)
    user = models.CharField(max_length=120, null=True, blank=True)

    created_at_github = models.DateTimeField(null=True, blank=True)
    updated_at_github = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["issue"]),
            models.Index(fields=["external_id"]),
            models.Index(fields=["updated_at_github"]),
        ]

    def __str__(self):
        return f"Comment on issue {self.issue_id} by {self.user or '-'}"

class IssuePrediction(models.Model):
    issue = models.OneToOneField(Issue, on_delete=models.CASCADE, related_name="prediction")
    model = models.ForeignKey(ModelLanguage, on_delete=models.CASCADE, related_name="predictions")
    updated_at = models.DateTimeField(default=timezone.now)

    bin_is_vuln = models.BooleanField(default=False)
    bin_score = models.FloatField(default=0.0)

    severity_label = models.IntegerField(null=True, blank=True)
    severity_probs = models.JSONField(null=True, blank=True)

    types_pred = models.JSONField(null=True, blank=True)
    types_probs = models.JSONField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["issue"]),
            models.Index(fields=["updated_at"]),
            models.Index(fields=["bin_is_vuln"]),
        ]

    def __str__(self):
        return f"Pred(issue={self.issue_id}, model={self.model.name})"
