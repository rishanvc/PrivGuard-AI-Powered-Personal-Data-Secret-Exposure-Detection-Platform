"""python manage.py run_worker [--once]"""

from django.core.management.base import BaseCommand

from apps.scans.worker import run_worker


class Command(BaseCommand):
    help = "Process queued scans. Extraction runs in an isolated child process with a time limit."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Process the queue until it is empty, then exit.")

    def handle(self, *args, once=False, **options):
        processed = run_worker(once=once, log=self._log)
        if once:
            self._log(f"Queue empty. Processed {processed} scan(s).")

    def _log(self, message: str) -> None:
        # Flush every line. Written to a file or pipe (a log file, Docker),
        # Python's output is block-buffered, and a busy worker would look silent.
        self.stdout.write(message)
        self.stdout.flush()
