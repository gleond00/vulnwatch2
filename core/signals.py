from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction

from .models import Issue, Comment
from .signal_guard import are_signals_suppressed
from .jobs import enqueue_issue

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
