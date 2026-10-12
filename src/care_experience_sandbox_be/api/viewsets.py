from django.http import Http404
from rest_framework import status
from rest_framework.authentication import BasicAuthentication, SessionAuthentication
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from care_experience_sandbox_be.api.permissions import IsSuperUser
from care_experience_sandbox_be.models import SandboxJob
from care_experience_sandbox_be.sandbox.revoke import revoke_sandbox
from care_experience_sandbox_be.tasks import create_sandbox_task

_TRUTHY = {"true", "1", "yes", "y", "on"}


def _as_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in _TRUTHY


def _serialize_job(job, request):
    return {
        "id": str(job.external_id),
        "status": job.status,
        "facility_name": job.facility_name or None,
        "is_facility_empty": job.is_facility_empty,
        "result": job.result or None,
        "error": job.error or None,
        "poll_url": request.build_absolute_uri(f"../{job.external_id}/"),
    }


class SandboxViewSet(GenericViewSet):
    authentication_classes = [BasicAuthentication, SessionAuthentication]
    permission_classes = [IsSuperUser]
    queryset = SandboxJob.objects.all()
    lookup_field = "external_id"

    def create(self, request, *args, **kwargs):
        is_facility_empty = _as_bool(
            request.query_params.get(
                "is_facility_empty", request.data.get("is_facility_empty")
            )
        )
        facility_name = (
            request.data.get("facility_name")
            or request.query_params.get("facility_name")
            or ""
        ).strip()
        # The plugin runs inside Care, so the server is whatever host the request hit.
        server_url = request.build_absolute_uri("/").rstrip("/")
        job = SandboxJob.objects.create(
            is_facility_empty=is_facility_empty,
            facility_name=facility_name,
            server_url=server_url,
            created_by=request.user,
        )
        create_sandbox_task.delay(job.id)
        return Response(
            _serialize_job(job, request), status=status.HTTP_202_ACCEPTED
        )

    def retrieve(self, request, *args, **kwargs):
        job = self.get_object()
        return Response(_serialize_job(job, request))

    def destroy(self, request, *args, **kwargs):
        # Revoke: soft-delete the facility and its sandbox users, then drop the job.
        # Idempotent: the job row is hard-deleted, so retries must not 404.
        try:
            job = self.get_object()
        except Http404:
            return Response(status=status.HTTP_204_NO_CONTENT)
        revoke_sandbox(job)
        SandboxJob.objects.filter(pk=job.pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
