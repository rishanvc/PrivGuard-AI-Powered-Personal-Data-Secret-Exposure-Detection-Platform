"""The extraction supervisor: real child processes, real timeouts, real crashes.

Runs without Django. Each test starts at least one Python process, so this
file takes a few seconds. The misbehaving child functions below must live at
module level: "spawn" starts a fresh interpreter, which imports them by name.
"""

import os
import shutil
import sys
import tempfile
import time
import unittest
from unittest import mock

from privguard_engine.detectors import DetectionConfig, Finding
from privguard_engine.extractors import ExtractionResult, ExtractionStatus, Limits
from privguard_engine.isolation import (
    CANCELLED, CRASHED, DONE, ERROR, MAX_FINDINGS_PER_FILE, TIMEOUT, ExtractionSupervisor, Job, JobResult,
    ProtocolError, child_main, decode_reply, encode_reply,
)


def report(connection, *notes):
    """Answer in the real reply protocol, carrying observations as extraction notes."""
    connection.send_bytes(encode_reply(JobResult(ExtractionResult(ExtractionStatus.SUCCEEDED, notes=list(notes)))))


def hanging_child(connection):
    """Accepts a job and never answers - a parser stuck in an endless loop."""
    connection.recv()
    while True:
        time.sleep(1)


def crashing_child(connection):
    """Accepts a job and dies abruptly, like a segfault in C code."""
    connection.recv()
    os._exit(3)


def probe_child(connection):
    """Reports what the child process has imported."""
    while (job := connection.recv()) is not None:
        report(connection, f"django={'django' in sys.modules}",
               f"engine={'privguard_engine.extractors' in sys.modules}")


def environment_probe_child(connection):
    """Reports which test variables, and which real PrivGuard secrets, the child can see.
    Names only - never values."""
    while (job := connection.recv()) is not None:
        visible = sorted(k for k in os.environ if k.startswith("PRIVGUARD_TEST_"))
        visible += sorted(k for k in ("DATABASE_URL", "DJANGO_SECRET_KEY") if k in os.environ)
        report(connection, *visible)


def broken_detector_child(connection):
    """The real child, with one extra detector that has a bug - and quotes the text in its message."""
    from privguard_engine import detectors

    def broken(text, location, config):
        raise ValueError(f"cannot handle {text!r}")

    detectors.DETECTORS["broken"] = broken
    child_main(connection)


def pickling_child(connection):
    """Replies with a pickle - what a child taken over by a hostile file might send."""
    connection.recv()
    connection.send({"looks": "harmless"})
    while True:
        time.sleep(1)


class SupervisorTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="privguard-isolation-")
        self.addCleanup(shutil.rmtree, self.folder, True)
        self.path = os.path.join(self.folder, "stored")
        with open(self.path, "wb") as handle:
            handle.write(b"synthetic line one\nsynthetic line two\n")
        self.job = Job(self.path, "text", Limits())

    def test_a_job_runs_in_the_child_and_the_child_is_reused(self):
        with ExtractionSupervisor(timeout=60) as supervisor:
            first = supervisor.run(self.job)
            child = supervisor._process.pid
            second = supervisor.run(self.job)
            self.assertEqual(supervisor._process.pid, child)  # no new process per file
        self.assertEqual((first.kind, second.kind), (DONE, DONE))
        self.assertEqual(first.result.extraction.status, ExtractionStatus.SUCCEEDED)
        self.assertEqual(first.result.extraction.stats["segments"], 2)
        self.assertIsNone(first.result.detection)  # no DetectionConfig: nothing searched
        self.assertNotEqual(child, os.getpid())  # it really ran elsewhere

    def test_the_real_child_does_not_import_django(self):
        with ExtractionSupervisor(timeout=60, target=probe_child) as supervisor:
            outcome = supervisor.run(self.job)
        self.assertEqual(outcome.kind, DONE)
        self.assertEqual(outcome.result.extraction.notes, ["django=False", "engine=True"])

    def test_detection_runs_in_the_child_and_only_masked_findings_come_back(self):
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write("Name: Rahul Verma\nMobile: 98765 43210\n")
        with ExtractionSupervisor(timeout=60) as supervisor:
            outcome = supervisor.run(Job(self.path, "text", Limits(), DetectionConfig()))
        self.assertEqual(outcome.kind, DONE)
        self.assertEqual(sorted(f.masked_value for f in outcome.result.findings), ["***** ***10", "R**** V****"])
        self.assertEqual(outcome.result.detection["findings"], 2)
        for raw in ("Rahul", "Verma", "98765"):
            self.assertNotIn(raw, repr(outcome))

    def test_a_bug_in_detection_is_reported_as_ours_and_the_child_survives(self):
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write("SYNTHETIC-SECRET-TEXT\n")
        job = Job(self.path, "text", Limits(), DetectionConfig())
        with ExtractionSupervisor(timeout=60, target=broken_detector_child) as supervisor:
            outcome = supervisor.run(job)
            child = supervisor._process.pid
            self.assertEqual(supervisor.run(job).kind, ERROR)
            self.assertEqual(supervisor._process.pid, child)  # not killed: it wasn't the file's fault
        self.assertEqual(outcome.kind, ERROR)
        self.assertEqual(outcome.result.kind, "ValueError")
        self.assertTrue(outcome.result.where.startswith("test_isolation.py:"))
        self.assertNotIn("SYNTHETIC-SECRET-TEXT", repr(outcome))  # the message never crosses over

    def test_a_reply_that_is_not_json_is_refused_and_the_child_replaced(self):
        with ExtractionSupervisor(timeout=60, target=pickling_child) as supervisor:
            with self.assertLogs("privguard_engine.isolation", "WARNING"):
                outcome = supervisor.run(self.job)
            self.assertIsNone(supervisor._process)  # killed: it may have been taken over
        self.assertEqual(outcome.kind, CRASHED)

    def test_secrets_in_the_environment_never_reach_the_child(self):
        # Synthetic stand-ins for what .env puts into the worker's environment.
        planted = {
            "PRIVGUARD_TEST_SECRET_KEY": "synthetic-not-a-secret",
            "PRIVGUARD_TEST_DATABASE_URL": "postgres://user:synthetic@localhost/db",
            "PRIVGUARD_TEST_API_TOKEN": "synthetic",
            "PRIVGUARD_TEST_HARMLESS_SETTING": "1",
        }
        with mock.patch.dict(os.environ, planted):
            with ExtractionSupervisor(timeout=60, target=environment_probe_child) as supervisor:
                outcome = supervisor.run(self.job)
        # Only the harmless one survives - and, when this runs under Django
        # (whose settings load .env), neither real secret appears either.
        self.assertEqual(outcome.result.extraction.notes, ["PRIVGUARD_TEST_HARMLESS_SETTING"])

    def test_a_hanging_child_is_killed_at_the_timeout_and_replaced(self):
        with ExtractionSupervisor(timeout=1.5, target=hanging_child) as supervisor:
            start = time.monotonic()
            outcome = supervisor.run(self.job)
            took = time.monotonic() - start
            self.assertEqual(outcome.kind, TIMEOUT)
            self.assertLess(took, 10)  # the timeout, not "forever"
            self.assertIsNone(supervisor._process)  # killed; a fresh one starts next time

    def test_a_crashing_child_is_reported_and_replaced(self):
        with ExtractionSupervisor(timeout=60, target=crashing_child) as supervisor:
            self.assertEqual(supervisor.run(self.job).kind, CRASHED)
            self.assertEqual(supervisor.run(self.job).kind, CRASHED)  # a new child each time

    def test_on_wait_returning_false_cancels_the_job(self):
        calls = {"n": 0}

        def stop_after_a_few_polls():
            calls["n"] += 1
            return calls["n"] < 3

        with ExtractionSupervisor(timeout=60, target=hanging_child, poll_interval=0.1) as supervisor:
            outcome = supervisor.run(self.job, on_wait=stop_after_a_few_polls)
        self.assertEqual(outcome.kind, CANCELLED)

    def test_close_stops_the_child(self):
        supervisor = ExtractionSupervisor(timeout=60)
        supervisor.run(self.job)
        process = supervisor._process
        supervisor.close()
        self.assertFalse(process.is_alive())


def a_finding(**changes):
    fields = dict(category="personal", type="email_address", method="pattern", confidence=0.9,
                  masked_value="a***@mailhost-synthetic.net", context="Email: a***@mailhost-synthetic.net",
                  location={"line": 1}, more_locations=({"line": 2},), occurrences=2,
                  explanation="Matches the structure of an email address.")
    return Finding(**{**fields, **changes})


def a_reply(*findings):
    return JobResult(ExtractionResult(ExtractionStatus.SUCCEEDED, stats={"segments": 2}), findings,
                     {"detections": 2, "findings": len(findings), "by_type": {"email_address": 1}, "truncated": False})


class ReplyProtocolTests(unittest.TestCase):
    """The parent trusts nothing the child sends: every field is checked."""

    def test_a_genuine_reply_survives_the_round_trip(self):
        reply = a_reply(a_finding())
        self.assertEqual(decode_reply(encode_reply(reply)), reply)

    def test_hostile_replies_are_refused(self):
        hostile = {
            "a pickle": b"\x80\x04\x95\x05\x00\x00\x00\x00\x00\x00\x00N.",
            "deep nesting": b"[" * 100_000,
            "unknown finding type": encode_reply(a_reply(a_finding(type="something_else"))),
            "unknown category": encode_reply(a_reply(a_finding(category="secret"))),
            "confidence above 1": encode_reply(a_reply(a_finding(confidence=7.5))),
            "zero occurrences": encode_reply(a_reply(a_finding(occurrences=0))),
            "an enormous preview": encode_reply(a_reply(a_finding(context="x" * 5_000))),
            "a header in a location": encode_reply(a_reply(a_finding(location={"header": "Rahul Verma"}))),
            "too many findings": encode_reply(a_reply(*[a_finding()] * (MAX_FINDINGS_PER_FILE + 1))),
            "an unknown status": encode_reply(a_reply()).replace(b'"succeeded"', b'"pwned"'),
        }
        for name, data in hostile.items():
            with self.subTest(name), self.assertRaises(ProtocolError):
                decode_reply(data)


if __name__ == "__main__":
    unittest.main()
