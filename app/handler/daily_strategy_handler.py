"""
Daily Strategy Message Handler

Kafka에서 수신한 일일 전략 메시지를 처리하고 데이터베이스에 저장
"""

import logging
from typing import Optional

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
        일일 전략 메시지 처리 및 데이터베이스 저장

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

            # 각 사용자별로 처리
            for user_strategies in message.strategies_by_user:
                user_id = user_strategies.user_id
                
                # 각 전략별로 처리
                for strategy in user_strategies.strategies:
                    # DailyStrategy 생성
                    daily_strategy = DailyStrategyModel(
                        user_strategy_id=strategy.user_strategy_id,
                        timestamp=message.timestamp,
                    )
                    session.add(daily_strategy)
                    await session.flush()  # ID를 얻기 위해 flush
                    
                    # DailyStrategyStock 생성
                    for stock_data in strategy.stocks:
                        daily_strategy_stock = DailyStrategyStockModel(
                            daily_strategy_id=daily_strategy.id,
                            stock_code=stock_data.stock_code,
                            stock_name=stock_data.stock_name,
                            exchange=stock_data.exchange,
                            stock_open=float(stock_data.stock_open), # TODO: int로 바꾸기
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
                f"{total_strategies} strategies, "
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
