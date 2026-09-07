"""Role-based access control wiring for the Django Admin backoffice.

Each administrative ``Role`` is mapped to an ``auth.Group`` that carries the
model permissions for that role. Users inherit permissions through the group
synced to their role, so Django Admin's native ``has_*_permission`` checks
enforce access without any custom permission logic.

The permission matrix below is the single source of truth. Run
``manage.py sync_roles`` (or call :func:`sync_role_groups`) after migrations to
apply it.
"""

from __future__ import annotations

# Permission matrix: role slug -> either "__all__" or a mapping of
# (app_label, model_name) -> list of actions (add / change / delete / view).
#
# "Operational data" = api.stations, api.regions.
# "Editorial content" = api.faqcategory, api.faqquestion (public FAQ page).
# "Reflected dbt tables" = api.stations, api.regions — read-only for everyone.
# "Admin-owned station data" = api.stationdetails, api.stationoverride — the
# models that replace the operational spreadsheet and the status seed CSV, and
# the only station data that is editable from the backoffice.
# "Sensor Leasing data" = api.institution, api.institutioncontract,
# api.institutionuser — client organizations, their leasing contracts, and the
# links granting users access to the institutional dashboard; admin-owned
# like the station data above.
# "Institutional alerts" = api.institutionalertrule, the configurable alert an
# operator sets up (admin's "Institution alerts" page), plus the two models it
# owns. Both of those carry `view` only for the roles that manage alerts, since
# neither is written by hand:
#   * api.institutionalert — the recorded firings, shown inline on the alert
#     page and registered read-only (see api.admin.InstitutionAlertEventAdmin).
#   * api.institutionalertrulestate — the sender's per-alert memory. `delete` is
#     granted alongside `delete_institutionalertrule` and only for that: it is a
#     CASCADE dependent, so Django checks it while deleting an alert and refuses
#     the whole deletion without it. Deleting one directly stays blocked in
#     api.admin.InstitutionAlertRuleStateAdmin regardless of this permission.
# Note both api.institutionalert and api.institutionalertrule display as
# "institution alert" in the admin's permission lists — the latter sets that
# verbose_name deliberately (see its Meta) — so match them by codename, not by
# the label shown on screen.
# "Institutional action history" = api.actionlog — written by institutions
# through the API and view-only in the backoffice for everyone (see
# api.admin.ActionLogAdmin), so only `view` is ever granted here.
# "Administrative configuration" = accounts.user, accounts.role.
#
# Note that `change_stationdetails` also gates opening a station's change page
# (see api.admin.StationsViewer), since the details are edited inline there.
ROLE_GROUP_PERMISSIONS: dict[str, object] = {
    # Superadmin: unrestricted administrative access.
    "superadmin": "__all__",
    # Admin: read the reflected dbt tables, manage admin-owned station data,
    # read administrative config, and fully manage editorial content.
    "admin": {
        ("api", "stations"): ["view"],
        ("api", "regions"): ["view"],
        ("api", "faqcategory"): ["add", "change", "delete", "view"],
        ("api", "faqquestion"): ["add", "change", "delete", "view"],
        ("api", "stationdetails"): ["add", "change", "view"],
        ("api", "stationoverride"): ["add", "change", "delete", "view"],
        ("api", "institution"): ["add", "change", "delete", "view"],
        ("api", "institutioncontract"): ["add", "change", "delete", "view"],
        ("api", "institutionuser"): ["add", "change", "delete", "view"],
        ("api", "institutionalert"): ["add", "change", "delete", "view"],
        ("api", "institutionalertrule"): ["add", "change", "delete", "view"],
        ("api", "institutionalertrulestate"): ["delete", "view"],
        ("api", "actionlog"): ["view"],
        ("accounts", "user"): ["view"],
        ("accounts", "role"): ["view"],
    },
    # Editor: edits admin-owned station data and editorial content, but never
    # the reflected dbt tables or administrative configuration. Deleting an
    # override remains an Admin decision.
    "editor": {
        ("api", "stations"): ["view"],
        ("api", "regions"): ["view"],
        ("api", "faqcategory"): ["add", "change", "view"],
        ("api", "faqquestion"): ["add", "change", "view"],
        ("api", "stationdetails"): ["add", "change", "view"],
        ("api", "stationoverride"): ["add", "change", "view"],
        ("api", "institution"): ["add", "change", "view"],
        ("api", "institutioncontract"): ["add", "change", "view"],
        ("api", "institutionuser"): ["add", "change", "view"],
        ("api", "institutionalert"): ["add", "change", "view"],
        ("api", "institutionalertrule"): ["add", "change", "view"],
        ("api", "institutionalertrulestate"): ["view"],
        ("api", "actionlog"): ["view"],
    },
    # Viewer: read-only on operational data, admin-owned station data, and
    # editorial content.
    "viewer": {
        ("api", "stations"): ["view"],
        ("api", "regions"): ["view"],
        ("api", "faqcategory"): ["view"],
        ("api", "faqquestion"): ["view"],
        ("api", "stationdetails"): ["view"],
        ("api", "stationoverride"): ["view"],
        ("api", "institution"): ["view"],
        ("api", "institutioncontract"): ["view"],
        ("api", "institutionuser"): ["view"],
        ("api", "institutionalert"): ["view"],
        ("api", "institutionalertrule"): ["view"],
        ("api", "institutionalertrulestate"): ["view"],
        ("api", "actionlog"): ["view"],
    },
}


def group_name_for_role(slug: str) -> str:
    """Deterministic Group name for a role slug (e.g. "superadmin" -> "Superadmin")."""
    return slug.capitalize()


ROLE_GROUP_NAMES = {group_name_for_role(slug) for slug in ROLE_GROUP_PERMISSIONS}


def sync_role_groups() -> None:
    """Create/refresh the auth.Group for each role and set its permissions.

    Idempotent. Requires model permissions to exist (i.e. run after migrations,
    once contenttypes/permissions have been populated).
    """
    from django.contrib.auth.models import Group, Permission
    from django.contrib.contenttypes.models import ContentType

    for slug, spec in ROLE_GROUP_PERMISSIONS.items():
        group, _ = Group.objects.get_or_create(name=group_name_for_role(slug))

        if spec == "__all__":
            group.permissions.set(Permission.objects.all())
            continue

        permissions = []
        for (app_label, model_name), actions in spec.items():  # type: ignore[union-attr]
            try:
                content_type = ContentType.objects.get(
                    app_label=app_label, model=model_name
                )
            except ContentType.DoesNotExist:
                continue
            for action in actions:
                codename = f"{action}_{model_name}"
                try:
                    permissions.append(
                        Permission.objects.get(
                            content_type=content_type, codename=codename
                        )
                    )
                except Permission.DoesNotExist:
                    continue
        group.permissions.set(permissions)


def sync_user_group(user) -> None:
    """Ensure the user belongs to exactly the group of their assigned role.

    Removes any other role-managed group so a role change does not leave stale
    permissions behind. Non-role groups are left untouched.
    """
    from django.contrib.auth.models import Group

    role = getattr(user, "role", None)
    if role is not None:
        target_name = group_name_for_role(role.slug)
        target_group, _ = Group.objects.get_or_create(name=target_name)
        stale = user.groups.filter(name__in=ROLE_GROUP_NAMES).exclude(name=target_name)
        if stale.exists():
            user.groups.remove(*stale)
        user.groups.add(target_group)
    else:
        managed = user.groups.filter(name__in=ROLE_GROUP_NAMES)
        if managed.exists():
            user.groups.remove(*managed)
