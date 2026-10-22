"""Authorization tests (FR-004, FR-005, NFR-018).

The Scan model arrives in Cycle 3. Until then, django.contrib.admin's LogEntry
stands in as the owned resource: it is a real model with a real `user` foreign
key, so OwnedQuerysetMixin and IsOwner run exactly the code path they will run
for Scan. The end-to-end "user A requests user B's scan" test is added in
Cycle 3, once Scan exists.

Credentials here are synthetic test values.
"""

from types import SimpleNamespace

from django.contrib.admin.models import ADDITION, LogEntry
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase
from rest_framework import generics, serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, APITestCase, force_authenticate
from rest_framework.views import APIView

from apps.accounts.permissions import IsAdminRole, IsOwner, OwnedQuerysetMixin

User = get_user_model()
PASSWORD = "correct-horse-battery-staple"


# ---------------------------------------------------------------- test-only views

class _EntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = LogEntry
        fields = ["id", "object_repr"]


class _OwnedDetail(OwnedQuerysetMixin, generics.RetrieveAPIView):
    queryset = LogEntry.objects.all()
    serializer_class = _EntrySerializer
    permission_classes = [IsAuthenticated, IsOwner]


class _OwnedList(OwnedQuerysetMixin, generics.ListAPIView):
    queryset = LogEntry.objects.order_by("id")
    serializer_class = _EntrySerializer
    permission_classes = [IsAuthenticated]


class _AdminOnly(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get(self, request):
        return Response({"ok": True})


# ---------------------------------------------------------------- roles

class RolePermissionTests(APITestCase):
    def setUp(self):
        self.factory = APIRequestFactory()

    def get_as(self, user):
        request = self.factory.get("/")
        if user is not None:
            force_authenticate(request, user=user)
        return _AdminOnly.as_view()(request)

    def test_admin_role_is_allowed(self):
        admin = User.objects.create_user("ada", password=PASSWORD, role=User.Role.ADMIN)
        self.assertEqual(self.get_as(admin).status_code, 200)

    def test_every_non_admin_role_is_denied(self):
        for role in (User.Role.ANALYST, User.Role.DEVELOPER, User.Role.GENERAL):
            with self.subTest(role=role):
                user = User.objects.create_user(f"user_{role}", password=PASSWORD, role=role)
                self.assertEqual(self.get_as(user).status_code, 403)

    def test_is_staff_alone_does_not_grant_admin_role(self):
        # Django-admin access and PrivGuard admin powers are separate.
        staff = User.objects.create_user("sam", password=PASSWORD, is_staff=True)
        self.assertEqual(self.get_as(staff).status_code, 403)

    def test_superuser_is_admin_through_role(self):
        root = User.objects.create_superuser("root", "root@example.com", PASSWORD)
        self.assertEqual(self.get_as(root).status_code, 200)

    def test_anonymous_is_denied(self):
        self.assertEqual(self.get_as(None).status_code, 403)


# ---------------------------------------------------------------- ownership

class OwnershipTests(APITestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.alice = User.objects.create_user("alice", password=PASSWORD)
        self.bob = User.objects.create_user("bob", password=PASSWORD)
        self.admin = User.objects.create_user("ada", password=PASSWORD, role=User.Role.ADMIN)
        self.alice_entry = LogEntry.objects.create(
            user=self.alice, action_flag=ADDITION, object_repr="alice-private"
        )
        LogEntry.objects.create(user=self.bob, action_flag=ADDITION, object_repr="bob-private")

    def retrieve(self, user, pk):
        request = self.factory.get("/")
        force_authenticate(request, user=user)
        return _OwnedDetail.as_view()(request, pk=pk)

    def list_for(self, user):
        request = self.factory.get("/")
        force_authenticate(request, user=user)
        return _OwnedList.as_view()(request)

    def test_owner_can_retrieve_own_object(self):
        r = self.retrieve(self.alice, self.alice_entry.pk)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["object_repr"], "alice-private")

    def test_other_user_gets_404_not_403(self):
        # 404 reveals nothing; 403 would confirm the ID exists.
        self.assertEqual(self.retrieve(self.bob, self.alice_entry.pk).status_code, 404)

    def test_admin_role_gets_no_ownership_bypass(self):
        # Cycle 2 decision: least privilege. Admins can't open others' data.
        self.assertEqual(self.retrieve(self.admin, self.alice_entry.pk).status_code, 404)

    def test_list_contains_only_own_objects(self):
        r = self.list_for(self.alice)
        self.assertEqual([row["object_repr"] for row in r.data["results"]], ["alice-private"])

    def test_list_for_user_with_nothing_is_empty_not_everything(self):
        r = self.list_for(self.admin)
        self.assertEqual(r.data["count"], 0)


# ---------------------------------------------------------------- IsOwner in isolation

class IsOwnerUnitTests(SimpleTestCase):
    """No database: checks the permission class's own logic."""

    @staticmethod
    def check(user, obj, owner_field="user"):
        request = SimpleNamespace(user=user)
        view = SimpleNamespace(owner_field=owner_field)
        return IsOwner().has_object_permission(request, view, obj)

    def test_owner_matches(self):
        user = SimpleNamespace(pk=7, is_authenticated=True)
        self.assertTrue(self.check(user, SimpleNamespace(user_id=7)))

    def test_non_owner_is_denied(self):
        user = SimpleNamespace(pk=7, is_authenticated=True)
        self.assertFalse(self.check(user, SimpleNamespace(user_id=8)))

    def test_custom_owner_field(self):
        user = SimpleNamespace(pk=7, is_authenticated=True)
        self.assertTrue(self.check(user, SimpleNamespace(created_by_id=7), owner_field="created_by"))

    def test_anonymous_user_and_ownerless_object_is_denied(self):
        # Regression test: without the explicit None check, pk None ==
        # user_id None evaluated True and granted access.
        anonymous = SimpleNamespace(pk=None, is_authenticated=False)
        self.assertFalse(self.check(anonymous, SimpleNamespace(user_id=None)))

    def test_authenticated_user_and_ownerless_object_is_denied(self):
        user = SimpleNamespace(pk=7, is_authenticated=True)
        self.assertFalse(self.check(user, SimpleNamespace()))
