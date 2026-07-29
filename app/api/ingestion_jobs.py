from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_ingestion_repository, get_tenant_context
from rag.errors import NotFoundError, ValidationError
from rag.ingestion.repository import IngestionRepository
from rag.schemas import IngestionJobResponse, TenantContext

router = APIRouter(prefix="/v1/ingestion-jobs", tags=["ingestion-jobs"])


@router.get("/{job_id}", response_model=IngestionJobResponse)
async def get_job(
    job_id: str,
    tenant: Annotated[TenantContext, Depends(get_tenant_context)],
    repository: Annotated[IngestionRepository, Depends(get_ingestion_repository)],
) -> IngestionJobResponse:
    job = await repository.get_job(tenant, job_id)
    if job is None:
        raise NotFoundError("ingestion job not found")
    return job


@router.post("/{job_id}/retry", response_model=IngestionJobResponse)
async def retry_job(
    job_id: str,
    tenant: Annotated[TenantContext, Depends(get_tenant_context)],
    repository: Annotated[IngestionRepository, Depends(get_ingestion_repository)],
) -> IngestionJobResponse:
    if not await repository.retry_job(tenant, job_id):
        raise ValidationError("ingestion job cannot be retried")
    job = await repository.get_job(tenant, job_id)
    if job is None:
        raise NotFoundError("ingestion job not found")
    return job
