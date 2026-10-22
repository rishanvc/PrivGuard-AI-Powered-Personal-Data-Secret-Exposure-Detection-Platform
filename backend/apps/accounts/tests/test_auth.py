"""Authentication API tests (Cycle 2).

Covers FR-002 (login), FR-003 (hashing), FR-006 (sessions and logout),
FR-001/FR-007 (registration off by default), and the authentication items
of SRS 12.3 security testing.

Every credential in this file is a synthetic test value, not a real secret.
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient, APITestCase

User = get_user_model()

PASSWORD = "correct-horse-battery-staple"  # synthetic test credential
FRONTEND_ORIGIN = "http://localhost:5173"


class AuthTestBase(APITestCase):
    def setUp(self):
        # Throttle counters live in the cache. Without clearing it, attempts
        # made in one test would count against the next, and tests would fail
        # depending on the order they happened to run in.
        cache.clear()
        self.user = User.objects.create_user(
            username="alice", email="Alice@Example.com", password=PASSWORD
        )

    def login(self, client=None, identifier="alice", password=PASSWORD, **extra):
        client = client or self.client
        return client.post(
            reverse("auth-login"),
            {"identifier": identifier, "password": password},
            format="json",
            **extra,
        )


class LoginTests(AuthTestBase):
    def test_login_with_username_sets_httponly_session_cookie(self):
        r = self.login()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["user"]["username"], "alice")
        self.assertIn("csrfToken", r.data)
        cookie = r.cookies[settings.SESSION_COOKIE_NAME]
        self.assertTrue(cookie["httponly"], "session cookie must not be readable by JavaScript")

    def test_login_with_email_is_case_insensitive(self):
        self.assertEqual(self.login(identifier="alice@example.COM").status_code, 200)

    def test_wrong_password_and_unknown_user_are_indistinguishable(self):
        wrong_password = self.login(password="not-the-password")
        unknown_user = self.login(identifier="mallory")
        self.assertEqual(wrong_password.status_code, 400)
        self.assertEqual(unknown_user.status_code, 400)
        # Identical bodies: the endpoint must not reveal which accounts exist.
        self.assertEqual(wrong_password.data, unknown_user.data)

    def test_inactive_user_cannot_log_in(self):
        self.user.is_active = False
        self.user.save()
        self.assertEqual(self.login().status_code, 400)

    def test_password_is_never_returned(self):
        r = self.login()
        self.assertNotIn("password", r.data["user"])

    def test_login_rotates_session_key(self):
        # Session fixation: a session that existed BEFORE login must not
        # survive it, or an attacker who planted that session ID inherits
        # the logged-in session.
        session = self.client.session
        session["probe"] = True
        session.save()
        before = session.session_key

        self.assertEqual(self.login().status_code, 200)
        self.assertNotEqual(self.client.session.session_key, before)

    def test_login_is_throttled_after_repeated_attempts(self):
        limit = int(settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["auth"].split("/")[0])
        for _ in range(limit):
            self.assertEqual(self.login(password="wrong").status_code, 400)
        self.assertEqual(self.login(password="wrong").status_code, 429)


class CsrfTests(AuthTestBase):
    """Login CSRF. APIClient skips CSRF by default, so these opt back in."""

    def csrf_client(self):
        client = APIClient(enforce_csrf_checks=True)
        token = client.get(reverse("auth-csrf")).data["csrfToken"]
        return client, token

    def test_login_without_csrf_token_is_rejected(self):
        client = APIClient(enforce_csrf_checks=True)
        r = self.login(client=client)
        self.assertEqual(r.status_code, 403)
        self.assertIn("CSRF", str(r.data["detail"]))

    def test_login_with_csrf_token_from_frontend_origin_succeeds(self):
        client, token = self.csrf_client()
        r = self.login(client=client, HTTP_X_CSRFTOKEN=token, HTTP_ORIGIN=FRONTEND_ORIGIN)
        self.assertEqual(r.status_code, 200)

    def test_login_from_untrusted_origin_is_rejected_even_with_token(self):
        client, token = self.csrf_client()
        r = self.login(client=client, HTTP_X_CSRFTOKEN=token, HTTP_ORIGIN="http://evil.example.com")
        self.assertEqual(r.status_code, 403)

    def test_logout_requires_csrf_token(self):
        client, token = self.csrf_client()
        self.login(client=client, HTTP_X_CSRFTOKEN=token)
        # No token on the logout POST: must be refused, user stays logged in.
        self.assertEqual(client.post(reverse("auth-logout")).status_code, 403)
        self.assertEqual(client.get(reverse("auth-me")).status_code, 200)


class LogoutTests(AuthTestBase):
    def test_logout_ends_the_session(self):
        self.login()
        self.assertEqual(self.client.get(reverse("auth-me")).status_code, 200)
        self.assertEqual(self.client.post(reverse("auth-logout")).status_code, 204)
        self.assertEqual(self.client.get(reverse("auth-me")).status_code, 403)

    def test_copied_session_cookie_is_useless_after_logout(self):
        # Server-side revocation: the reason we chose sessions over JWTs.
        # Someone holding a copy of the cookie loses access the moment the
        # real user logs out.
        self.login()
        stolen = self.client.cookies[settings.SESSION_COOKIE_NAME].value
        self.client.post(reverse("auth-logout"))

        attacker = APIClient()
        attacker.cookies[settings.SESSION_COOKIE_NAME] = stolen
        self.assertEqual(attacker.get(reverse("auth-me")).status_code, 403)

    def test_logout_via_get_is_not_allowed(self):
        self.login()
        self.assertEqual(self.client.get(reverse("auth-logout")).status_code, 405)
        self.assertEqual(self.client.get(reverse("auth-me")).status_code, 200)

    def test_logout_when_not_logged_in_is_harmless(self):
        self.assertEqual(self.client.post(reverse("auth-logout")).status_code, 204)


class MeTests(AuthTestBase):
    def test_me_requires_authentication(self):
        # 403 rather than 401: DRF's SessionAuthentication sends no
        # WWW-Authenticate challenge, so DRF reports "forbidden".
        self.assertEqual(self.client.get(reverse("auth-me")).status_code, 403)

    def test_me_returns_profile_without_sensitive_fields(self):
        self.login()
        r = self.client.get(reverse("auth-me"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["username"], "alice")
        self.assertEqual(r.data["role"], User.Role.GENERAL)
        for field in ("password", "is_superuser", "is_staff"):
            self.assertNotIn(field, r.data)


class RegistrationTests(AuthTestBase):
    def register(self, **fields):
        payload = {"username": "bob", "email": "bob@example.com", "password": PASSWORD}
        payload.update(fields)
        return self.client.post(reverse("auth-register"), payload, format="json")

    def test_registration_is_disabled_by_default(self):
        self.assertFalse(settings.ALLOW_REGISTRATION)
        self.assertEqual(self.register().status_code, 403)
        self.assertFalse(User.objects.filter(username="bob").exists())

    @override_settings(ALLOW_REGISTRATION=True)
    def test_registration_creates_general_user_and_ignores_role(self):
        r = self.register(role="admin")  # escalation attempt
        self.assertEqual(r.status_code, 201)
        bob = User.objects.get(username="bob")
        self.assertEqual(bob.role, User.Role.GENERAL)
        self.assertTrue(bob.check_password(PASSWORD))
        self.assertNotEqual(bob.password, PASSWORD)  # stored hashed (FR-003)

    @override_settings(ALLOW_REGISTRATION=True)
    def test_registration_rejects_duplicate_email_case_insensitive(self):
        self.assertEqual(self.register(email="ALICE@example.com").status_code, 400)

    @override_settings(ALLOW_REGISTRATION=True)
    def test_registration_enforces_password_validators(self):
        self.assertEqual(self.register(password="123").status_code, 400)


class UserModelTests(TestCase):
    def test_superuser_gets_admin_role(self):
        root = User.objects.create_superuser("root", "root@example.com", PASSWORD)
        self.assertEqual(root.role, User.Role.ADMIN)

    def test_regular_user_defaults_to_general_role(self):
        self.assertEqual(User.objects.create_user("u1", password=PASSWORD).role, User.Role.GENERAL)

    def test_email_is_unique_case_insensitively(self):
        User.objects.create_user("u1", "Same@Example.com", PASSWORD)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                User.objects.create_user("u2", "same@example.COM", PASSWORD)

    def test_multiple_accounts_without_email_are_allowed(self):
        User.objects.create_user("u1", "", PASSWORD)
        User.objects.create_user("u2", "", PASSWORD)
        self.assertEqual(User.objects.filter(email="").count(), 2)


class HealthEndpointTests(APITestCase):
    def test_health_stays_public(self):
        # Deny-by-default must not lock out the one endpoint needed to
        # diagnose a broken login.
        self.assertEqual(self.client.get(reverse("health")).status_code, 200)
