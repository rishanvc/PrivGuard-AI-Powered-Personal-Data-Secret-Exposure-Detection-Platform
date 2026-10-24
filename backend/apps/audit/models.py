"""The audit log (SRS 7.2.8, FR-116, FR-117).

Append-only: a record can be written once and never changed or deleted
through the application, so the log can be trusted as a history. Records
point at what they describe by ID, not by foreign key, so they outlive it -
deleting a scan does not delete the record of what was done to it.

Cycle 7 records finding reviews (UC-03). Cycle 11 adds logins, scan creation
and deletion, redaction, export and policy changes.
"""

import uuid

from django.conf import settings
from django.db import models


class AppendOnlyError(Exception):
    """An attempt to change or delete an audit record."""


class AuditLogQuerySet(models.QuerySet):
    """Bulk operations skip a model's save() and delete(), so they are refused here too.
    (Raw SQL could still change the table: database-level protection is Cycle 12 hardening.)"""

    def update(self, **kwargs):
        raise AppendOnlyError("Audit records cannot be changed.")

    def delete(self):
        raise AppendOnlyError("Audit records cannot be deleted.")


class AuditLog(models.Model):
    class Result(models.TextChoices):
        SUCCESS = "success", "Success"
        FAILURE = "failure", "Failure"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # PROTECT: who did what must not vanish with the account.
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="audit_records")
    action = models.CharField(max_length=64)          # e.g. "finding.review"
    resource_type = models.CharField(max_length=32)   # e.g. "finding"
    resource_id = models.CharField(max_length=64)     # the ID as text: survives the resource being deleted
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    result = models.CharField(max_length=16, choices=Result.choices, default=Result.SUCCESS)
    # FR-117: IDs, types and statuses only - never a value, a password or document text.
    safe_metadata = models.JSONField(default=dict, blank=True)

    objects = AuditLogQuerySet.as_manager()

    class Meta:
        db_table = "privguard_audit_log"
        ordering = ["-timestamp"]
        indexes = [models.Index(fields=["resource_type", "resource_id", "-timestamp"])]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise AppendOnlyError("Audit records cannot be changed.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise AppendOnlyError("Audit records cannot be deleted.")

    def __str__(self) -> str:
        return f"{self.action} {self.resource_type}:{self.resource_id} ({self.result})"
