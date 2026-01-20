from datetime import date
from typing import Optional, List, Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.database.database.strategy import (
    DailyStrategy,
    DailyStrategyStock,
    UserStrategy,
    Order,
    OrderExecution,
    StrategyStatus,
    OrderStatus,
    OrderType,
)


class StrategyRepository:
    """Strategy DB 접근"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_user_active_strategies(self, user_id: int) -> List[UserStrategy]:
        """사용자의 활성 전략 목록 조회"""
        result = await self.db.execute(
            select(UserStrategy).where(
                UserStrategy.user_id == user_id,
                UserStrategy.status == StrategyStatus.ACTIVE,
            )
        )
        return list(result.scalars().all())

    async def get_daily_strategy_by_date(
        self,
        user_strategy_id: int,
        target_date: date
    ) -> Optional[DailyStrategy]:
        """특정 날짜의 DailyStrategy 조회 (stocks 포함)"""
        result = await self.db.execute(
            select(DailyStrategy)
            .options(
                selectinload(DailyStrategy.stocks).selectinload(DailyStrategyStock.orders)
            )
            .where(
                DailyStrategy.user_strategy_id == user_strategy_id,
                func.date(DailyStrategy.timestamp) == target_date,
            )
        )
        return result.scalar_one_or_none()

    async def get_td_position(
        self,
        user_id: int,
        target_date: date
    ) -> Tuple[Optional[DailyStrategy], List[DailyStrategyStock]]:
        """
        당일 포지션 조회

        Args:
            user_id: 사용자 ID
            target_date: 조회 날짜

        Returns:
            (DailyStrategy, List[DailyStrategyStock]) 튜플
        """
        # 1. 사용자의 활성 전략 조회
        user_strategies = await self.get_user_active_strategies(user_id)

        if not user_strategies:
            return None, []

        # 첫 번째 활성 전략 사용 (추후 여러 전략 지원 시 수정)
        user_strategy = user_strategies[0]

        # 2. 해당 날짜의 DailyStrategy 조회 (stocks, orders 포함)
        daily_strategy = await self.get_daily_strategy_by_date(
            user_strategy.id, target_date
        )

        if not daily_strategy:
            return None, []

        return daily_strategy, list(daily_strategy.stocks)

    async def get_stock_orders(
        self,
        daily_strategy_stock_id: int
    ) -> List[Order]:
        """특정 종목의 주문 내역 조회"""
        result = await self.db.execute(
            select(Order)
            .options(selectinload(Order.executions))
            .where(Order.daily_strategy_stock_id == daily_strategy_stock_id)
            .order_by(Order.ordered_at.desc())
        )
        return list(result.scalars().all())

    async def get_position_summary(
        self,
        daily_strategy_id: int
    ) -> dict:
        """
        포지션 요약 정보 조회 (집계 쿼리)

        Returns:
            {
                'total_buy_amount': float,
                'total_sell_amount': float,
                'total_profit_amount': float,
                'stock_count': int,
                'holding_count': int,
                'sold_count': int
            }
        """
        # 종목별 집계
        result = await self.db.execute(
            select(
                func.count(DailyStrategyStock.id).label('stock_count'),
                func.sum(
                    DailyStrategyStock.buy_price * DailyStrategyStock.buy_quantity
                ).label('total_buy_amount'),
                func.sum(
                    DailyStrategyStock.sell_price * DailyStrategyStock.sell_quantity
                ).label('total_sell_amount'),
                func.count(
                    DailyStrategyStock.id
                ).filter(
                    DailyStrategyStock.sell_quantity.is_(None) |
                    (DailyStrategyStock.sell_quantity == 0)
                ).label('holding_count'),
                func.count(
                    DailyStrategyStock.id
                ).filter(
                    DailyStrategyStock.sell_quantity.isnot(None),
                    DailyStrategyStock.sell_quantity > 0
                ).label('sold_count'),
            ).where(
                DailyStrategyStock.daily_strategy_id == daily_strategy_id
            )
        )

        row = result.one()
        return {
            'stock_count': row.stock_count or 0,
            'total_buy_amount': float(row.total_buy_amount or 0),
            'total_sell_amount': float(row.total_sell_amount or 0),
            'holding_count': row.holding_count or 0,
            'sold_count': row.sold_count or 0,
        }
