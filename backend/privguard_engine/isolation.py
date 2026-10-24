"""Run extraction in a separate process that can be killed (NFR-003, NFR-009, SRS 15).

Python cannot stop a thread that is stuck inside C code - PDFium, for
instance - so the only reliable way to put a time limit on parsing a hostile
file is to parse it in a child process and kill that process if it takes too
long. A crash inside the parser (say, a segfault in C) also takes down only
the child.

The child imports privguard_engine and nothing else - no Django, no database
connection (D-002) - so it starts quickly and stays small. One child is reused
file after file and replaced only after a timeout or a crash, because starting
a Python process costs about half a second on Windows.

Detection runs in the child too (Cycle 5): raw values found in a file never
leave it. Only masked Findings come back.
"""

from __future__ import annotations

import json
import logging
import math
import multiprocessing
import os
import re
import signal
import time
import traceback
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace

from .detectors import TYPE_LABELS, DetectionConfig, Finding, FindingCollector
from .detectors.base import CATEGORY_OF, CHECKSUM, CONTEXT, ENTROPY, PATTERN, VALIDATED
from .detectors.collector import STORED_LOCATION_KEYS
from .extractors import ExtractionResult, ExtractionStatus, Limits, extract_file

logger = logging.getLogger(__name__)

DONE, TIMEOUT, CRASHED, CANCELLED, ERROR = "done", "timeout", "crashed", "cancelled", "error"

# Replies travel child -> parent as JSON, never pickle. Unpickling can run any
# code the data names, so a child taken over by a hostile file could take over
# the worker - which holds the database credentials - through its reply. JSON
# can only produce plain data, and decode_reply() checks every field.
MAX_REPLY_BYTES = 64 * 1024 * 1024
MAX_FINDINGS_PER_FILE = 5_000

# A child inherits its parent's environment - and under Django that includes
# DATABASE_URL and DJANGO_SECRET_KEY, loaded from .env into os.environ. The
# child parses hostile files; if a parser bug ever let a file run code, these
# would be the first thing worth stealing. So they are removed before any
# parsing starts.
_SECRET_NAMES = re.compile(r"SECRET|PASSWORD|PASSWD|TOKEN|CREDENTIAL|PRIVATE_KEY|API_KEY|DATABASE_URL", re.IGNORECASE)


def scrub_environment() -> list[str]:
    """Remove secret-looking variables from this process's environment; return their names."""
    removed = [name for name in os.environ if _SECRET_NAMES.search(name)]
    for name in removed:
        del os.environ[name]
    return removed


def _child_entry(connection, target) -> None:
    """Every child starts here, whatever its target: secrets go before parsing begins."""
    scrub_environment()
    target(connection)


@dataclass(frozen=True)
class Job:
    path: str
    file_type: str
    limits: Limits
    detection: DetectionConfig | None = None  # None: extract only, search nothing


@dataclass(frozen=True)
class JobResult:
    extraction: ExtractionResult
    findings: tuple[Finding, ...] = ()
    detection: dict | None = None  # FindingCollector.stats(); None when nothing searched


@dataclass(frozen=True)
class EngineError:
    """A bug in PrivGuard's own code while handling a file - not a problem WITH the file.

    Only the exception's type and the line it came from cross over: its
    message could quote the file's content.
    """

    kind: str   # "ValueError"
    where: str  # "labelled.py:182"


@dataclass(frozen=True)
class Outcome:
    kind: str                                 # DONE, ERROR, TIMEOUT, CRASHED or CANCELLED
    result: JobResult | EngineError | None    # JobResult for DONE, EngineError for ERROR
    seconds: float


# ---------------------------------------------------------------- the child

def perform(job: Job) -> JobResult:
    """One job, start to finish. Raw values exist only inside this function's collector."""
    if job.detection is None:
        return JobResult(extract_file(job.path, job.file_type, limits=job.limits))
    config = replace(job.detection, file_type=job.file_type)  # rules differ for .env, config and code
    collector = FindingCollector(config, max_findings=MAX_FINDINGS_PER_FILE)
    extraction = extract_file(job.path, job.file_type, limits=job.limits, sink=collector)
    return JobResult(extraction, tuple(collector.findings()), collector.stats())


