"""Lifecycle, deletion, cross-user access and the dashboard (Cycle 3).

Includes the FR-005 end-to-end test deferred from Cycle 2.
FR-005, FR-081, FR-082, FR-089, NFR-018, NFR-024.
"""

from unittest import mock

from django.db.models import ProtectedError
from django.urls import reverse

from apps.scans import services
from apps.scans.models import Scan, ScannedFile
from apps.scans.services import ScanStateError

from .base import PNG, ScanTestBase


class TransitionTests(ScanTestBase):
    def test_start_moves_a_draft_to_queued_exactly_once(self):
        scan = self.make_scan()
        r = self.client.post(self.url("scan-start", scan))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["status"], "queued")

        again = self.client.post(self.url("scan-start", scan))
        self.assertEqual(again.status_code, 409)
        self.assertEqual(again.data["detail"], "Cannot start a scan that is queued.")

    def test_cancelling_a_queued_scan_records_when_it_finished(self):
        scan = self.make_scan()
        services.transition(scan, "start")
        r = self.client.post(self.url("scan-cancel", scan))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["status"], "cancelled")
        self.assertIsNotNone(r.data["completed_at"])

    def test_a_draft_cannot_be_cancelled(self):
        scan = self.make_scan()
        self.assertEqual(self.client.post(self.url("scan-cancel", scan)).status_code, 409)

    def test_a_scan_with_no_accepted_files_cannot_start(self):
        scan = self.make_scan(files=(("photo.png", PNG),))  # unsupported until OCR exists
        r = self.client.post(self.url("scan-start", scan))
        self.assertEqual(r.status_code, 409)
        self.assertIn("Nothing to scan", r.data["detail"])

    def test_stale_copy_cannot_start_an_already_started_scan(self):
        # Simulates the race sequentially: both copies were loaded while the
        # scan was "draft". The conditional UPDATE re-checks the status in the
        # database, so the second start fails even though its in-memory copy
        # still says "draft". (A truly concurrent test needs threads and
        # TransactionTestCase; this proves the property the fix relies on.)
        scan = self.make_scan()
        first = Scan.objects.get(pk=scan.pk)
        second = Scan.objects.get(pk=scan.pk)

        services.transition(first, "start")
        with self.assertRaises(ScanStateError):
            services.transition(second, "start")
        self.assertEqual(Scan.objects.get(pk=scan.pk).status, "queued")


class DeleteTests(ScanTestBase):
    def test_delete_removes_stored_files_and_records(self):
        scan = self.make_scan()
        self.assertTrue(self.scan_dir(scan).is_dir())

        r = self.client.delete(self.url("scan-detail", scan))
        self.assertEqual(r.status_code, 204)
        self.assertFalse(self.scan_dir(scan).exists())
        self.assertFalse(Scan.objects.filter(pk=scan.pk).exists())
        self.assertEqual(ScannedFile.objects.count(), 0)

    def test_delete_is_refused_while_processing(self):
        scan = self.make_scan()
        Scan.objects.filter(pk=scan.pk).update(status=Scan.Status.PROCESSING)  # what Cycle 4's worker will do
        r = self.client.delete(self.url("scan-detail", scan))
        self.assertEqual(r.status_code, 409)
        self.assertTrue(self.scan_dir(scan).is_dir())

    def test_a_scan_with_nothing_stored_can_be_deleted(self):
        scan = self.make_scan(files=(("empty.txt", b""),))
        self.assertFalse(self.scan_dir(scan).exists())
        self.assertEqual(self.client.delete(self.url("scan-detail", scan)).status_code, 204)

    def test_if_files_cannot_be_removed_the_record_is_kept(self):
        # Files first, then records: a failed removal must not leave a
        # "deleted" scan whose files are still on disk.
        scan = self.make_scan()
        with mock.patch("apps.scans.services.shutil.rmtree", side_effect=PermissionError("file locked")), \
                self.assertLogs("apps.scans.services", "ERROR"):
            r = self.client.delete(self.url("scan-detail", scan))
        self.assertEqual(r.status_code, 500)
        self.assertIn("was not deleted", r.data["detail"])
        self.assertTrue(Scan.objects.filter(pk=scan.pk).exists())
        self.assertTrue(self.scan_dir(scan).is_dir())

    def test_a_user_with_scans_cannot_be_deleted_directly(self):
        # PROTECT: deleting the user would otherwise drop the scan rows and
        # strand their files on disk.
        self.make_scan()
        with self.assertRaises(ProtectedError):
            self.alice.delete()


class CrossUserAccessTests(ScanTestBase):
    """FR-005 / NFR-018 end to end - the test deferred from Cycle 2."""

    def setUp(self):
        super().setUp()
        self.alice_scan = self.make_scan(user=self.alice)

    def assert_alice_scan_untouched(self):
        scan = Scan.objects.get(pk=self.alice_scan.pk)
        self.assertEqual(scan.status, "draft")
        self.assertTrue(self.scan_dir(scan).is_dir())

    def test_another_user_gets_404_for_every_operation(self):
        self.client.force_login(self.bob)
        operations = {
            "GET detail": lambda: self.client.get(self.url("scan-detail", self.alice_scan)),
            "GET files": lambda: self.client.get(self.url("scan-files", self.alice_scan)),
            "POST start": lambda: self.client.post(self.url("scan-start", self.alice_scan)),
            "POST cancel": lambda: self.client.post(self.url("scan-cancel", self.alice_scan)),
            "DELETE": lambda: self.client.delete(self.url("scan-detail", self.alice_scan)),
        }
        for label, call in operations.items():
            with self.subTest(operation=label):
                self.assertEqual(call().status_code, 404)
        self.assert_alice_scan_untouched()

    def test_administrator_role_gets_no_bypass(self):
        # D-009: least privilege.
        self.client.force_login(self.ada)
        self.assertEqual(self.client.get(self.url("scan-detail", self.alice_scan)).status_code, 404)
        self.assertEqual(self.client.delete(self.url("scan-detail", self.alice_scan)).status_code, 404)
        self.assert_alice_scan_untouched()

    def test_lists_and_dashboard_only_show_your_own_scans(self):
        self.make_scan(user=self.bob)
        self.client.force_login(self.bob)

        listing = self.client.get(reverse("scan-list")).data
        self.assertEqual(listing["count"], 1)
        self.assertNotIn(str(self.alice_scan.pk), [row["id"] for row in listing["results"]])
        self.assertEqual(self.client.get(reverse("dashboard")).data["total_scans"], 1)

    def test_malformed_scan_id_is_404_not_500(self):
        self.assertEqual(self.client.get("/api/scans/not-a-uuid/").status_code, 404)


class DashboardTests(ScanTestBase):
    def test_summary_counts_honestly(self):
        self.make_scan(files=(("a.txt", b"synthetic a\n"), ("b.txt", b"synthetic b\n"), ("empty.txt", b"")))
        self.make_scan(files=(("c.txt", b"synthetic c\n"),))

        data = self.client.get(reverse("dashboard")).data
        self.assertEqual(data["total_scans"], 2)
        self.assertEqual(data["files_inventoried"], 4)
        self.assertEqual(data["files_accepted"], 3)
        self.assertEqual(data["files_scanned"], 0)    # nothing processes until Cycle 4
        self.assertIsNone(data["total_findings"])     # null, not 0: detection doesn't exist yet
