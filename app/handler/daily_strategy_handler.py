"""
Daily Strategy Message Handler

Kafka에서 수신한 일일 전략 메시지를 처리하고 데이터베이스에 저장
같은 날 같은 user_strategy_id에 대해 기존 데이터가 있으면 업데이트 (upsert)
"""

import logging
from typing import Optional, List

from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.db_connections import get_session_factory
from app.schemas.daily_strategy import DailyStrategyMessage
from app.database.database.strategy import (
    DailyStrategy as DailyStrategyModel,
    DailyStrategyStock as DailyStrategyStockModel,
)

logger = logging.getLogger(__name__)


class DailyStrategyHandler:
    """일일 전략 메시지 핸들러"""

    def __init__(self):
        self._session_factory = get_session_factory()

    async def handle_daily_strategy(self, message: DailyStrategyMessage) -> None:
        """
        일일 전략 메시지 처리 및 데이터베이스 저장 (Upsert)

        같은 날 같은 user_strategy_id에 대해:
        - 기존 데이터가 있으면: 기존 stocks 삭제 후 새로 추가
        - 기존 데이터가 없으면: 새로 생성

        Args:
            message: Kafka에서 수신한 일일 전략 메시지
        """
        logger.info(
            f"Processing daily strategy message: "
            f"timestamp={message.timestamp}, "
            f"users={len(message.strategies_by_user)}"
        )

        session: Optional[AsyncSession] = None
        try:
            session = self._session_factory()

            total_strategies = 0
            total_stocks = 0
            updated_strategies = 0
            created_strategies = 0

            message_date = message.timestamp.date()

            # 각 사용자별로 처리
            for user_strategies in message.strategies_by_user:
                user_id = user_strategies.user_id

                # 각 전략별로 처리
                for strategy in user_strategies.strategies:
                    # 같은 날 같은 user_strategy_id로 기존 DailyStrategy 조회
                    stmt = select(DailyStrategyModel).where(
                        DailyStrategyModel.user_strategy_id == strategy.user_strategy_id,
                        func.date(DailyStrategyModel.timestamp) == message_date
                    )
                    result = await session.execute(stmt)
                    existing_daily_strategy = result.scalar_one_or_none()

                    if existing_daily_strategy:
                        # 기존 데이터 있음 -> 업데이트
                        daily_strategy = existing_daily_strategy
                        daily_strategy.timestamp = message.timestamp  # 타임스탬프 업데이트

                        # 기존 stocks 삭제 (cascade 안 되는 경우 대비)
                        await session.execute(
                            delete(DailyStrategyStockModel).where(
                                DailyStrategyStockModel.daily_strategy_id == daily_strategy.id
                            )
                        )
                        await session.flush()

                        updated_strategies += 1
                        logger.debug(
                            f"Updating existing DailyStrategy: "
                            f"id={daily_strategy.id}, user_strategy_id={strategy.user_strategy_id}"
                        )
                    else:
                        # 새로 생성
                        daily_strategy = DailyStrategyModel(
                            user_strategy_id=strategy.user_strategy_id,
                            timestamp=message.timestamp,
                        )
                        session.add(daily_strategy)
                        await session.flush()  # ID를 얻기 위해 flush

                        created_strategies += 1
                        logger.debug(
                            f"Creating new DailyStrategy: "
                            f"id={daily_strategy.id}, user_strategy_id={strategy.user_strategy_id}"
                        )

                    # DailyStrategyStock 생성
                    for stock_data in strategy.stocks:
                        daily_strategy_stock = DailyStrategyStockModel(
                            daily_strategy_id=daily_strategy.id,
                            stock_code=stock_data.stock_code,
                            stock_name=stock_data.stock_name,
                            exchange=stock_data.exchange,
                            stock_open=float(stock_data.stock_open),
                            target_price=stock_data.target_price,
                            target_quantity=stock_data.target_quantity,
                            target_sell_price=stock_data.target_sell_price,
                            stop_loss_price=stock_data.stop_loss_price,
                        )
                        session.add(daily_strategy_stock)
                        total_stocks += 1

                    total_strategies += 1

            # 커밋
            await session.commit()

            logger.info(
                f"Successfully saved daily strategy: "
                f"{total_strategies} strategies ({created_strategies} created, {updated_strategies} updated), "
                f"{total_stocks} stocks"
            )

        except Exception as e:
            if session:
                await session.rollback()
            logger.error(
                f"Error processing daily strategy message: {e}",
                exc_info=True
            )
            raise
        finally:
            if session:
                await session.close()


# 싱글톤 인스턴스
_handler_instance: Optional[DailyStrategyHandler] = None


def get_daily_strategy_handler() -> DailyStrategyHandler:
    """Daily Strategy Handler 싱글톤 인스턴스 반환"""
    global _handler_instance
    if _handler_instance is None:
        _handler_instance = DailyStrategyHandler()
    return _handler_instance
