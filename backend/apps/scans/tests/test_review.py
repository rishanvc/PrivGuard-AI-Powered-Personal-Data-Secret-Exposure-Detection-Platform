"""Reviewing, searching and filtering findings (FR-079, FR-081, FR-083 to FR-088, UC-03). Cycle 7.

Alice has two scans: a staff list (2 names, 2 phones, 1 email) and an .env
file with a password. Bob has his own staff list. Every value is synthetic.
"""

from django.urls import reverse
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.scans.models import Finding, Scan
from tests.engine import secret_fixtures

from .test_worker import STAFF_CSV, WorkerTestBase


class ReviewTestBase(WorkerTestBase):
    def setUp(self):
        super().setUp()
        self.staff = self.queued([("staff.csv", STAFF_CSV)])
        self.secrets = self.queued([("app.env", f"DB_PASSWORD={secret_fixtures.rand(16)}\n".encode())])
        self.bobs = self.queued([("staff.csv", STAFF_CSV)], user=self.bob)
        for _ in range(3):
            self.claim_and_process()
        self.password = Finding.objects.get(scan=self.secrets)

    def findings(self, query="", client=None):
        response = (client or self.client).get(reverse("finding-list") + query)
        return response

    def detail_url(self, finding):
        return reverse("finding-detail", kwargs={"pk": finding.pk})

    def review(self, finding, status, client=None):
        return (client or self.client).patch(self.detail_url(finding), {"review_status": status}, format="json")


class FindingListTests(ReviewTestBase):
    def test_lists_only_your_own_findings_across_your_scans(self):
        data = self.findings().data
        self.assertEqual(data["count"], 6)
        self.assertEqual({row["scan_id"] for row in data["results"]}, {self.staff.pk, self.secrets.pk})

    def test_each_fr_087_filter(self):
        expected = {
            "?severity=high": 1,                       # the password
            "?severity=medium,high": 3,                # ...and the two phone numbers
            "?category=secret": 1,
            "?file_type=env": 1,
            "?method=context": 3,                      # two names (column header) and the password (setting name)
            "?status=new": 6,
            f"?scan={self.staff.pk}": 5,
            f"?scan={self.staff.pk}&severity=low": 3,  # filters combine
        }
        for query, count in expected.items():
            with self.subTest(query=query):
                self.assertEqual(self.findings(query).data["count"], count)

    def test_search_covers_paths_kinds_and_masked_values(self):
        for query, count in {"?q=staff": 5, "?q=Phone": 2, "?q=a***@": 1, "?q=nothing-matches": 0}.items():
            with self.subTest(query=query):
                self.assertEqual(self.findings(query).data["count"], count)

    def test_another_users_scan_simply_matches_nothing(self):
        self.assertEqual(self.findings(f"?scan={self.bobs.pk}").data["count"], 0)  # not a 404: nothing revealed

    def test_unknown_values_are_explained_not_ignored(self):
        for query, field in {"?severity=urgent": "severity", "?scan=not-a-uuid": "scan",
                             "?ordering=random": "ordering", "?q=" + "x" * 101: "q"}.items():
            with self.subTest(query=query[:30]):
                response = self.findings(query)
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.data)

    def test_sorting_by_risk(self):
        risks = [row["risk_score"] for row in self.findings("?ordering=risk").data["results"]]
        self.assertEqual(risks, sorted(risks, reverse=True))

    def test_the_scan_findings_tab_takes_the_same_filters(self):
        url = self.url("scan-findings", self.staff)
        self.assertEqual(self.client.get(url + "?severity=medium").data["count"], 2)


class FindingDetailTests(ReviewTestBase):
    def test_everything_about_one_finding(self):
        data = self.client.get(self.detail_url(self.password)).data
        self.assertEqual((data["subcategory"], data["severity"], data["file_type"]), ("password", "high", "env"))
        self.assertEqual((data["risk_score"], data["risk_band"]), (66, "high"))  # 70 x 0.94, in the 40-69 band
        self.assertEqual(data["scan_name"], self.secrets.name)
        self.assertIn("Change the password", data["remediation"])  # FR-084
        self.assertEqual((data["review_status"], data["reviewed_by"], data["history"]), ("new", None, []))

    def test_only_the_owner_can_see_it(self):
        self.client.force_login(self.bob)
        self.assertEqual(self.client.get(self.detail_url(self.password)).status_code, 404)
        self.client.force_login(self.ada)  # administrators get no bypass (D-009)
        self.assertEqual(self.client.get(self.detail_url(self.password)).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(self.detail_url(self.password)).status_code, 403)

    def test_findings_cannot_be_created_or_deleted_through_the_api(self):
        self.assertEqual(self.client.post(reverse("finding-list"), {}).status_code, 405)
        self.assertEqual(self.client.delete(self.detail_url(self.password)).status_code, 405)


