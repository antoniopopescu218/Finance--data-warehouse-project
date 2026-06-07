from fastapi import APIRouter, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, ConfigDict

from api.deps import get_db
from storage.repository import get_source, list_sources

router = APIRouter(prefix="/sources", tags=["sources"])


class SourceSummary(BaseModel):
    source_id: str
    name: str


class SourceDetail(BaseModel):
    model_config = ConfigDict(extra="allow")

    source_id: str
    name: str
    description: str | None = None
    api_endpoint: str | None = None


@router.get("", operation_id="list_sources", response_model=list[SourceSummary])
async def list_sources_endpoint(db: AsyncIOMotorDatabase = Depends(get_db)) -> list:
    """Return a summary list of all registered data sources.

    Each item includes source_id and name.
    Use GET /sources/{source_id} for full details.
    """
    return await list_sources(db)


@router.get("/{source_id}", operation_id="get_source", response_model=SourceDetail)
async def get_source_endpoint(
    source_id: str, db: AsyncIOMotorDatabase = Depends(get_db)
) -> dict:
    """Return full details of a single data source.

    Returns 404 if the source_id is not registered.
    """
    source = await get_source(db, source_id)
    if not source:
        raise HTTPException(status_code=404, detail=f"Source '{source_id}' not found")
    return source
