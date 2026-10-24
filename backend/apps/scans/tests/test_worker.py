"""The scan worker: claiming, extraction outcomes, cancellation, recovery (Cycle 4).

FR-028, FR-082, FR-089, FR-115, NFR-002, NFR-028, NFR-029, NFR-030.

Most tests replace the isolated child with an in-process stand-in - fast,
deterministic, and able to simulate timeouts and crashes on demand. One test
runs the real loop with a real child process end to end.
"""

import time
from collections import Counter
from datetime import timedelta

from django.test import SimpleTestCase
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.core.health import collect_health
from apps.scans import services, worker
from apps.scans.models import Finding, Scan, ScannedFile, WorkerHeartbeat
from privguard_engine.detectors import DETECTION_VERSION
from privguard_engine.isolation import (
    CANCELLED, CRASHED, DONE, ERROR, TIMEOUT, EngineError, Outcome, decode_reply, encode_reply, perform,
)
from privguard_engine.risk import RISK_POLICY_VERSION, SEVERITY_POLICY_VERSION
from tests.engine import builders, secret_fixtures

from .base import EXE, ScanTestBase

S, FS, E = Scan.Status, ScannedFile.Status, ScannedFile.Extraction


def in_process(job, keep_waiting):
    """Stand-in for ExtractionSupervisor.run: the child's work, in THIS process -
    including the JSON round trip and every check the parent applies to a reply."""
    started = time.monotonic()
    return Outcome(DONE, decode_reply(encode_reply(perform(job))), time.monotonic() - started)


class WorkerTestBase(ScanTestBase):
    def queued(self, files, user=None):
        return services.transition(self.make_scan(user=user, files=files), "start")

    def claim_and_process(self, run_job=in_process):
        scan = worker.claim_next_scan()
        return scan, worker.process_scan(scan, run_job)

    @staticmethod
    def files(scan):
        return {f.relative_path: f for f in ScannedFile.objects.filter(scan=scan)}


class FinalStatusRuleTests(SimpleTestCase):
    def test_the_rules(self):
        cases = [
            ([E.SUCCEEDED, E.SUCCEEDED], S.COMPLETED),
            ([E.SUCCEEDED, E.PARTIAL], S.PARTIALLY_COMPLETED),
            ([E.SUCCEEDED, E.FAILED], S.PARTIALLY_COMPLETED),
            ([E.SUCCEEDED, E.NOT_SUPPORTED], S.PARTIALLY_COMPLETED),
            ([E.PARTIAL], S.PARTIALLY_COMPLETED),
            ([E.FAILED, E.NOT_SUPPORTED], S.FAILED),
            ([], S.FAILED),
        ]
        for statuses, expected in cases:
            with self.subTest(statuses=statuses):
                self.assertEqual(worker.final_status(statuses), expected)


class ClaimTests(WorkerTestBase):
    def test_claims_the_oldest_queued_scan_and_marks_it_processing(self):
        older = self.queued([("a.txt", b"synthetic a\n")])
        self.queued([("b.txt", b"synthetic b\n")])
        scan = worker.claim_next_scan()
        self.assertEqual(scan.pk, older.pk)
        self.assertEqual(scan.status, S.PROCESSING)
        self.assertIsNotNone(scan.heartbeat_at)
        self.assertIsNotNone(scan.started_at)
        self.assertIn("extraction_version", scan.configuration)

    def test_nothing_queued_means_nothing_claimed(self):
        self.make_scan()  # a draft is not queued
        self.assertIsNone(worker.claim_next_scan())

    def test_a_resumed_scan_keeps_its_original_start_time(self):
        self.queued([("a.txt", b"synthetic\n")])
        first = worker.claim_next_scan()
        worker._requeue(first.pk)
        again = worker.claim_next_scan()
        self.assertEqual(again.started_at, first.started_at)


