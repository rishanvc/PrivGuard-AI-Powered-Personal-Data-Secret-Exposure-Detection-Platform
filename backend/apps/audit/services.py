"""Writing audit records (FR-116). The one place records are created."""

from __future__ import annotations

from collections.abc import Mapping

from .models import AuditLog

# FR-117: metadata keys allowed in a record. Anything else is a programming
# error - refused loudly rather than stored quietly.
SAFE_KEYS = frozenset({"scan_id", "finding_type", "from_status", "to_status"})


def record(*, user, action: str, resource_type: str, resource_id, metadata: Mapping | None = None,
           result: str = AuditLog.Result.SUCCESS) -> AuditLog:
    metadata = dict(metadata or {})
    unsafe = set(metadata) - SAFE_KEYS
    if unsafe:
        raise ValueError(f"Audit metadata may not contain {sorted(unsafe)} (FR-117).")
    return AuditLog.objects.create(user=user, action=action, resource_type=resource_type,
                                   resource_id=str(resource_id), result=result, safe_metadata=metadata)