def _where(exc: BaseException) -> str:
    frames = traceback.extract_tb(exc.__traceback__)
    return f"{os.path.basename(frames[-1].filename)}:{frames[-1].lineno}" if frames else "unknown"


def child_main(connection) -> None:
    """Runs in the child process: take a job, send back its result, repeat."""
    # Ctrl+C is delivered to every process attached to the terminal. The child
    # ignores it so the PARENT decides what happens to the file in progress -
    # otherwise the parent could mistake the child's exit for a crash and
    # wrongly mark the file as failed.
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    while True:
        try:
            job = connection.recv()  # from the trusted parent, so pickle is fine this way round
        except (EOFError, OSError):
            return  # the parent has gone
        if job is None:
            return  # orderly shutdown
        try:
            reply = perform(job)
        except Exception as exc:  # a bug in a detector, say: report it and stay alive
            reply = EngineError(type(exc).__name__, _where(exc))
        connection.send_bytes(encode_reply(reply))


# ---------------------------------------------------------------- the reply

def encode_reply(reply: JobResult | EngineError) -> bytes:
    if isinstance(reply, EngineError):
        payload = {"error": asdict(reply)}
    else:
        payload = {
            "extraction": reply.extraction.to_dict(),
            "findings": [asdict(finding) for finding in reply.findings],
            "detection": reply.detection,
        }
    return json.dumps(payload).encode()


class ProtocolError(Exception):
    """A reply no genuine child would send."""


_METHODS = frozenset({PATTERN, VALIDATED, CHECKSUM, CONTEXT, ENTROPY})


def _check(condition: bool) -> None:
    if not condition:
        raise ProtocolError


def _text(value, limit: int) -> str:
    _check(isinstance(value, str) and len(value) <= limit)
    return value


def _count(value) -> int:
    _check(type(value) is int and 0 <= value <= 10**12)
    return value


def _scalars(value, keys=None) -> dict:
    """A small, flat dict of short scalars: extraction stats, or a location."""
    _check(isinstance(value, dict) and len(value) <= 50)
    for key, item in value.items():
        _check(len(key) <= 50 and (keys is None or key in keys))
        _check(item is None or type(item) in (bool, int) or (type(item) is float and math.isfinite(item))
               or (isinstance(item, str) and len(item) <= 300))
    return value


def _extraction(value) -> ExtractionResult:
    _check(isinstance(value, dict))
    notes = value.get("notes")
    _check(isinstance(notes, list) and len(notes) <= 50)
    try:
        status = ExtractionStatus(value.get("status"))
    except ValueError:
        raise ProtocolError from None
    return ExtractionResult(status, _text(value.get("reason"), 5_000), _scalars(value.get("stats")),
                            [_text(note, 1_000) for note in notes])


def _finding(value) -> Finding:
    _check(isinstance(value, dict))
    more = value.get("more_locations")
    _check(isinstance(more, list) and len(more) <= 50)
    confidence = value.get("confidence")
    _check(type(confidence) is float and 0.0 <= confidence <= 1.0)
    _check(value.get("type") in TYPE_LABELS and value.get("category") == CATEGORY_OF[value["type"]])
    _check(value.get("method") in _METHODS)
    _check(_count(value.get("occurrences")) >= 1)
    return Finding(
        category=value["category"], type=value["type"], method=value["method"], confidence=confidence,
        masked_value=_text(value.get("masked_value"), 300), context=_text(value.get("context"), 1_000),
        location=_scalars(value.get("location"), STORED_LOCATION_KEYS),
        more_locations=tuple(_scalars(location, STORED_LOCATION_KEYS) for location in more),
        occurrences=value["occurrences"], explanation=_text(value.get("explanation"), 1_000),
    )


def _detection_stats(value) -> dict | None:
    if value is None:
        return None
    _check(isinstance(value, dict) and set(value) == {"detections", "findings", "by_type", "truncated"})
    by_type = value["by_type"]
    _check(isinstance(by_type, dict) and all(kind in TYPE_LABELS for kind in by_type))
    _check(type(value["truncated"]) is bool)
    return {"detections": _count(value["detections"]), "findings": _count(value["findings"]),
            "by_type": {kind: _count(n) for kind, n in by_type.items()}, "truncated": value["truncated"]}