class ProcessingTests(WorkerTestBase):
    def test_every_accepted_file_is_extracted_and_the_scan_completes(self):
        self.queued([
            ("notes.txt", b"synthetic notes\n"),
            ("report.pdf", builders.pdf_bytes(["Synthetic report"])),
            ("app.py", b"print('synthetic')\n"),
            ("invoice.pdf", EXE),  # rejected at intake: must be left alone
        ])
        scan, result = self.claim_and_process()
        self.assertEqual(result, S.COMPLETED)

        files = self.files(scan)
        for name in ("notes.txt", "report.pdf", "app.py"):
            with self.subTest(file=name):
                self.assertEqual(files[name].processing_status, FS.COMPLETED)
                self.assertEqual(files[name].extraction_status, E.SUCCEEDED)
                self.assertGreater(files[name].extraction_stats["segments"], 0)
                self.assertIn("seconds", files[name].extraction_stats)
                self.assertIsNotNone(files[name].processed_at)
        self.assertEqual(files["invoice.pdf"].processing_status, FS.REJECTED)

        scan.refresh_from_db()
        self.assertEqual((scan.status, scan.processed_files, scan.failed_files), (S.COMPLETED, 3, 0))
        self.assertIsNotNone(scan.completed_at)
        self.assertIsNone(scan.heartbeat_at)
        self.assertEqual(scan.total_findings, 0)  # searched - and these synthetic files hold no personal data
        self.assertEqual(scan.error_summary, "")

    def test_a_partly_readable_file_makes_the_scan_partially_completed(self):
        self.queued([("notes.txt", b"synthetic\n"), ("report.pdf", builders.pdf_bytes(["Page one", ""]))])
        scan, result = self.claim_and_process()
        self.assertEqual(result, S.PARTIALLY_COMPLETED)
        self.assertEqual(self.files(scan)["report.pdf"].extraction_status, E.PARTIAL)
        scan.refresh_from_db()
        self.assertIn("1 of 2 files", scan.error_summary)

    def test_a_scan_where_nothing_can_be_read_fails(self):
        self.queued([("report.pdf", b"%PDF-1.4 passes intake, but is not a real PDF")])
        scan, result = self.claim_and_process()
        self.assertEqual(result, S.FAILED)
        record = self.files(scan)["report.pdf"]
        self.assertEqual((record.processing_status, record.extraction_status), (FS.FAILED, E.FAILED))
        scan.refresh_from_db()
        self.assertEqual(scan.failed_files, 1)

    def test_timeouts_and_crashes_fail_that_file_and_the_scan_continues(self):
        queued = self.queued([("a.txt", b"synthetic a\n"), ("b.txt", b"synthetic b\n"), ("c.txt", b"synthetic c\n")])
        scripted = {"a.txt": TIMEOUT, "b.txt": CRASHED}
        name_by_path = {f.stored_file.path: f.file_name for f in ScannedFile.objects.filter(scan=queued)}

        def misbehaving(job, keep_waiting):
            name = name_by_path[job.path]
            if name in scripted:
                return Outcome(scripted[name], None, 3.0)
            return in_process(job, keep_waiting)

        scan, result = self.claim_and_process(misbehaving)
        self.assertEqual(result, S.PARTIALLY_COMPLETED)
        files = self.files(scan)
        self.assertIn("took longer than", files["a.txt"].extraction_detail)
        self.assertIn("stopped unexpectedly", files["b.txt"].extraction_detail)
        self.assertEqual(files["c.txt"].extraction_status, E.SUCCEEDED)
        scan.refresh_from_db()
        self.assertEqual(scan.failed_files, 2)

    def test_a_missing_stored_file_is_reported_not_crashed_on(self):
        scan = self.queued([("notes.txt", b"synthetic\n")])
        record = ScannedFile.objects.get(scan=scan)
        record.stored_file.storage.delete(record.stored_file.name)
        scan, result = self.claim_and_process()
        self.assertEqual(result, S.FAILED)
        self.assertEqual(self.files(scan)["notes.txt"].extraction_detail, worker.MISSING)

    def test_no_extracted_text_or_raw_value_is_stored_anywhere(self):
        # FR-115: the text exists only in memory. The one deliberate exception
        # is a finding's preview (FR-085): masked, and at most 40 characters
        # either side. Search every column of every row - and every API
        # response - for text the files contain.
        marker = "SYNTHETIC-MARKER-7Q3X"
        filler = "followed by a long stretch of unrelated synthetic words, "  # pushes the marker out of the preview
        letter = builders.docx_bytes(
            builders.para(builders.run(f"Account note {marker}"))
            + builders.para(builders.run(f"Mobile: 98765 43210, {filler}{marker}")),
            comments=[("Reviewer", f"See {marker}")],
        )
        # No header row: the extractor takes the first row of DATA as the header,
        # so "Rahul Verma" reaches the detectors as a column header.
        no_header = (b"Rahul Verma,rahul.verma@mailhost-synthetic.net,98765 43211\r\n"
                     b"Priya Sharma,priya.sharma@mailhost-synthetic.net,98765 43212\r\n")
        scan = self.queued([("letter.docx", letter), ("contacts.csv", no_header)])
        self.claim_and_process()
        # The test means something: letter.docx - the phone, the comment's author;
        # contacts.csv - two emails, two phones. (The names in the CSV have no label: not found.)
        self.assertEqual(Finding.objects.filter(scan=scan).count(), 6)

        # Cycle 7: reviewing writes to the audit log - a table that must stay clean too.
        for finding in Finding.objects.filter(scan=scan):
            self.client.patch(reverse("finding-detail", kwargs={"pk": finding.pk}),
                              {"review_status": "confirmed"}, format="json")
        self.assertEqual(AuditLog.objects.count(), 6)

        forbidden = [marker, "Rahul Verma", "rahul.verma", "priya.sharma", "98765 43210", "98765 43211", "98765 43212"]
        for row in [*Scan.objects.all(), *ScannedFile.objects.all(), *Finding.objects.all(), *AuditLog.objects.all()]:
            values = " ".join(str(v) for k, v in vars(row).items() if k != "_state")
            for text in forbidden:
                self.assertNotIn(text, values, f"{text!r} found in a {type(row).__name__} row")
        one_finding = reverse("finding-detail", kwargs={"pk": Finding.objects.filter(scan=scan).first().pk})
        for url in (self.url("scan-detail", scan), self.url("scan-files", scan), self.url("scan-findings", scan),
                    reverse("finding-list"), one_finding, reverse("dashboard")):
            body = self.client.get(url).content.decode()
            for text in forbidden:
                self.assertNotIn(text, body, f"{text!r} found in {url}")


