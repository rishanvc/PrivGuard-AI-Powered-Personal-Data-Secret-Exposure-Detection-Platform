"""Authentication routes, mounted at /api/auth/."""

from django.urls import path

from .views import CsrfView, LoginView, LogoutView, MeView, RegisterView

urlpatterns = [
    path("csrf/", CsrfView.as_view(), name="auth-csrf"),
    path("login/", LoginView.as_view(), name="auth-login"),
    path("logout/", LogoutView.as_view(), name="auth-logout"),
    path("me/", MeView.as_view(), name="auth-me"),
    path("register/", RegisterView.as_view(), name="auth-register"),
]
