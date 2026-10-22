"""User model and roles (SRS 7.2.1, FR-004)."""

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """PrivGuard user.

    Extends AbstractUser rather than AbstractBaseUser: we want Django's
    username/email/password handling and PBKDF2 hashing (FR-003) as-is, and
    only need to add a role. Rebuilding all of that by hand would add risk
    to the single most security-sensitive model in the system.

    This model exists from Cycle 1 even though authentication is Cycle 2,
    because AUTH_USER_MODEL cannot be changed after the first migration
    without rebuilding the database.
    """

    class Role(models.TextChoices):
        """FR-004 / SRS 2.3. Permission behaviour is implemented in Cycle 2."""

        ADMIN = "admin", "Administrator"
        ANALYST = "analyst", "Security Analyst"
        DEVELOPER = "developer", "Developer"
        GENERAL = "general", "General User"

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.GENERAL,
        help_text="Determines which scans and administrative actions are permitted.",
    )

    # SRS 7.2.1 lists created_at/updated_at on every entity. AbstractUser's
    # date_joined overlaps with created_at, but updated_at is genuinely absent
    # and useful for auditing role changes (FR-116).
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "privguard_user"
        indexes = [models.Index(fields=["role"])]

    def __str__(self) -> str:
        return f"{self.username} ({self.get_role_display()})"