STAFF_CSV = (
    b"Name,Mobile,Email\r\n"
    b"Ana Example,98765 43210,ana.example@mailhost-synthetic.net\r\n"
    b"Rahul Verma,98765 43211,ana.example@mailhost-synthetic.net\r\n"  # the same address again
)


class DetectionTests(WorkerTestBase):
    def test_findings_are_stored_masked_grouped_and_counted(self):
        scan = self.queued([("staff.csv", STAFF_CSV), ("notes.txt", b"synthetic notes\n")])
        self.claim_and_process()
        scan.refresh_from_db()

        findings = Finding.objects.filter(scan=scan)
        self.assertEqual(Counter(findings.values_list("subcategory", flat=True)),
                         {"person_name": 2, "phone_number": 2, "email_address": 1})
        self.assertEqual(scan.total_findings, 5)

        email = findings.get(subcategory="email_address")
        self.assertEqual((email.masked_value, email.occurrences), ("a***@mailhost-synthetic.net", 2))
        self.assertEqual(email.source_location, {"row": 2, "column": 3, "line": 2})  # no "header" (D-033)
        self.assertEqual(email.other_locations, [{"row": 3, "column": 3, "line": 3}])
        self.assertEqual((email.category, email.detection_method, email.confidence), ("personal", "pattern", 0.95))
        # Risk 23 = Low base 20 x confidence factor 0.98 (0.6 + 0.4 x 0.95) + 3 for appearing twice, rounded.
        self.assertEqual((email.review_status, email.severity, email.risk_score), ("new", "low", 23))
        self.assertTrue(email.severity_reason.startswith("Low. Email address:"))
        self.assertIn("BCC", email.remediation)
        self.assertEqual(email.detection_version, DETECTION_VERSION)
        self.assertEqual(scan.configuration["severity_policy_version"], SEVERITY_POLICY_VERSION)

        files = self.files(scan)
        self.assertEqual(files["staff.csv"].detection_stats["findings"], 5)
        self.assertEqual(files["notes.txt"].detection_stats["findings"], 0)  # searched, nothing found
        self.assertEqual(scan.configuration["detection_version"], DETECTION_VERSION)
        self.assertEqual(scan.configuration["phone_region"], "IN")
        self.assertIn("aadhaar", scan.configuration["detectors"])

    def test_the_scan_is_scored_from_its_riskiest_finding(self):
        scan = self.queued([("staff.csv", STAFF_CSV)])
        self.claim_and_process()
        scan.refresh_from_db()
        # Riskiest: a phone number, Medium base 45 x 0.98 = 44. No other finding reaches 60: no bonus.
        self.assertEqual(scan.risk_score, 44)
        self.assertEqual(scan.configuration["risk_policy_version"], RISK_POLICY_VERSION)
        risk = self.client.get(self.url("scan-detail", scan)).data["risk"]
        self.assertEqual((risk["score"], risk["band"], risk["band_label"]), (44, "high", "High"))
        self.assertEqual(risk["factors"], ["Riskiest finding: Phone number in staff.csv (44)"])
        self.assertIn("not proof that the files are safe or unsafe", risk["limitation"])  # FR-080
        # FR-077's bands travel with the score, so no page repeats the thresholds.
        self.assertEqual([(b["from"], b["band"]) for b in risk["bands"]],
                         [(70, "critical"), (40, "high"), (20, "moderate"), (0, "low")])
        listed, = self.client.get(reverse("scan-list")).data["results"]
        self.assertEqual((listed["risk_score"], listed["risk_band"]), (44, "high"))

    def test_an_unsearched_scan_has_no_risk_score(self):
        scan = self.queued([("report.pdf", b"%PDF-1.4 passes intake, but is not a real PDF")])
        self.claim_and_process()
        scan.refresh_from_db()
        self.assertIsNone(scan.risk_score)  # nothing was read: no score, never 0
        self.assertIsNone(self.client.get(self.url("scan-detail", scan)).data["risk"])

    def test_a_file_nobody_could_read_was_not_searched(self):
        scan = self.queued([("report.pdf", b"%PDF-1.4 passes intake, but is not a real PDF")])
        self.claim_and_process()
        scan.refresh_from_db()
        self.assertIsNone(scan.total_findings)  # not 0: nothing was read, so nothing was searched
        self.assertIsNone(self.files(scan)["report.pdf"].detection_stats)

    def test_an_internal_error_fails_only_that_file_with_a_fixed_message(self):
        queued = self.queued([("a.txt", b"Email: ana@mailhost-synthetic.net\n"), ("b.txt", b"synthetic b\n")])
        name_by_path = {f.stored_file.path: f.file_name for f in ScannedFile.objects.filter(scan=queued)}

        def buggy_on_b(job, keep_waiting):
            if name_by_path[job.path] == "b.txt":
                return Outcome(ERROR, EngineError("ValueError", "labelled.py:42"), 0.1)
            return in_process(job, keep_waiting)

        with self.assertLogs("apps.scans.worker", "ERROR"):
            scan, result = self.claim_and_process(buggy_on_b)
        self.assertEqual(result, S.PARTIALLY_COMPLETED)
        b = self.files(scan)["b.txt"]
        self.assertEqual((b.processing_status, b.detection_stats), (FS.FAILED, None))
        self.assertIn("internal error while searching this file (ValueError at labelled.py:42)", b.extraction_detail)
        scan.refresh_from_db()
        self.assertEqual(scan.total_findings, 1)  # a.txt's finding still counts

    def test_a_late_result_for_a_file_recovery_gave_up_on_is_dropped(self):
        scan = self.queued([("a.txt", b"Email: ana@mailhost-synthetic.net\n")])

        def recovered_meanwhile(job, keep_waiting):
            # While the child worked, recovery decided this worker had died (D-026).
            ScannedFile.objects.filter(scan=scan).update(processing_status=FS.FAILED, extraction_detail=worker.POISON)
            return in_process(job, keep_waiting)

        self.claim_and_process(recovered_meanwhile)
        self.assertFalse(Finding.objects.exists())
        self.assertEqual(self.files(scan)["a.txt"].extraction_detail, worker.POISON)

    def test_deleting_a_scan_deletes_its_findings(self):
        scan = self.queued([("a.txt", b"Email: ana@mailhost-synthetic.net\n")])
        self.claim_and_process()
        self.assertEqual(Finding.objects.count(), 1)
        services.delete_scan(Scan.objects.get(pk=scan.pk))
        self.assertFalse(Finding.objects.exists())


