"""
주문 결과 메시지 핸들러

주문 접수 및 체결통보 메시지를 처리하여 Order와 OrderExecution 테이블에 저장
"""

import logging
from typing import Optional
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.config.db_connections import get_session_factory
from app.schemas.order_signal import OrderResultMessage
from app.repositories.stock_repository import StockRepository
from app.database.database.strategy import (
    DailyStrategy as DailyStrategyModel,
    DailyStrategyStock as DailyStrategyStockModel,
    Order as OrderModel,
    OrderExecution as OrderExecutionModel,
    OrderStatus,
    OrderType,
)

logger = logging.getLogger(__name__)


class OrderResultHandler:
    """주문 결과 메시지 핸들러"""

    def __init__(self):
        self._session_factory = get_session_factory()

    async def handle_order_result(self, message: OrderResultMessage) -> None:
        """
        주문 결과 메시지 처리 및 데이터베이스 저장
        
        주문 접수(status: "ordered") 시:
            - Order 테이블에 주문 내역 저장
        
        체결통보(status: "partially_executed" or "executed") 시:
            - 기존 Order 조회 및 업데이트
            - OrderExecution 테이블에 체결 내역 저장
        """
        logger.info(
            f"Processing order result message: order_no={message.order_no}, "
            f"status={message.status}, user_strategy_id={message.user_strategy_id}"
        )

        session: Optional[AsyncSession] = None
        try:
            session = self._session_factory()
            stock_repository = StockRepository(session)

            # timestamp를 datetime으로 변환
            if isinstance(message.timestamp, str):
                timestamp = datetime.fromisoformat(message.timestamp.replace('Z', '+00:00'))
            else:
                timestamp = message.timestamp

            # DailyStrategyStock 찾기
            order_date = timestamp.date()
            daily_strategy = await stock_repository.get_daily_strategy_with_stocks(
                message.user_strategy_id, order_date
            )

            if not daily_strategy:
                logger.warning(
                    f"DailyStrategy not found: user_strategy_id={message.user_strategy_id}, "
                    f"date={order_date}"
                )
                return

            # 해당 종목 찾기
            daily_strategy_stock = None
            for stock in daily_strategy.stocks:
                if stock.stock_code == message.stock_code:
                    daily_strategy_stock = stock
                    break

            if not daily_strategy_stock:
                logger.warning(
                    f"DailyStrategyStock not found: stock_code={message.stock_code}, "
                    f"daily_strategy_id={daily_strategy.id}"
                )
                return

            # 주문번호로 기존 Order 조회 (SQLAlchemy 2.0 스타일)
            from sqlalchemy import select
            stmt = select(OrderModel).where(OrderModel.order_no == message.order_no)
            result = await session.execute(stmt)
            existing_order = result.scalar_one_or_none()

            if message.status == "ordered":
                # 주문 접수: Order 테이블에 새 레코드 생성
                if existing_order:
                    logger.warning(
                        f"Order already exists: order_no={message.order_no}, updating..."
                    )
                    # 기존 주문이 있으면 업데이트 (재수신 경우 대비)
                    existing_order.order_quantity = message.order_quantity
                    existing_order.order_price = message.order_price
                    existing_order.order_dvsn = message.order_dvsn
                    existing_order.status = OrderStatus.ORDERED
                    existing_order.total_executed_quantity = 0
                    existing_order.total_executed_price = 0.0
                    existing_order.remaining_quantity = message.order_quantity
                    existing_order.is_fully_executed = False
                    existing_order.ordered_at = timestamp
                else:
                    # 새 주문 생성
                    new_order = OrderModel(
                        daily_strategy_stock_id=daily_strategy_stock.id,
                        order_no=message.order_no,
                        order_type=OrderType.BUY if message.order_type == "BUY" else OrderType.SELL,
                        order_quantity=message.order_quantity,
                        order_price=message.order_price,
                        order_dvsn=message.order_dvsn,
                        account_no=message.account_no,
                        is_mock=message.is_mock,
                        status=OrderStatus.ORDERED,
                        total_executed_quantity=0,
                        total_executed_price=0.0,
                        remaining_quantity=message.order_quantity,
                        is_fully_executed=False,
                        ordered_at=timestamp,
                    )
                    session.add(new_order)
                    logger.info(
                        f"Created new order: order_no={message.order_no}, "
                        f"order_type={message.order_type}, quantity={message.order_quantity}"
                    )
            else:
                # 체결통보: 기존 Order 업데이트 및 OrderExecution 생성
                if not existing_order:
                    logger.warning(
                        f"Order not found for execution: order_no={message.order_no}, "
                        f"creating order first..."
                    )
                    # 주문이 없으면 먼저 생성 (체결통보가 먼저 도착한 경우)
                    existing_order = OrderModel(
                        daily_strategy_stock_id=daily_strategy_stock.id,
                        order_no=message.order_no,
                        order_type=OrderType.BUY if message.order_type == "BUY" else OrderType.SELL,
                        order_quantity=message.order_quantity,
                        order_price=message.order_price,
                        order_dvsn=message.order_dvsn,
                        account_no=message.account_no,
                        is_mock=message.is_mock,
                        status=OrderStatus.PARTIALLY_EXECUTED if message.status == "partially_executed" else OrderStatus.EXECUTED,
                        total_executed_quantity=message.total_executed_quantity,
                        total_executed_price=message.total_executed_price,
                        remaining_quantity=message.remaining_quantity,
                        is_fully_executed=message.is_fully_executed,
                        ordered_at=timestamp,
                    )
                    session.add(existing_order)
                    await session.flush()  # ID를 얻기 위해 flush
                else:
                    # 기존 주문 업데이트
                    existing_order.status = OrderStatus.PARTIALLY_EXECUTED if message.status == "partially_executed" else OrderStatus.EXECUTED
                    existing_order.total_executed_quantity = message.total_executed_quantity
                    existing_order.total_executed_price = message.total_executed_price
                    existing_order.remaining_quantity = message.remaining_quantity
                    existing_order.is_fully_executed = message.is_fully_executed

                # 체결 순서 계산 (기존 체결 건수 조회)
                execution_stmt = select(OrderExecutionModel).where(
                    OrderExecutionModel.order_id == existing_order.id
                ).order_by(OrderExecutionModel.execution_sequence.desc())
                execution_result = await session.execute(execution_stmt)
                last_execution = execution_result.scalar_one_or_none()
                execution_sequence = (last_execution.execution_sequence + 1) if last_execution else 1

                # OrderExecution 생성
                new_execution = OrderExecutionModel(
                    order_id=existing_order.id,
                    execution_sequence=execution_sequence,
                    executed_quantity=message.executed_quantity,
                    executed_price=message.executed_price,
                    total_executed_quantity_after=message.total_executed_quantity,
                    total_executed_price_after=message.total_executed_price,
                    remaining_quantity_after=message.remaining_quantity,
                    is_fully_executed_after=message.is_fully_executed,
                    executed_at=timestamp,
                )
                session.add(new_execution)
                logger.info(
                    f"Created order execution: order_no={message.order_no}, "
                    f"sequence={execution_sequence}, "
                    f"executed_quantity={message.executed_quantity}, "
                    f"total_executed_quantity={message.total_executed_quantity}"
                )
                
                # 전량 체결 완료 시 DailyStrategyStock 업데이트
                if message.is_fully_executed:
                    await self._update_daily_strategy_stock(
                        session,
                        daily_strategy_stock,
                        daily_strategy,
                        existing_order,
                        message.order_type
                    )

            await session.commit()
            logger.info(f"Successfully processed order result: order_no={message.order_no}")

        except Exception as e:
            logger.error(f"Error processing order result: {e}", exc_info=True)
            if session:
                await session.rollback()
            raise
        finally:
            if session:
                await session.close()

    async def _update_daily_strategy_stock(
        self,
        session: AsyncSession,
        daily_strategy_stock: DailyStrategyStockModel,
        daily_strategy: DailyStrategyModel,
        order: OrderModel,
        order_type: str
    ) -> None:
        """
        전량 체결 완료 시 DailyStrategyStock 및 DailyStrategy 업데이트
        
        Args:
            session: DB 세션
            daily_strategy_stock: DailyStrategyStock 객체
            daily_strategy: DailyStrategy 객체
            order: Order 객체 (전량 체결 완료된 주문)
            order_type: "BUY" or "SELL"
        """
        if order_type == "BUY":
            # 매수 전량 체결 완료
            daily_strategy_stock.buy_price = order.total_executed_price  # 가중평균 체결 가격
            daily_strategy_stock.buy_quantity = float(order.total_executed_quantity)  # 체결 수량
            
            # DailyStrategy의 총 매수금액 업데이트
            if daily_strategy.buy_amount is None:
                daily_strategy.buy_amount = 0.0
            # 기존 매수금액 제거 후 새로 계산 (중복 방지)
            # 실제로는 Order 테이블에서 집계하는 것이 더 정확하지만, 
            # 여기서는 간단히 추가만 함
            buy_amount = order.total_executed_price * order.total_executed_quantity
            daily_strategy.buy_amount += buy_amount
            
            logger.info(
                f"Updated DailyStrategyStock buy info: stock_code={daily_strategy_stock.stock_code}, "
                f"buy_price={order.total_executed_price:.2f}, "
                f"buy_quantity={order.total_executed_quantity}"
            )
        elif order_type == "SELL":
            # 매도 전량 체결 완료
            daily_strategy_stock.sell_price = order.total_executed_price  # 가중평균 체결 가격
            daily_strategy_stock.sell_quantity = float(order.total_executed_quantity)  # 체결 수량
            
            # 수익률 계산 (매수가가 있는 경우에만)
            if daily_strategy_stock.buy_price and daily_strategy_stock.buy_quantity:
                profit_rate = ((order.total_executed_price - daily_strategy_stock.buy_price) / daily_strategy_stock.buy_price) * 100
                daily_strategy_stock.profit_rate = profit_rate
                
                # 수익금액 계산 (실제 체결 수량 기준)
                actual_quantity = min(order.total_executed_quantity, int(daily_strategy_stock.buy_quantity))
                profit_amount = (order.total_executed_price - daily_strategy_stock.buy_price) * actual_quantity
                
                # DailyStrategy의 총 매도금액 업데이트
                if daily_strategy.sell_amount is None:
                    daily_strategy.sell_amount = 0.0
                sell_amount = order.total_executed_price * order.total_executed_quantity
                daily_strategy.sell_amount += sell_amount
                
                # DailyStrategy의 총 수익금액 업데이트
                if daily_strategy.total_profit_amount is None:
                    daily_strategy.total_profit_amount = 0.0
                daily_strategy.total_profit_amount += profit_amount
                
                # DailyStrategy의 총 수익률 계산 (가중 평균)
                # 모든 종목의 매수금액 합계로 계산
                from sqlalchemy import select, func
                stmt = select(
                    func.sum(DailyStrategyStockModel.buy_price * DailyStrategyStockModel.buy_quantity)
                ).where(
                    DailyStrategyStockModel.daily_strategy_id == daily_strategy.id,
                    DailyStrategyStockModel.buy_price.isnot(None),
                    DailyStrategyStockModel.buy_quantity.isnot(None)
                )
                result = await session.execute(stmt)
                total_buy_amount = result.scalar() or 0.0
                
                if total_buy_amount > 0:
                    daily_strategy.total_profit_rate = (
                        daily_strategy.total_profit_amount / total_buy_amount
                    ) * 100
                
                logger.info(
                    f"Updated DailyStrategyStock sell info: stock_code={daily_strategy_stock.stock_code}, "
                    f"sell_price={order.total_executed_price:.2f}, "
                    f"sell_quantity={order.total_executed_quantity}, "
                    f"profit_rate={profit_rate:.2f}%, "
                    f"profit_amount={profit_amount:.2f}"
                )
            else:
                logger.warning(
                    f"SELL execution completed but buy_price/buy_quantity not set: "
                    f"stock_code={daily_strategy_stock.stock_code}"
                )
                # 매수가 정보가 없어도 매도 정보는 저장
                if daily_strategy.sell_amount is None:
                    daily_strategy.sell_amount = 0.0
                sell_amount = order.total_executed_price * order.total_executed_quantity
                daily_strategy.sell_amount += sell_amount


_handler_instance: Optional[OrderResultHandler] = None


def get_order_result_handler() -> OrderResultHandler:
    """Order Result Handler 싱글톤 인스턴스 반환"""
    global _handler_instance
    if _handler_instance is None:
        _handler_instance = OrderResultHandler()
    return _handler_instance