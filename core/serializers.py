# core/serializers.py
from __future__ import annotations
from rest_framework import serializers
from .models import Repository, Issue, Comment, IssuePrediction

class RepositorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Repository
        fields = ["id", "full_name", "is_own", "default_branch", "last_synced", "created_at"]

class IssuePredictionSerializer(serializers.ModelSerializer):
    class Meta:
        model = IssuePrediction
        fields = ["id", "model_name", "model_run_dir", "bin_is_vuln", "bin_score",
                  "severity_label", "severity_probs", "types_pred", "types_probs", "updated_at"]

class IssueSerializer(serializers.ModelSerializer):
    last_prediction = serializers.SerializerMethodField()

    class Meta:
        model = Issue
        fields = ["id", "repo", "number", "title", "body", "user", "html_url",
                  "updated_at", "is_open", "last_prediction"]

    def get_last_prediction(self, obj: Issue):
        pred = getattr(obj, "prediction", None)
        if not pred:
            pred = IssuePrediction.objects.filter(issue=obj).order_by("-updated_at").first()
        return IssuePredictionSerializer(pred).data if pred else None

class CommentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Comment
        fields = ["id", "issue", "user", "body", "html_url", "created_at"]