class CancellationTests(WorkerTestBase):
    def test_cancelling_mid_scan_stops_and_leaves_unprocessed_files_pending(self):
        scan = self.queued([("a.txt", b"synthetic a\n"), ("b.txt", b"synthetic b\n")])

        def user_cancels_during_first_file(job, keep_waiting):
            services.transition(Scan.objects.get(pk=scan.pk), "cancel")
            return Outcome(CANCELLED, None, 0.5)  # what the supervisor returns once keep_waiting says stop

        claimed = worker.claim_next_scan()
        self.assertEqual(worker.process_scan(claimed, user_cancels_during_first_file), "cancelled")
        statuses = {f.file_name: f.processing_status for f in ScannedFile.objects.filter(scan=scan)}
        self.assertEqual(statuses, {"a.txt": FS.PENDING, "b.txt": FS.PENDING})  # nothing half-done
        self.assertEqual(Scan.objects.get(pk=scan.pk).status, S.CANCELLED)

    def test_keep_waiting_turns_false_once_the_scan_is_cancelled(self):
        self.queued([("a.txt", b"synthetic\n")])
        scan = worker.claim_next_scan()
        pulse = worker._Pulse(scan.pk, None)
        pulse.last_check -= 5
        self.assertTrue(pulse.keep_waiting())
        services.transition(Scan.objects.get(pk=scan.pk), "cancel")
        pulse.last_check -= 5
        self.assertFalse(pulse.keep_waiting())

    def test_a_cancel_during_the_last_file_is_honoured(self):
        scan = self.queued([("a.txt", b"synthetic\n")])

        def cancel_then_finish(job, keep_waiting):
            services.transition(Scan.objects.get(pk=scan.pk), "cancel")
            return in_process(job, keep_waiting)  # the file itself still completes

        claimed = worker.claim_next_scan()
        self.assertEqual(worker.process_scan(claimed, cancel_then_finish), "cancelled")
        self.assertEqual(Scan.objects.get(pk=scan.pk).status, S.CANCELLED)

    def test_finishing_never_overwrites_a_cancel(self):
        # The real race window: every file is done, and the user cancels in the
        # instant before the final status is written. The loop's own status
        # check has already passed, so only the compare-and-swap in _finish
        # stands between "cancelled" and being overwritten by "completed".
        self.queued([("a.txt", b"synthetic\n")])
        scan, _ = self.claim_and_process()
        Scan.objects.filter(pk=scan.pk).update(status=S.PROCESSING)  # rewind to just before the final write
        services.transition(Scan.objects.get(pk=scan.pk), "cancel")   # ...and cancel in that instant

        self.assertEqual(worker._finish(scan), "cancelled")
        self.assertEqual(Scan.objects.get(pk=scan.pk).status, S.CANCELLED)


