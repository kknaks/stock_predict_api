from fastapi import APIRouter, Query
from datetime import datetime

from app.api.deps import DbSession
from app.core.permissions import CurrentUser

from app.services.history_sevice import HistoryService


router = APIRouter()

@router.get("", response_model=HistoryResponse, status_code=status.HTTP_200_OK)
async def get_history(
    db: DbSession,
    current_user: CurrentUser,
    date: str = Query(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d"),
        description="조회할 날짜 (YYYY-MM-DD)"
    ),
):
    service = HistoryService(db)
    result = await service.get_monthly_history(current_user.uid, date)
    return result