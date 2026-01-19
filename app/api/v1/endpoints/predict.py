from datetime import datetime

from fastapi import APIRouter, Query, HTTPException, status

from app.api.deps import DbSession
from app.core.permissions import CurrentUser
from app.schemas.predict import PredictListResponse
from app.services.predict_service import PredictService
from app.utils.market_time import is_market_open

router = APIRouter()


@router.get("", response_model=PredictListResponse, status_code=status.HTTP_200_OK)
async def get_predict_list(
    db: DbSession,
    date: str = Query(default=datetime.now().strftime("%Y-%m-%d"), description="조회할 날짜 (YYYY-MM-DD)"),
):
    """예측 목록 조회"""
    service = PredictService(db)

    try:
        predict_list = await service.get_predict_by_type_all(date)
        market_is_open = is_market_open()
        
        return PredictListResponse(
            is_market_open=market_is_open,
            data=predict_list
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"잘못된 날짜 형식입니다: {str(e)}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )