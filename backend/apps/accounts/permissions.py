"""Authorization rules (FR-004, FR-005, NFR-018).

Authentication answers "who are you?". These classes answer "what may you touch?".

Cycle 2 decision - least privilege: administrators manage users, settings and
policy, but get NO bypass on ownership. An admin account is not a skeleton key
to every user's findings.
"""

from django.conf import settings
from rest_framework.permissions import BasePermission


class IsAdminRole(BasePermission):
    """Allow only users whose PrivGuard role is Administrator.

    Checks `role`, not `is_staff`/`is_superuser`. is_staff controls access to
    the Django admin site; `role` controls PrivGuard features. Keeping them
    separate means granting one never silently grants the other.
    """

    message = "Administrator role required."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.role == user.Role.ADMIN)


class IsOwner(BasePermission):
    """Object-level check: the requesting user must own the object (FR-005).

    Second line of defence. The first is OwnedQuerysetMixin, which removes
    other users' objects from the queryset so they 404 before this runs.
    Compares <field>_id rather than <field> to avoid loading the related user.
    The owner may sit behind a relation, as in "scan__user" for a finding (Cycle 7).
    """

    message = "You do not have access to this resource."

    def has_object_permission(self, request, view, obj):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        *path, field = getattr(view, "owner_field", "user").split("__")
        for relation in path:
            obj = getattr(obj, relation, None)
        owner_id = getattr(obj, f"{field}_id", None)
        # The explicit None check matters: an anonymous user's pk is None, so
        # without it an ownerless object would satisfy None == None. This class
        # must be safe on its own, not only when IsAuthenticated runs first.
        return owner_id is not None and owner_id == user.pk


class OwnedQuerysetMixin:
    """Scope a view's queryset to objects owned by request.user.

    Another user's object is *absent*, not *forbidden*: retrieving it returns
    404, not 403. A 403 would confirm the ID exists; a 404 reveals nothing.

    perform_create stamps the owner server-side, so a client can never create
    an object owned by someone else by putting a different user ID in the body.
    """

    owner_field = "user"

    def get_queryset(self):
        return super().get_queryset().filter(**{self.owner_field: self.request.user})

    def perform_create(self, serializer):
        serializer.save(**{self.owner_field: self.request.user})


class RegistrationEnabled(BasePermission):
    """FR-001 / FR-007: registration exists but is off unless configured."""

    message = "Registration is disabled on this deployment."

    def has_permission(self, request, view):
        return settings.ALLOW_REGISTRATION
