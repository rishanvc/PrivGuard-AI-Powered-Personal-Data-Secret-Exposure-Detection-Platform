"""Root URL configuration.

All application endpoints live under /api/ so the frontend has one obvious
prefix to proxy and CORS has one obvious surface (SRS 11).
"""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/", include("apps.scans.urls")),
    path("api/", include("apps.core.urls")),
]
