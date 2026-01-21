from fastapi import APIRouter, Query, status
from datetime import datetime

from app.api.deps import DbSession
from app.core.permissions import CurrentUser
from app.schemas.history import HistoryResponse
from app.services.history_sevice import HistoryService


router = APIRouter()


@router.get("", response_model=HistoryResponse, status_code=status.HTTP_200_OK)
async def get_history(
    db: DbSession,
    current_user: CurrentUser,
    date: str = Query(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d"),
        description="조회할 날짜 (YYYY-MM-DD) - 해당 월의 전체 데이터 반환",
        examples=["2026-01-20"],
    ),
):
    """
    월별 히스토리 조회

    사용자의 모든 계좌별 월간 수익률 데이터를 조회합니다.

    - **date**: 조회 기준 날짜 (해당 월 전체 데이터 반환)

    응답 정보:
    - **accounts**: 계좌별 히스토리 목록
        - account_id: 계좌 ID
        - account_number: 계좌번호
        - account_name: 계좌명
        - total_profit_rate: 월간 총 수익률 (%)
        - total_profit_amount: 월간 총 수익금
        - trading_days: 거래일 수
        - daily_histories: 일별 상세 데이터
    """
    service = HistoryService(db)
    result = await service.get_monthly_history(current_user.uid, date)
    return result
