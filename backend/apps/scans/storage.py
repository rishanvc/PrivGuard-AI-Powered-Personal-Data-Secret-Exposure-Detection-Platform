"""Private storage for uploaded scan files (FR-030, NFR-023)."""

import os
import uuid

from django.conf import settings
from django.core.files.storage import FileSystemStorage


class PrivateUploadStorage(FileSystemStorage):
    """Uploaded files live under settings.UPLOAD_ROOT and have NO URL.

    base_url is None, so storage.url() raises instead of producing a link.
    Uploads are only ever read by PrivGuard's own code; any download of a
    sanitized copy (Cycle 10) goes through an authenticated, ownership-checked
    view - never a static file URL.

    The location is read from settings on every access rather than captured at
    import time, so tests can point it at a temporary directory.
    """

    @property
    def base_location(self):
        return os.fspath(settings.UPLOAD_ROOT)

    @property
    def location(self):
        return os.path.abspath(self.base_location)

    @property
    def base_url(self):
        return None


private_upload_storage = PrivateUploadStorage()


def scan_dir_name(user_id, scan_id) -> str:
    """Storage-relative folder holding one scan's files: <user id>/<scan id>.

    Per-user, per-scan folders isolate users' files (FR-030) and make deleting
    a scan a single folder removal.
    """
    return f"{user_id}/{scan_id}"


def upload_path(instance, filename):
    """Storage name for an accepted upload: <user id>/<scan id>/<random hex>.

    `filename` - the name the uploader chose - is deliberately ignored. It is
    attacker-controlled (traversal, reserved device names such as CON,
    look-alike Unicode), so it never reaches the filesystem; the sanitised
    display name is kept in the database instead. There is no extension
    either, so nothing on disk can be opened or served by type based on what
    the uploader called it.
    """
    return f"{scan_dir_name(instance.scan.user_id, instance.scan_id)}/{uuid.uuid4().hex}"
