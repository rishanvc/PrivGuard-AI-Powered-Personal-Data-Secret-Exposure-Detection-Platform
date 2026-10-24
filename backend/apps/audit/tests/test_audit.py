"""The audit log is append-only and holds only safe metadata (SRS 7.2.8, FR-116, FR-117)."""

from django.contrib.auth import get_user_model
from django.db.models import ProtectedError
from django.test import TestCase

from apps.audit.models import AppendOnlyError, AuditLog
from apps.audit.services import record

User = get_user_model()


class AuditLogTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create(username="alice")
        self.entry = record(user=self.alice, action="finding.review", resource_type="finding",
                            resource_id="00000000-0000-0000-0000-000000000001",
                            metadata={"from_status": "new", "to_status": "confirmed"})

    def test_a_record_is_written_with_its_safe_metadata(self):
        stored = AuditLog.objects.get()
        self.assertEqual((stored.user, stored.action, stored.result), (self.alice, "finding.review", "success"))
        self.assertEqual(stored.safe_metadata, {"from_status": "new", "to_status": "confirmed"})

    def test_metadata_outside_the_safe_list_is_refused(self):
        with self.assertRaises(ValueError):
            record(user=self.alice, action="finding.review", resource_type="finding", resource_id="x",
                   metadata={"masked_value": "a***@mailhost-synthetic.net"})
        self.assertEqual(AuditLog.objects.count(), 1)  # nothing stored

    def test_a_record_cannot_be_changed(self):
        self.entry.action = "something.else"
        with self.assertRaises(AppendOnlyError):
            self.entry.save()
        with self.assertRaises(AppendOnlyError):
            AuditLog.objects.update(action="something.else")  # the bulk route too
        self.assertEqual(AuditLog.objects.get().action, "finding.review")

    def test_a_record_cannot_be_deleted(self):
        with self.assertRaises(AppendOnlyError):
            self.entry.delete()
        with self.assertRaises(AppendOnlyError):
            AuditLog.objects.all().delete()
        self.assertEqual(AuditLog.objects.count(), 1)

    def test_who_did_it_cannot_vanish_with_the_account(self):
        with self.assertRaises(ProtectedError):
            self.alice.delete()
