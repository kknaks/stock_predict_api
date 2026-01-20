from datetime import datetime

from fastapi import APIRouter, HTTPException, status, Query

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

    사용자의 당일 매수/매도 현황을 조회합니다.

    - **date**: 조회할 날짜 (기본값: 오늘)

    응답 정보:
    - **summary**: 요약 정보 (총 매입금액, 평가금액, 손익, 수익률)
    - **positions**: 종목별 상세 정보
        - stock_code: 종목코드
        - stock_name: 종목명
        - buy_price: 매수 평균단가
        - buy_quantity: 매수 수량
        - holding_quantity: 현재 보유수량
        - target_price: 목표가
        - stop_loss_price: 손절가
        - status: 포지션 상태 (holding/target_reached/stop_loss/sold)
        - profit_rate: 수익률 (%)
    """
    service = StrategyService(db)
    result = await service.get_td_position(current_user.uid, date)
    return result