class ReviewTests(ReviewTestBase):
    def test_a_review_is_saved_and_recorded(self):
        response = self.review(self.password, "false_positive")
        self.assertEqual(response.status_code, 200)
        self.assertEqual((response.data["review_status"], response.data["reviewed_by"]), ("false_positive", "alice"))
        self.assertIsNotNone(response.data["reviewed_at"])

        entry = AuditLog.objects.get()
        self.assertEqual((entry.user, entry.action, entry.resource_type, entry.resource_id),
                         (self.alice, "finding.review", "finding", str(self.password.pk)))
        # FR-117: IDs, the kind of finding and the statuses - nothing about the value.
        self.assertEqual(entry.safe_metadata, {"scan_id": str(self.secrets.pk), "finding_type": "password",
                                               "from_status": "new", "to_status": "false_positive"})
        history = self.client.get(self.detail_url(self.password)).data["history"]
        self.assertEqual([(h["from_status"], h["to_status"], h["by"]) for h in history],
                         [("new", "false_positive", "alice")])

    def test_a_review_that_changes_nothing_records_nothing(self):
        self.review(self.password, "new")
        self.assertFalse(AuditLog.objects.exists())

    def test_only_the_review_status_can_change(self):
        for body in ({"review_status": "ignored"}, {"review_status": "confirmed", "severity": "low"}, {}):
            with self.subTest(body=body):
                response = self.client.patch(self.detail_url(self.password), body, format="json")
                self.assertEqual(response.status_code, 400)
        self.password.refresh_from_db()
        self.assertEqual((self.password.review_status, self.password.severity), ("new", "high"))
        self.assertFalse(AuditLog.objects.exists())

    def test_nobody_else_can_review_it(self):
        for user in (self.bob, self.ada):
            self.client.force_login(user)
            self.assertEqual(self.review(self.password, "resolved").status_code, 404)
        self.password.refresh_from_db()
        self.assertEqual(self.password.review_status, "new")
        self.assertFalse(AuditLog.objects.exists())

    def test_a_review_needs_the_csrf_token(self):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.alice)
        self.assertEqual(self.review(self.password, "resolved", client=client).status_code, 403)

    def test_reviews_move_the_scan_score(self):
        # The password alone: High base 70 x (0.6 + 0.4 x 0.85) = 65.8 -> 66.
        self.assertEqual(Scan.objects.get(pk=self.secrets.pk).risk_score, 66)
        self.review(self.password, "false_positive")
        risk = self.client.get(self.url("scan-detail", self.secrets)).data["risk"]
        self.assertEqual((risk["score"], risk["band"]), (0, "low"))
        self.assertIn("1 finding(s) not counted: reviewed as false positive or resolved", risk["factors"])
        # The detail recalculates live, but the scan list and the dashboard read the STORED score:
        # both must move too (a mutation check caught this test missing a stale stored score).
        self.assertEqual(Scan.objects.get(pk=self.secrets.pk).risk_score, 0)
        listed = {row["id"]: row for row in self.client.get(reverse("scan-list")).data["results"]}
        self.assertEqual(listed[str(self.secrets.pk)]["risk_score"], 0)  # the API sends IDs as text
        self.review(self.password, "accepted_risk")  # accepted risk is still risk
        self.assertEqual(Scan.objects.get(pk=self.secrets.pk).risk_score, 66)


class DashboardStatisticsTests(ReviewTestBase):
    def test_fr_081_statistics(self):
        data = self.client.get(reverse("dashboard")).data
        self.assertEqual(data["critical_high_findings"], 1)
        self.assertEqual(data["severity_counts"], {"critical": 0, "high": 1, "medium": 2, "low": 3, "informational": 0,
                                                   "not_assessed": 0})
        self.assertEqual(data["category_counts"], {"personal": 5, "secret": 1, "financial": 0})
        self.assertEqual(data["review_counts"]["new"], 6)
        self.assertEqual([scan["id"] for scan in data["riskiest_scans"]], [self.secrets.pk, self.staff.pk])

    def test_reviewed_away_findings_leave_the_open_counts(self):
        self.review(self.password, "false_positive")
        data = self.client.get(reverse("dashboard")).data
        self.assertEqual(data["critical_high_findings"], 0)
        self.assertEqual(data["category_counts"]["secret"], 0)
        self.assertEqual((data["review_counts"]["new"], data["review_counts"]["false_positive"]), (5, 1))
