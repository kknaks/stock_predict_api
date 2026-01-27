"""
주문 관련 API 엔드포인트
"""

import logging

from fastapi import APIRouter, HTTPException

from app.kafka.producer import get_kafka_producer
from app.api.deps import DbSession
from app.schemas.manual_sell import ManualSellRequest, ManualSellResponse, OrderType
from app.services.strategy_service import StrategyService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/sell", response_model=ManualSellResponse)
async def manual_sell(
    request: ManualSellRequest,
    db: DbSession,
):
    """
    수동 매도 주문

    Kafka로 매도 시그널을 전송합니다.
    - order_type이 LIMIT인 경우 order_price 필수
    - order_quantity 생략 시 전량 매도
    """

    service = StrategyService(db)
    # 지정가 주문인데 가격이 없으면 에러
    if request.order_type == OrderType.LIMIT and request.order_price is None:
        raise HTTPException(
            status_code=400,
            detail="order_price is required for LIMIT order"
        )

    strategy_id = await service.get_user_strategy_id_by_daily(request.daily_strategy_id)
    if not strategy_id:
        raise HTTPException(
            status_code=400,
            detail="strategy_id not found"
        )

    # Kafka 메시지 생성
    message = {
        "user_strategy_id": strategy_id,
        "stock_code": request.stock_code,
        "order_type": request.order_type.value,
    }

    if request.order_price is not None:
        message["order_price"] = request.order_price

    if request.order_quantity is not None:
        message["order_quantity"] = request.order_quantity

    # Kafka 전송
    producer = get_kafka_producer()
    success = await producer.send_manual_sell_signal(message)

    if not success:
        raise HTTPException(
            status_code=500,
            detail="Failed to send sell signal to Kafka"
        )

    return ManualSellResponse(
        success=True,
        message=f"Sell signal sent for {request.stock_code}"
    )
