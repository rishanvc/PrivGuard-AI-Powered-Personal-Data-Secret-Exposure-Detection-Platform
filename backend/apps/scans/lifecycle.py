"""Scan lifecycle: which status changes are allowed (FR-082, FR-089).

    draft --start--> queued --(Cycle 4 worker)--> processing --> completed
                       |                              |      +--> partially_completed
                       |                              |      +--> failed
                       +----cancel---> cancelled <----+-cancel

Transitions are applied with a conditional UPDATE (see services.transition),
so of two simultaneous requests, exactly one can succeed.
"""

from .models import Scan

S = Scan.Status

# action -> (statuses it may start from, resulting status)
ACTIONS = {
    "start": (frozenset({S.DRAFT}), S.QUEUED),
    "cancel": (frozenset({S.QUEUED, S.PROCESSING}), S.CANCELLED),
}

FINISHED = frozenset({S.COMPLETED, S.PARTIALLY_COMPLETED, S.FAILED, S.CANCELLED})

# While processing, a worker is reading the scan's files; deleting them
# underneath it is refused. Cancel first.
UNDELETABLE = frozenset({S.PROCESSING})


def can(action: str, status: str) -> bool:
    allowed_from, _ = ACTIONS[action]
    return status in allowed_from
