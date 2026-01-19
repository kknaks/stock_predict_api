from datetime import datetime

from fastapi import APIRouter, Query, HTTPException, status

from app.api.deps import DbSession
from app.core.permissions import CurrentUser
from app.schemas.predict import PredictionItem
from app.services.predict_service import PredictService

router = APIRouter()


@router.get("", response_model=list[PredictionItem], status_code=status.HTTP_200_OK)
async def get_predict_list(
    db: DbSession,
    date: str = Query(default=datetime.now().strftime("%Y-%m-%d"), description="조회할 날짜 (YYYY-MM-DD)"),
):
    """예측 목록 조회"""
    service = PredictService(db)

    try:
        predict_list = await service.get_predict_list(date)
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

    return predict_list