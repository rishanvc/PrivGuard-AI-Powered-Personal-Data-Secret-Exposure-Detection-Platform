"""User model and roles (SRS 7.2.1, FR-004)."""

from django.contrib.auth.models import AbstractUser
from django.contrib.auth.models import UserManager as DjangoUserManager
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower


class UserManager(DjangoUserManager):
    """Superusers get the PrivGuard Administrator role automatically.

    Without this, `createsuperuser` would produce an account Django treats as
    all-powerful but PrivGuard treats as a General User, because `role`
    defaults to GENERAL. Two permission systems disagreeing about the same
    account is exactly the kind of gap that causes access-control bugs.
    """

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault("role", self.model.Role.ADMIN)
        return super().create_superuser(username, email, password, **extra_fields)


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

    objects = UserManager()

    class Meta:
        db_table = "privguard_user"
        indexes = [models.Index(fields=["role"])]
        constraints = [
            # Login accepts an email address (SRS 5.1.1), so two accounts must
            # never share one - including "Alice@x.com" vs "alice@x.com".
            # Blank emails are exempt so accounts without an email still work.
            models.UniqueConstraint(
                Lower("email"),
                condition=~Q(email=""),
                name="uniq_user_email_ci",
                violation_error_message="A user with this email address already exists.",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.username} ({self.get_role_display()})"