def decode_reply(data: bytes) -> JobResult | EngineError:
    """Rebuild a reply from the child, checking every field. Raises ProtocolError."""
    try:
        payload = json.loads(data)
    except (ValueError, RecursionError):  # not JSON at all - a pickle, say
        raise ProtocolError from None
    _check(isinstance(payload, dict))
    if "error" in payload:
        error = payload["error"]
        _check(isinstance(error, dict))
        return EngineError(_text(error.get("kind"), 100), _text(error.get("where"), 200))
    findings = payload.get("findings")
    _check(isinstance(findings, list) and len(findings) <= MAX_FINDINGS_PER_FILE)
    return JobResult(_extraction(payload.get("extraction")), tuple(_finding(f) for f in findings),
                     _detection_stats(payload.get("detection")))


# ---------------------------------------------------------------- the parent


class ExtractionSupervisor:
    """Owns the child process: sends jobs, enforces the timeout, replaces it after failures."""

    def __init__(self, timeout: float, *, target: Callable = child_main, poll_interval: float = 0.25):
        self.timeout = timeout
        self._target = target
        self._poll = poll_interval
        # "spawn" starts a fresh interpreter - the only option on Windows, and
        # chosen everywhere so behaviour is identical on Linux (NFR-043).
        self._context = multiprocessing.get_context("spawn")
        self._process = None
        self._connection = None

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()

    def _start(self) -> None:
        parent_end, child_end = self._context.Pipe()
        self._process = self._context.Process(
            target=_child_entry, args=(child_end, self._target), daemon=True, name="privguard-extractor"
        )
        self._process.start()
        child_end.close()  # the parent keeps only its own end
        self._connection = parent_end

    def _discard(self, *, kill: bool) -> None:
        if self._process is not None:
            if kill and self._process.is_alive():
                self._process.kill()
            self._process.join(timeout=5)
        if self._connection is not None:
            self._connection.close()
        self._process = self._connection = None

    def run(self, job: Job, on_wait: Callable[[], bool] | None = None) -> Outcome:
        """Extract (and search) one file in the child.

        `on_wait` is called every poll interval while waiting; returning False
        cancels the job (the child is killed and replaced on the next run).
        """
        if self._process is None or not self._process.is_alive():
            self._discard(kill=True)
            self._start()

        started = time.monotonic()
        try:
            self._connection.send(job)
        except OSError:
            self._discard(kill=True)
            return Outcome(CRASHED, None, 0.0)

        while True:
            elapsed = time.monotonic() - started
            if self._connection.poll(self._poll):
                try:
                    reply = decode_reply(self._connection.recv_bytes(MAX_REPLY_BYTES))
                except (EOFError, OSError):  # the child died mid-reply, or the reply was too big
                    self._discard(kill=True)
                    return Outcome(CRASHED, None, elapsed)
                except ProtocolError:
                    # Not what a genuine child sends: it may have been taken over. Replace it.
                    logger.warning("The extraction child sent an invalid reply; it was stopped.")
                    self._discard(kill=True)
                    return Outcome(CRASHED, None, elapsed)
                kind = ERROR if isinstance(reply, EngineError) else DONE
                return Outcome(kind, reply, time.monotonic() - started)
            if not self._process.is_alive():
                self._discard(kill=False)
                return Outcome(CRASHED, None, elapsed)
            if elapsed >= self.timeout:
                self._discard(kill=True)
                return Outcome(TIMEOUT, None, elapsed)
            if on_wait is not None and on_wait() is False:
                self._discard(kill=True)
                return Outcome(CANCELLED, None, elapsed)

    def close(self) -> None:
        """Ask the child to exit; kill it if it does not."""
        if self._process is not None and self._process.is_alive():
            try:
                self._connection.send(None)
            except OSError:
                pass
            self._process.join(timeout=5)
        self._discard(kill=True)
