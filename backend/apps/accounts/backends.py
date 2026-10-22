"""Authentication backend: username OR email (SRS 5.1.1)."""

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class EmailOrUsernameBackend(ModelBackend):
    """Authenticate with either a username or an email address.

    Mirrors ModelBackend.authenticate, including its timing-attack mitigation:
    when no account matches, we still run the password hasher once, so an
    attacker can't tell "no such user" from "wrong password" by measuring how
    long the response takes.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()
        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)
        if not username or password is None:
            return None

        user = self._find_user(UserModel, username)
        if user is None:
            UserModel().set_password(password)  # equalise timing; result discarded
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None

    @staticmethod
    def _find_user(UserModel, identifier):
        # Username first: it's the primary identifier and always unique.
        try:
            return UserModel._default_manager.get_by_natural_key(identifier)
        except UserModel.DoesNotExist:
            pass
        # Then email, case-insensitively - matching the uniq_user_email_ci
        # constraint, which guarantees at most one row.
        if "@" in identifier:
            return UserModel._default_manager.filter(email__iexact=identifier).first()
        return None
