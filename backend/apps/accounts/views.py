"""Authentication endpoints: /api/auth/* (FR-001, FR-002, FR-006)."""

from django.contrib.auth import login, logout
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .permissions import RegistrationEnabled
from .serializers import LoginSerializer, RegisterSerializer, UserSerializer


class CsrfEnforcedSessionAuthentication(SessionAuthentication):
    """SessionAuthentication that enforces CSRF for anonymous requests too.

    DRF's SessionAuthentication only checks CSRF once a user is logged in.
    The login endpoint is, by definition, hit by users who are NOT logged in,
    so by default it has no CSRF protection at all. That allows "login CSRF":
    a malicious page silently logs your browser into the attacker's account,
    and the files you then scan land in a scan the attacker owns.
    """

    def authenticate(self, request):
        result = super().authenticate(request)  # enforces CSRF if a session user exists
        if result is None:
            self.enforce_csrf(request)  # ...and here for anonymous requests
        return result


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfView(APIView):
    """GET /api/auth/csrf/ - issue a CSRF token for the SPA.

    Returned in the body as well as the cookie, so the frontend keeps it in
    memory rather than depending on reading cookies across ports.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"csrfToken": get_token(request)})


class LoginView(APIView):
    """POST /api/auth/login/ - {identifier, password} -> session cookie."""

    permission_classes = [AllowAny]
    authentication_classes = [CsrfEnforcedSessionAuthentication]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]

        # login() issues a NEW session key (defeats session fixation) and a NEW
        # CSRF token. The old token is now stale, so the fresh one goes back in
        # the response - otherwise the SPA's very next POST would fail with 403.
        login(request, user)
        return Response({"user": UserSerializer(user).data, "csrfToken": get_token(request)})


class LogoutView(APIView):
    """POST /api/auth/logout/ - destroy the server-side session.

    POST only: a GET logout could be triggered by an <img> tag on any page.
    Idempotent, and CSRF-protected even when already logged out.
    """

    permission_classes = [AllowAny]
    authentication_classes = [CsrfEnforcedSessionAuthentication]

    def post(self, request):
        logout(request)  # session row deleted; any copy of the cookie is now worthless
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    """GET /api/auth/me/ - the current user, or 403 if not logged in.

    DRF returns 403 (not 401) for unauthenticated session requests, because
    SessionAuthentication defines no WWW-Authenticate challenge.
    """

    def get(self, request):
        return Response(UserSerializer(request.user).data)


class RegisterView(APIView):
    """POST /api/auth/register/ - FR-001, only when ALLOW_REGISTRATION=True."""

    permission_classes = [RegistrationEnabled]
    authentication_classes = [CsrfEnforcedSessionAuthentication]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)