class RecoveryTests(WorkerTestBase):
    def test_a_stale_scan_is_requeued_and_its_poison_file_failed(self):
        scan = self.queued([("a.txt", b"synthetic a\n"), ("b.txt", b"synthetic b\n")])
        worker.claim_next_scan()
        ScannedFile.objects.filter(scan=scan, file_name="a.txt").update(processing_status=FS.PROCESSING)
        Scan.objects.filter(pk=scan.pk).update(heartbeat_at=timezone.now() - timedelta(minutes=10))

        with self.assertLogs("apps.scans.worker", "WARNING") as logs:  # recovery must be visible
            self.assertEqual(worker.recover_stale_scans(), 1)
        self.assertIn(str(scan.pk), logs.output[0])
        self.assertEqual(Scan.objects.get(pk=scan.pk).status, S.QUEUED)
        poisoned = ScannedFile.objects.get(scan=scan, file_name="a.txt")
        self.assertEqual((poisoned.processing_status, poisoned.extraction_detail), (FS.FAILED, worker.POISON))

        _, result = self.claim_and_process()  # resumes with the rest
        self.assertEqual(result, S.PARTIALLY_COMPLETED)
        self.assertEqual(ScannedFile.objects.get(scan=scan, file_name="b.txt").extraction_status, E.SUCCEEDED)

    def test_a_scan_with_a_fresh_heartbeat_is_left_alone(self):
        self.queued([("a.txt", b"synthetic\n")])
        scan = worker.claim_next_scan()
        self.assertEqual(worker.recover_stale_scans(), 0)
        self.assertEqual(Scan.objects.get(pk=scan.pk).status, S.PROCESSING)


