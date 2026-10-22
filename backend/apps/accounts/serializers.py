"""Serializers for authentication and the current user."""

from django.contrib.auth import authenticate, get_user_model, password_validation
from rest_framework import serializers

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    """The user as the frontend sees it.

    Explicit field allow-list. Never `fields = "__all__"`: that would include
    the password hash, is_superuser, and whatever field gets added next year.
    """

    role_display = serializers.CharField(source="get_role_display", read_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "email", "first_name", "last_name", "role", "role_display"]
        read_only_fields = fields


class LoginSerializer(serializers.Serializer):
    identifier = serializers.CharField(max_length=254, label="Username or email")
    # trim_whitespace=False: leading/trailing spaces are legitimate password
    # characters. Stripping them would silently change the user's password.
    password = serializers.CharField(
        max_length=128,
        write_only=True,
        trim_whitespace=False,
        style={"input_type": "password"},
    )

    # One message for every failure - unknown user, wrong password, disabled
    # account - so the endpoint never confirms that an account exists.
    INVALID = "Invalid username/email or password."

    def validate(self, attrs):
        user = authenticate(
            self.context.get("request"),
            username=attrs["identifier"],
            password=attrs["password"],
        )
        if user is None:
            raise serializers.ValidationError(self.INVALID, code="invalid_credentials")
        attrs["user"] = user
        return attrs


class RegisterSerializer(serializers.ModelSerializer):
    """FR-001 self-registration (only reachable when ALLOW_REGISTRATION=True).

    `role` is deliberately NOT a field. Accepting it would let anyone register
    themselves as an Administrator - a classic mass-assignment escalation.
    New accounts always start as General User.
    """

    password = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
        style={"input_type": "password"},
    )

    class Meta:
        model = User
        fields = ["username", "email", "password"]
        extra_kwargs = {"email": {"required": True, "allow_blank": False}}

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email address already exists.")
        return value

    def validate(self, attrs):
        # Django's AUTH_PASSWORD_VALIDATORS: length, common-password list,
        # similarity to username/email, all-numeric.
        candidate = User(username=attrs["username"], email=attrs["email"])
        password_validation.validate_password(attrs["password"], user=candidate)
        return attrs

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)  # hashes the password (FR-003)
