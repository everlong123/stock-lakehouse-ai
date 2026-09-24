"""Pipeline trigger endpoint."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, get_pipeline_service
from app.schemas.common import ok
from app.schemas.stock import PipelineRunRequest
from app.services.pipeline_service import PipelineService

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


@router.post("/run")
def run_pipeline(
    payload: PipelineRunRequest,
    db: Session | None = Depends(get_db),
    service: PipelineService = Depends(get_pipeline_service),
) -> dict:
    result = service.run(payload.symbol.upper(), payload.interval, payload.source, db=db)
    return ok(result, message="Pipeline completed.")
