"""
주식 관련 API 엔드포인트
"""

from fastapi import APIRouter, HTTPException, status, Query

from app.api.deps import DbSession
from app.core.permissions import CurrentUser
from app.schemas.stocks import (
    StockMetadataResponse,
)
from app.services.stock_service import StockService

router = APIRouter()

@router.get("/metadata", response_model=StockMetadataResponse, status_code=status.HTTP_200_OK)
async def get_metadata(
    db: DbSession,
    stock_code: str = Query(..., description="조회할 종목 코드"),
):
    """종목 메타 정보 조회"""
    service = StockService(db)
    metadata = await service.get_metadata(stock_code)
    if not metadata:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"종목 코드 '{stock_code}'에 해당하는 메타 정보를 찾을 수 없습니다.",
        )
    return metadata