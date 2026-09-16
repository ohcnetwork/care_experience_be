import logging
import sys
import warnings
from contextlib import contextmanager
from unittest.mock import patch

import care.emr.utils.valueset_coding_type  # noqa: F401
from care.fixtures.base import CareFixtureBase
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import transaction
from rest_framework.test import APIClient

from care_experience_sandbox_be.settings import plugin_settings

# Skip valueset validation while seeding, mirroring care's fixture context.
sys.modules["care.emr.utils.valueset_coding_type"].validate_valueset = (
    lambda f, s, c: c
)


class _NoOpLock:
    """Bypass create locks inside the outer sandbox transaction."""

    def __init__(self, *args, **kwargs):
        pass

    def acquire(self):
        pass

    def release(self):
        pass


class _SecureAPIClient(APIClient):
    """Force every request to be treated as HTTPS so SECURE_SSL_REDIRECT won't 301."""

    def generic(self, method, path, *args, **kwargs):
        kwargs["secure"] = True
        return super().generic(method, path, *args, **kwargs)


def _resolve_actor(actor_user):
    """Seed as the authorized caller; fall back to any superuser if unset."""
    if actor_user is not None and actor_user.is_superuser:
        return actor_user
    superuser = get_user_model().objects.filter(is_superuser=True).first()
    if superuser is None:
        msg = "No superuser available to run the sandbox seeding."
        raise RuntimeError(msg)
    return superuser


@contextmanager
def sandbox_context(actor_user=None, base_cls: type[CareFixtureBase] = CareFixtureBase):
    if not plugin_settings.SANDBOX_ENABLED:
        msg = "Sandbox creation is disabled. Set SANDBOX_ENABLED to enable it."
        raise RuntimeError(msg)

    audit_logger = logging.getLogger("audit_log")
    original_level = audit_logger.level
    audit_logger.setLevel(logging.WARNING)

    try:
        call_command("sync_permissions_roles")

        with (
            transaction.atomic(),
            patch("care.emr.api.viewsets.patient.PatientCreateLock", _NoOpLock),
            patch(
                "care.emr.api.viewsets.encounter.FacilityEncounterCreateLock",
                _NoOpLock,
            ),
            warnings.catch_warnings(),
        ):
            warnings.filterwarnings(
                "ignore",
                message=r".*received a naive datetime.*",
                category=RuntimeWarning,
            )

            actor = _resolve_actor(actor_user)
            client = _SecureAPIClient()
            client.force_authenticate(user=actor)

            fixture_base = base_cls(client)
            fixture_base.user = actor
            yield fixture_base
    finally:
        audit_logger.setLevel(original_level)