class RunWorkerTests(WorkerTestBase):
    def test_once_empties_the_queue_using_the_real_isolated_child(self):
        first = self.queued([("a.txt", b"Email: ana@mailhost-synthetic.net\n")])
        second = self.queued([("report.pdf", builders.pdf_bytes(["Synthetic"]))])
        messages = []
        self.assertEqual(worker.run_worker(once=True, log=messages.append), 2)
        for scan in (first, second):
            self.assertEqual(Scan.objects.get(pk=scan.pk).status, S.COMPLETED)
        self.assertFalse(WorkerHeartbeat.objects.exists())  # removed on a clean stop
        self.assertTrue(any("extracting 1 file" in m for m in messages))
        # Detection really ran in the spawned child, and its JSON reply was accepted.
        finding = Finding.objects.get(scan=first)
        self.assertEqual(finding.masked_value, "a***@mailhost-synthetic.net")
        self.assertEqual(Scan.objects.get(pk=second.pk).total_findings, 0)
        self.assertTrue(any("1 finding(s)" in m for m in messages))

    def test_ctrl_c_puts_the_scan_back_in_the_queue(self):
        scan = self.queued([("a.txt", b"synthetic\n")])

        def interrupted(job, keep_waiting):
            raise KeyboardInterrupt

        messages = []
        worker.run_worker(once=True, log=messages.append, run_job=interrupted)
        self.assertEqual(Scan.objects.get(pk=scan.pk).status, S.QUEUED)
        self.assertEqual(ScannedFile.objects.get(scan=scan).processing_status, FS.PENDING)  # no penalty
        self.assertTrue(any("went back to the queue" in m for m in messages))

    def test_the_worker_is_visible_while_it_runs(self):
        self.queued([("a.txt", b"synthetic\n")])
        seen = {}

        def look(job, keep_waiting):
            seen["workers"] = WorkerHeartbeat.objects.count()
            return in_process(job, keep_waiting)

        worker.run_worker(once=True, log=lambda m: None, run_job=look)
        self.assertEqual(seen["workers"], 1)


class HealthAndApiTests(WorkerTestBase):
    def test_no_worker_means_degraded_health(self):
        health = collect_health()
        self.assertEqual(health["components"]["worker"]["status"], "error")
        self.assertEqual(health["status"], "degraded")

    def test_a_recent_heartbeat_means_the_worker_is_running(self):
        now = timezone.now()
        WorkerHeartbeat.objects.create(name="test:1", started_at=now, last_seen=now)
        health = collect_health()
        self.assertEqual(health["components"]["worker"]["status"], "ok")
        self.assertEqual(health["status"], "ok")

    def test_scan_detail_and_inventory_report_extraction_results(self):
        scan = self.queued([("notes.txt", b"synthetic\n"), ("report.pdf", builders.pdf_bytes(["One", ""]))])
        self.claim_and_process()

        detail = self.client.get(self.url("scan-detail", scan)).data
        self.assertEqual(detail["progress"], {"done": 2, "total": 2})
        self.assertEqual(detail["extraction_counts"]["succeeded"], 1)
        self.assertEqual(detail["extraction_counts"]["partial"], 1)
        self.assertEqual(detail["total_findings"], 0)  # searched, nothing personal in these files

        rows = self.inventory(scan.pk)
        self.assertEqual(rows["report.pdf"]["extraction_status_display"], "Partially succeeded")
        self.assertIn("pages", rows["report.pdf"]["extraction_stats"])
        self.assertIn("scanned", rows["report.pdf"]["extraction_detail"])

        self.assertEqual(self.client.get(reverse("dashboard")).data["files_processed"], 2)


