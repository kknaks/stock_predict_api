from datetime import date
from typing import Optional, List, Tuple, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload

from app.database.database.strategy import (
    DailyStrategy,
    DailyStrategyStock,
    UserStrategy,
    Order,
    StrategyStatus,
    StrategyInfo,
    StrategyWeightType,
)


class StrategyRepository:
    """Strategy DB 접근"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_account_active_strategies(self, account_id: int) -> List[UserStrategy]:
        """계좌의 활성 전략 목록 조회"""
        result = await self.db.execute(
            select(UserStrategy).where(
                UserStrategy.account_id == account_id,
                UserStrategy.status == StrategyStatus.ACTIVE,
                UserStrategy.is_deleted == False,
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
        account_id: int,
        target_date: date
    ) -> Tuple[Optional[DailyStrategy], List[DailyStrategyStock]]:
        """
        당일 포지션 조회

        Args:
            account_id: 계좌 ID
            target_date: 조회 날짜

        Returns:
            (DailyStrategy, List[DailyStrategyStock]) 튜플
        """
        # 1. 계좌의 활성 전략 조회
        user_strategies = await self.get_account_active_strategies(account_id)

        if not user_strategies:
            return None, []

        # 첫 번째 활성 전략 사용 (계좌당 하나의 ACTIVE 전략만 가능)
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

    async def get_monthly_daily_strategies(
        self,
        user_strategy_ids: List[int],
        start_date: date,
        end_date: date
    ) -> List[DailyStrategy]:
        """
        월별 DailyStrategy 목록 조회

        Args:
            user_strategy_ids: 사용자 전략 ID 목록
            start_date: 시작일
            end_date: 종료일

        Returns:
            DailyStrategy 목록 (날짜 순 정렬)
        """
        if not user_strategy_ids:
            return []

        result = await self.db.execute(
            select(DailyStrategy)
            .where(
                and_(
                    DailyStrategy.user_strategy_id.in_(user_strategy_ids),
                    func.date(DailyStrategy.timestamp) >= start_date,
                    func.date(DailyStrategy.timestamp) <= end_date,
                )
            )
            .order_by(DailyStrategy.timestamp.asc())
        )
        return list(result.scalars().all())

    async def get_user_strategy_by_id(
        self,
        strategy_id: int,
        account_id: int
    ) -> Optional[UserStrategy]:
        """
        전략 조회 (계좌 소유 확인)

        Args:
            strategy_id: UserStrategy ID
            account_id: 계좌 ID

        Returns:
            UserStrategy 또는 None
        """
        result = await self.db.execute(
            select(UserStrategy)
            .options(
                selectinload(UserStrategy.strategy_info),
                selectinload(UserStrategy.strategy_weight_type),
            )
            .where(
                UserStrategy.id == strategy_id,
                UserStrategy.account_id == account_id,
                UserStrategy.is_deleted == False,
            )
        )
        return result.scalar_one_or_none()

    async def update_user_strategy(
        self,
        strategy_id: int,
        account_id: int,
        update_data: Dict[str, Any]
    ) -> Optional[UserStrategy]:
        """
        전략 업데이트

        Args:
            strategy_id: UserStrategy ID
            account_id: 계좌 ID
            update_data: 업데이트할 필드들

        Returns:
            업데이트된 UserStrategy 또는 None (권한 없음)
        """
        user_strategy = await self.get_user_strategy_by_id(strategy_id, account_id)

        if not user_strategy:
            return None

        # 필드 업데이트
        for key, value in update_data.items():
            if hasattr(user_strategy, key) and value is not None:
                setattr(user_strategy, key, value)

        await self.db.commit()
        await self.db.refresh(user_strategy)

        return user_strategy

    async def deactivate_other_strategies(
        self,
        account_id: int,
        exclude_strategy_id: int
    ) -> None:
        """
        다른 전략들을 INACTIVE로 변경 (계좌당 하나의 ACTIVE 전략만 유지)

        Args:
            account_id: 계좌 ID
            exclude_strategy_id: 제외할 전략 ID (ACTIVE로 유지)
        """
        result = await self.db.execute(
            select(UserStrategy).where(
                UserStrategy.account_id == account_id,
                UserStrategy.id != exclude_strategy_id,
                UserStrategy.status == StrategyStatus.ACTIVE,
                UserStrategy.is_deleted == False,
            )
        )
        strategies = result.scalars().all()

        for strategy in strategies:
            strategy.status = StrategyStatus.INACTIVE

    async def soft_delete_user_strategy(
        self,
        strategy_id: int,
        account_id: int
    ) -> bool:
        """
        전략 소프트 삭제

        Args:
            strategy_id: UserStrategy ID
            account_id: 계좌 ID

        Returns:
            성공 여부
        """
        user_strategy = await self.get_user_strategy_by_id(strategy_id, account_id)

        if not user_strategy:
            return False

        user_strategy.is_auto = False
        user_strategy.status = StrategyStatus.INACTIVE
        user_strategy.is_deleted = True

        await self.db.commit()
        return True

    async def get_all_strategy_info(self) -> List[StrategyInfo]:
        """전략 정보 목록 조회"""
        result = await self.db.execute(select(StrategyInfo))
        return list(result.scalars().all())

    async def get_all_strategy_weight_types(self) -> List[StrategyWeightType]:
        """가중치 타입 목록 조회"""
        result = await self.db.execute(select(StrategyWeightType))
        return list(result.scalars().all())

    async def create_user_strategy(
        self,
        account_id: int,
        strategy_id: int,
        investment_weight: float,
        ls_ratio: float,
        tp_ratio: float,
        is_auto: bool,
        weight_type_id: Optional[int] = None
    ) -> UserStrategy:
        """
        전략 생성

        Args:
            account_id: 계좌 ID
            strategy_id: 전략 정보 ID
            investment_weight: 투자 비중
            ls_ratio: 손절 비율
            tp_ratio: 익절 비율
            is_auto: 자동 매매 여부
            weight_type_id: 가중치 타입 ID

        Returns:
            생성된 UserStrategy
        """
        # 해당 계좌에 활성 전략이 있는지 확인
        existing_active = await self.db.execute(
            select(UserStrategy).where(
                UserStrategy.account_id == account_id,
                UserStrategy.status == StrategyStatus.ACTIVE,
                UserStrategy.is_deleted != True,
            )
        )
        has_active = existing_active.scalar_one_or_none() is not None

        # 첫 번째 전략이면 ACTIVE, 아니면 INACTIVE
        initial_status = StrategyStatus.INACTIVE if has_active else StrategyStatus.ACTIVE

        user_strategy = UserStrategy(
            account_id=account_id,
            strategy_id=strategy_id,
            investment_weight=investment_weight,
            ls_ratio=ls_ratio,
            tp_ratio=tp_ratio,
            is_auto=is_auto,
            weight_type_id=weight_type_id,
            status=initial_status,
            is_deleted=False,
        )

        self.db.add(user_strategy)
        await self.db.commit()
        await self.db.refresh(user_strategy)

        # relationship 로드
        result = await self.db.execute(
            select(UserStrategy)
            .options(
                selectinload(UserStrategy.strategy_info),
                selectinload(UserStrategy.strategy_weight_type),
            )
            .where(UserStrategy.id == user_strategy.id)
        )
        return result.scalar_one()

    async def get_user_strategy_id_by_daily(self, daily_strategy_id: int) -> Optional[int]:
        """DailyStrategy ID에 해당하는 UserStrategy ID 조회"""
        result = await self.db.execute(
            select(DailyStrategy.user_strategy_id).where(DailyStrategy.id == daily_strategy_id)
        )
        return result.scalar_one_or_none()