# core/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction

from .models import Issue, Comment, IssuePrediction
from .signal_guard import are_signals_suppressed
from .jobs import enqueue_issue
from .exporter import enqueue_export


@receiver(post_save, sender=Issue, dispatch_uid="core_issue_post_save")
def issue_post_save(sender, instance: Issue, created, **kwargs):
    if are_signals_suppressed():
        return
    issue_id = instance.id
    transaction.on_commit(lambda: enqueue_issue(issue_id))


@receiver(post_save, sender=Comment, dispatch_uid="core_comment_post_save")
def comment_post_save(sender, instance: Comment, created, **kwargs):
    if are_signals_suppressed():
        return
    if created and instance.issue_id:
        iid = instance.issue_id
        transaction.on_commit(lambda: enqueue_issue(iid))


@receiver(post_save, sender=IssuePrediction, dispatch_uid="core_prediction_post_save")
def prediction_post_save(sender, instance: IssuePrediction, created, **kwargs):
    """
    Cada vez que se crea/actualiza una predicción, exportamos una fila al CSV.
    """
    if instance.issue_id:
        issue_id = instance.issue_id
        transaction.on_commit(lambda: enqueue_export(issue_id, reason="pred_upsert"))