class FindingsApiTests(WorkerTestBase):
    def setUp(self):
        super().setUp()
        self.scan = self.queued([("staff.csv", STAFF_CSV), ("notes.txt", b"synthetic notes\n")])
        self.claim_and_process()

    def test_findings_are_listed_most_serious_first_with_masked_values(self):
        response = self.client.get(self.url("scan-findings", self.scan))
        self.assertEqual(response.status_code, 200)
        rows = response.data["results"]
        self.assertEqual(response.data["count"], 5)
        self.assertEqual([row["severity"] for row in rows], ["medium", "medium", "low", "low", "low"])  # phones first

        email = next(row for row in rows if row["subcategory"] == "email_address")
        self.assertEqual(email["subcategory_display"], "Email address")
        self.assertEqual(email["masked_value"], "a***@mailhost-synthetic.net")
        self.assertEqual(email["file_path"], "staff.csv")
        self.assertEqual(email["occurrences"], 2)
        self.assertEqual(email["review_status_display"], "New")
        self.assertEqual(email["severity_display"], "Low")
        self.assertIn("Email address", email["severity_reason"])

    def test_findings_can_be_sorted_four_ways(self):
        def rows(ordering):
            return self.client.get(self.url("scan-findings", self.scan) + f"?ordering={ordering}").data["results"]

        confidences = [row["confidence"] for row in rows("confidence")]
        self.assertEqual(confidences, sorted(confidences, reverse=True))
        self.assertEqual([row["category"] for row in rows("category")], ["personal"] * 5)
        self.assertEqual([row["file_path"] for row in rows("file")], ["staff.csv"] * 5)
        refused = self.client.get(self.url("scan-findings", self.scan) + "?ordering=severity;DROP")
        self.assertEqual(refused.status_code, 400)

    def test_scan_detail_counts_findings_by_severity(self):
        counts = self.client.get(self.url("scan-detail", self.scan)).data["severity_counts"]
        self.assertEqual(counts, {"critical": 0, "high": 0, "medium": 2, "low": 3, "informational": 0,
                                  "not_assessed": 0})

    def test_findings_found_before_severity_existed_are_not_assessed_and_sort_last(self):
        Finding.objects.filter(scan=self.scan, subcategory="phone_number").update(severity=None, severity_reason="")
        self.assertEqual(self.client.get(self.url("scan-detail", self.scan)).data["severity_counts"]["not_assessed"], 2)
        rows = self.client.get(self.url("scan-findings", self.scan)).data["results"]
        self.assertEqual([row["severity"] for row in rows][-2:], [None, None])

    def test_the_dashboard_counts_critical_and_high_findings(self):
        self.assertEqual(self.client.get(reverse("dashboard")).data["critical_high_findings"], 0)  # looked: none
        self.queued([("app.env", f"DB_PASSWORD={secret_fixtures.rand(16)}\n".encode())])
        self.claim_and_process()
        self.assertEqual(self.client.get(reverse("dashboard")).data["critical_high_findings"], 1)  # a password: high

    def test_scan_detail_counts_findings_by_type(self):
        detail = self.client.get(self.url("scan-detail", self.scan)).data
        self.assertEqual(detail["total_findings"], 5)
        self.assertEqual(detail["finding_counts"], [
            {"type": "person_name", "label": "Person's name", "count": 2},
            {"type": "phone_number", "label": "Phone number", "count": 2},
            {"type": "email_address", "label": "Email address", "count": 1},
        ])
        self.assertEqual(self.inventory(self.scan.pk)["staff.csv"]["detection_stats"]["findings"], 5)

    def test_findings_are_paginated(self):
        response = self.client.get(self.url("scan-findings", self.scan) + "?page_size=2")
        self.assertEqual((len(response.data["results"]), response.data["count"]), (2, 5))
        self.assertIsNotNone(response.data["next"])

    def test_the_dashboard_adds_up_searched_scans_only(self):
        self.make_scan()  # a draft: never searched, so it adds nothing - not even a 0
        self.assertEqual(self.client.get(reverse("dashboard")).data["total_findings"], 5)

    def test_signed_out_requests_are_refused(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url("scan-findings", self.scan)).status_code, 403)
