import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _

from .managers import UserManager


class Role(models.Model):
    """Administrative role used to classify users and drive permissions.

    The role provides the semantic grouping (Superadmin / Admin / Editor /
    Viewer). Effective Django Admin permissions are resolved through the
    matching ``auth.Group`` that each role is synced to (see Ticket 5 / RBAC).
    """

    SUPERADMIN = "superadmin"
    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"

    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        db_table = "accounts_role"
        ordering = ["name"]
        verbose_name = "Role"
        verbose_name_plural = "Roles"

    def __str__(self) -> str:
        return self.name


class User(AbstractUser):
    """Custom user model authenticated by email with a UUID primary key.

    ``username`` is preserved for third-party compatibility but is optional and
    excluded from the authentication flow (``USERNAME_FIELD = "email"``).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(_("email address"), unique=True)
    username = models.CharField(max_length=150, blank=True, null=True)
    role = models.ForeignKey(
        Role,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="users",
    )
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    objects = UserManager()

    class Meta:
        db_table = "accounts_user"
        verbose_name = "User"
        verbose_name_plural = "Users"

    def __str__(self) -> str:
        return self.email
