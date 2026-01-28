"""
Stock Repository - DB 접근 레이어
"""

from datetime import date, datetime
from typing import Optional
from sqlalchemy import select, func, cast, Date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.database.strategy import (
    UserStrategy,
    StrategyInfo,
    StrategyStatus,
    DailyStrategy,
)
from app.database.database.stocks import StockPrices, StockMetadata


class StockRepository:
    """Stock DB 접근"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_strategy_info(self, strategy_id: int) -> StrategyInfo | None:
        """전략 정보 조회"""
        result = await self.db.execute(
            select(StrategyInfo).where(StrategyInfo.id == strategy_id)
        )
        return result.scalar_one_or_none()

    async def get_user_strategy(self, user_id: int, strategy_id: int) -> UserStrategy | None:
        """사용자 전략 조회"""
        result = await self.db.execute(
            select(UserStrategy).where(
                UserStrategy.user_id == user_id,
                UserStrategy.strategy_id == strategy_id
            )
        )
        return result.scalar_one_or_none()

    async def get_user_strategy_with_info(self, user_strategy_id: int) -> UserStrategy | None:
        """사용자 전략 조회 (전략 정보 포함)"""
        result = await self.db.execute(
            select(UserStrategy)
            .options(selectinload(UserStrategy.strategy_info))
            .where(UserStrategy.id == user_strategy_id)
        )
        return result.scalar_one_or_none()

    async def get_user_strategies(self, user_id: int) -> list[UserStrategy]:
        """사용자의 전략 목록 조회"""
        result = await self.db.execute(
            select(UserStrategy)
            .options(selectinload(UserStrategy.strategy_info))
            .where(UserStrategy.user_id == user_id)
        )
        return list(result.scalars().all())

    async def create_user_strategy(self, user_strategy: UserStrategy) -> UserStrategy:
        """사용자 전략 생성"""
        self.db.add(user_strategy)
        await self.db.flush()
        return await self.get_user_strategy_with_info(user_strategy.id)

    async def update_user_strategy(
        self,
        user_strategy: UserStrategy,
        ls_ratio: float | None = None,
        tp_ratio: float | None = None,
        status: StrategyStatus | str | None = None,
        is_auto: bool | None = None,
    ) -> UserStrategy:
        """사용자 전략 업데이트"""
        if ls_ratio is not None:
            user_strategy.ls_ratio = ls_ratio
        if tp_ratio is not None:
            user_strategy.tp_ratio = tp_ratio
        if status is not None:
            # 문자열로 전달된 경우 StrategyStatus Enum으로 변환
            if isinstance(status, str):
                user_strategy.status = StrategyStatus(status)
            else:
                user_strategy.status = status
        if is_auto is not None:
            user_strategy.is_auto = is_auto
        
        await self.db.flush()
        return await self.get_user_strategy_with_info(user_strategy.id)

    async def delete_user_strategy(self, user_strategy: UserStrategy) -> None:
        """사용자 전략 삭제"""
        await self.db.delete(user_strategy)
        await self.db.flush()

    async def get_daily_strategy_with_stocks(
        self, user_strategy_id: int, order_date: date
    ) -> DailyStrategy | None:
        """일일 전략 조회 (종목, UserStrategy, Account 포함)"""
        # created_at은 DateTime이므로 날짜 부분만 비교
        # 또는 timestamp 필드의 날짜 부분을 비교
        # 같은 날짜에 여러 레코드가 있을 수 있으므로 가장 최근 레코드를 선택
        result = await self.db.execute(
            select(DailyStrategy)
            .options(
                selectinload(DailyStrategy.stocks),
                selectinload(DailyStrategy.user_strategy).selectinload(UserStrategy.account),
            )
            .where(
                DailyStrategy.user_strategy_id == user_strategy_id,
                func.date(DailyStrategy.timestamp) == order_date
            )
            .order_by(DailyStrategy.timestamp.desc())
            .limit(1)
        )
        return result.scalars().first()

    async def get_closing_price(self, stock_code: str, target_date: date) -> Optional[float]:
        """
        종목의 특정 날짜 종가 조회
        
        Args:
            stock_code: 종목 코드
            target_date: 조회할 날짜
        
        Returns:
            종가 또는 None (데이터가 없으면)
        """
        result = await self.db.execute(
            select(StockPrices.close)
            .where(
                StockPrices.symbol == stock_code,
                StockPrices.date == target_date
            )
        )
        return result.scalar_one_or_none()

    async def get_metadata(self, stock_code: str) -> StockMetadata | None:
        """종목 메타 정보 조회"""
        result = await self.db.execute(
            select(StockMetadata).where(StockMetadata.symbol == stock_code)
        )
        return result.scalar_one_or_none()
