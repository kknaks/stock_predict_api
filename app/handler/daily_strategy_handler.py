"""
Daily Strategy Message Handler

Kafka에서 수신한 일일 전략 메시지를 처리하고 데이터베이스에 저장
같은 날 같은 user_strategy_id에 대해 기존 데이터가 있으면 머지 (거래 기록 보존)
"""

import logging
from typing import Optional, List, Dict

from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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

    @staticmethod
    def _has_trading_data(stock: DailyStrategyStockModel) -> bool:
        """종목에 매수/매도 거래 기록이 있는지 확인"""
        return (
            stock.buy_price is not None
            or stock.buy_quantity is not None
            or stock.sell_price is not None
            or stock.sell_quantity is not None
        )

    async def handle_daily_strategy(self, message: DailyStrategyMessage) -> None:
        """
        일일 전략 메시지 처리 및 데이터베이스 저장 (Merge)

        같은 날 같은 user_strategy_id에 대해:
        - 기존 데이터가 없으면: 새로 생성
        - 기존 데이터가 있으면: 머지 (거래 기록 보존)
          - 거래 기록(buy/sell)이 있는 종목: 보존 (target 정보만 업데이트)
          - 거래 기록이 없는 기존 종목: target 정보 업데이트
          - 새 종목: 추가

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
            total_stocks_added = 0
            total_stocks_updated = 0
            total_stocks_preserved = 0
            updated_strategies = 0
            created_strategies = 0

            message_date = message.timestamp.date()

            # 각 사용자별로 처리
            for user_strategies in message.strategies_by_user:
                user_id = user_strategies.user_id

                # 각 전략별로 처리
                for strategy in user_strategies.strategies:
                    # 같은 날 같은 user_strategy_id로 기존 DailyStrategy 조회 (stocks 포함)
                    stmt = (
                        select(DailyStrategyModel)
                        .options(selectinload(DailyStrategyModel.stocks))
                        .where(
                            DailyStrategyModel.user_strategy_id == strategy.user_strategy_id,
                            func.date(DailyStrategyModel.timestamp) == message_date,
                        )
                    )
                    result = await session.execute(stmt)
                    existing_daily_strategy = result.scalar_one_or_none()

                    if existing_daily_strategy:
                        # 기존 데이터 있음 -> 머지
                        daily_strategy = existing_daily_strategy
                        daily_strategy.timestamp = message.timestamp

                        # 기존 종목을 stock_code 기준 dict로 변환
                        existing_stocks: Dict[str, DailyStrategyStockModel] = {
                            s.stock_code: s for s in daily_strategy.stocks
                        }

                        # 메시지의 종목 코드 set
                        incoming_stock_codes = {
                            s.stock_code for s in strategy.stocks
                        }

                        # 거래 기록 없는 기존 종목 중 메시지에 없는 것은 삭제
                        stocks_to_delete = []
                        for stock_code, existing_stock in existing_stocks.items():
                            if stock_code not in incoming_stock_codes:
                                if not self._has_trading_data(existing_stock):
                                    stocks_to_delete.append(existing_stock.id)
                                else:
                                    total_stocks_preserved += 1
                                    logger.debug(
                                        f"Preserving traded stock not in message: "
                                        f"stock_code={stock_code}"
                                    )

                        if stocks_to_delete:
                            await session.execute(
                                delete(DailyStrategyStockModel).where(
                                    DailyStrategyStockModel.id.in_(stocks_to_delete)
                                )
                            )

                        # 메시지의 각 종목 처리
                        for stock_data in strategy.stocks:
                            existing_stock = existing_stocks.get(stock_data.stock_code)

                            if existing_stock:
                                if self._has_trading_data(existing_stock):
                                    # 거래 기록 있음 → target 정보만 업데이트, 거래 기록 보존
                                    existing_stock.target_price = stock_data.target_price
                                    existing_stock.target_quantity = stock_data.target_quantity
                                    existing_stock.target_sell_price = stock_data.target_sell_price
                                    existing_stock.stop_loss_price = stock_data.stop_loss_price
                                    total_stocks_preserved += 1
                                    logger.debug(
                                        f"Preserved traded stock: "
                                        f"stock_code={stock_data.stock_code}, "
                                        f"buy_price={existing_stock.buy_price}"
                                    )
                                else:
                                    # 거래 기록 없음 → 전체 업데이트
                                    existing_stock.stock_name = stock_data.stock_name
                                    existing_stock.exchange = stock_data.exchange
                                    existing_stock.stock_open = float(stock_data.stock_open)
                                    existing_stock.target_price = stock_data.target_price
                                    existing_stock.target_quantity = stock_data.target_quantity
                                    existing_stock.target_sell_price = stock_data.target_sell_price
                                    existing_stock.stop_loss_price = stock_data.stop_loss_price
                                    total_stocks_updated += 1
                            else:
                                # 새 종목 추가
                                new_stock = DailyStrategyStockModel(
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
                                session.add(new_stock)
                                total_stocks_added += 1

                        updated_strategies += 1
                        logger.debug(
                            f"Merged DailyStrategy: "
                            f"id={daily_strategy.id}, "
                            f"user_strategy_id={strategy.user_strategy_id}, "
                            f"preserved={total_stocks_preserved}, "
                            f"updated={total_stocks_updated}, "
                            f"added={total_stocks_added}"
                        )
                    else:
                        # 새로 생성
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
                                stock_open=float(stock_data.stock_open),
                                target_price=stock_data.target_price,
                                target_quantity=stock_data.target_quantity,
                                target_sell_price=stock_data.target_sell_price,
                                stop_loss_price=stock_data.stop_loss_price,
                            )
                            session.add(daily_strategy_stock)
                            total_stocks_added += 1

                        created_strategies += 1
                        logger.debug(
                            f"Creating new DailyStrategy: "
                            f"id={daily_strategy.id}, user_strategy_id={strategy.user_strategy_id}"
                        )

                    total_strategies += 1

            # 커밋
            await session.commit()

            logger.info(
                f"Successfully saved daily strategy: "
                f"{total_strategies} strategies "
                f"({created_strategies} created, {updated_strategies} merged), "
                f"stocks: {total_stocks_added} added, "
                f"{total_stocks_updated} updated, "
                f"{total_stocks_preserved} preserved (with trading data)"
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
