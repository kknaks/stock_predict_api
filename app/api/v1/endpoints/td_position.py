from datetime import datetime

from fastapi import APIRouter, Query, status

from app.api.deps import DbSession
from app.core.permissions import CurrentUser
from app.services.strategy_service import StrategyService
from app.schemas.td_position import TdPositionResponse

router = APIRouter()


@router.get("", response_model=TdPositionResponse, status_code=status.HTTP_200_OK)
async def get_td_position(
    db: DbSession,
    current_user: CurrentUser,
    date: str = Query(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d"),
        description="조회할 날짜 (YYYY-MM-DD)",
        examples=["2026-01-20"],
    ),
):
    """
    당일 포지션 조회

    사용자의 모든 계좌별 당일 매수/매도 현황을 조회합니다.

    - **date**: 조회할 날짜 (기본값: 오늘)

    응답 정보:
    - **accounts**: 계좌별 포지션 목록
        - account_id: 계좌 ID
        - account_number: 계좌번호
        - account_name: 계좌명
        - summary: 요약 정보 (총 매입금액, 평가금액, 손익, 수익률)
        - positions: 종목별 상세 정보
    """
    service = StrategyService(db)
    return await service.get_td_position(current_user.uid, date)
