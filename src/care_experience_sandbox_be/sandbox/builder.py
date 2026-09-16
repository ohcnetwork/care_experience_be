from care.emr.models.organization import Organization
from care.emr.resources.organization.spec import OrganizationTypeChoices
from care.fixtures.scripts.load_pack import load_pack
from care.security.models import RoleModel
from django.db import transaction

from care_experience_sandbox_be.sandbox.pack_counts import summarize_pack_counts
from care_experience_sandbox_be.settings import plugin_settings

# (role name as synced in care, username prefix, pack user ref)
# Pack refs must cover schedules / queues / appointments / clinical requesters.
SANDBOX_USERS = [
    ("Administrator", "care-admin", "user:admin"),
    ("Facility Admin", "care-fac-admin", "user:fac_admin"),
    ("Doctor", "care-doctor", "user:doctor"),
    ("Nurse", "care-nurse", "user:nurse"),
    ("Staff", "care-staff", "user:staff"),
    ("Volunteer", "care-volunteer", "user:volunteer"),
    ("Pharmacist", "care-pharmacist", "user:pharmacist"),
    # Extra pack resources (same roles, distinct sandbox usernames).
    ("Doctor", "care-doctor-peds", "user:doctor_pediatrics"),
    ("Nurse", "care-nurse-peds-1", "user:nurse_pediatrics_1"),
    ("Nurse", "care-nurse-peds-2", "user:nurse_pediatrics_2"),
]

# Sign-in credentials returned to the client (one primary account per role).
SIGN_IN_ROLE_PREFIXES = {
    "Administrator": "care-admin",
    "Facility Admin": "care-fac-admin",
    "Doctor": "care-doctor",
    "Nurse": "care-nurse",
    "Staff": "care-staff",
    "Volunteer": "care-volunteer",
    "Pharmacist": "care-pharmacist",
}

PRIMARY_ROLE = "Facility Admin"


def _pick_or_create_geo(base):
    """Reuse the first existing state and its first district; create defaults if none."""
    govt = OrganizationTypeChoices.govt.value
    state = (
        Organization.objects.filter(org_type=govt, parent__isnull=True)
        .order_by("id")
        .first()
    )
    if state is None:
        resp = base.create_organization(org_type=govt, name="Kerala")
        state_id, state_name = resp.id, resp.name
    else:
        state_id, state_name = str(state.external_id), state.name

    district = (
        Organization.objects.filter(org_type=govt, parent__external_id=state_id)
        .order_by("id")
        .first()
    )
    if district is None:
        resp = base.create_organization(
            org_type=govt, name="Ernakulam", parent=state_id
        )
        district_id, district_name = resp.id, resp.name
    else:
        district_id, district_name = str(district.external_id), district.name

    return state_id, state_name, district_id, district_name


def _seed_full_facility(base, facility_id, user_ids_by_ref):
    """Attach the generic_hospital_v1 pack to this sandbox facility.

    On success, ``loaded_data`` is flat resource→int counts from pack JSON
    (Hub "Loaded data" UI). On failure, bool + error string only.
    """
    try:
        with transaction.atomic():
            load_pack(
                base,
                facility_id=facility_id,
                include_users=False,
                user_ids_by_ref=user_ids_by_ref,
            )
    except Exception as exc:  # noqa: BLE001
        return {
            "pack": False,
            "pack_error": f"{type(exc).__name__}: {exc}",
        }
    return summarize_pack_counts()


def build_sandbox(base, sandbox_id, is_facility_empty, facility_name="", server_url=""):
    password = plugin_settings.SANDBOX_DEFAULT_PASSWORD
    short = str(sandbox_id).replace("-", "")[:8]
    facility_name = (facility_name or "").strip() or f"Sandbox Facility {short}"

    state_id, state_name, district_id, district_name = _pick_or_create_geo(base)

    role_names = {role_name for role_name, _prefix, _ref in SANDBOX_USERS}
    role_orgs = {}
    for role_name in sorted(role_names):
        role_orgs[role_name] = base.create_organization(
            org_type=OrganizationTypeChoices.role.value,
            name=f"{role_name} {short}",
        )

    facility = base.create_facility(
        district_id,
        name=facility_name,
        facility_type="Private Hospital",
    )
    facility_id = facility.id

    administration = next(
        (
            org
            for org in base.get_facility_organizations(facility_id)
            if org.name == "Administration"
        ),
        None,
    )

    wanted = sorted(role_names)
    roles = {r.name: r for r in RoleModel.objects.filter(name__in=wanted)}
    missing = [name for name in wanted if name not in roles]
    if missing:
        msg = f"Required roles not found (run sync_permissions_roles): {missing}"
        raise RuntimeError(msg)

    user_ids_by_ref = {}
    sign_in_by_role = {}
    for role_name, prefix, pack_ref in SANDBOX_USERS:
        role_id = str(roles[role_name].external_id)
        username = f"{prefix}-{short}"
        user = base.create_user(
            district_id,
            role_orgs=[
                {
                    "organization": role_orgs[role_name].id,
                    "role": role_id,
                }
            ],
            username=username,
            email=f"{username}@care.test",
            password=password,
        )
        user_ids_by_ref[pack_ref] = user.id
        if administration:
            base.add_user_to_facility_organization(facility_id, administration.id, user.id, role_id)
        if SIGN_IN_ROLE_PREFIXES.get(role_name) == prefix:
            sign_in_by_role[role_name] = {
                "username": username,
                "password": password,
                "role": role_name,
                "sign_in_url": server_url,
                "is_primary": role_name == PRIMARY_ROLE,
            }

    users = [sign_in_by_role[role_name] for role_name in SIGN_IN_ROLE_PREFIXES if role_name in sign_in_by_role]

    loaded_data = {}
    if not is_facility_empty:
        loaded_data = _seed_full_facility(base, facility_id, user_ids_by_ref)

    return {
        "server": server_url,
        "default_password": password,
        "is_facility_empty": is_facility_empty,
        "facility": {
            "id": facility_id,
            "name": facility.name,
            "type": "Private Hospital",
            "district": district_name,
            "state": state_name,
        },
        "users": users,
        "loaded_data": loaded_data,
    }
