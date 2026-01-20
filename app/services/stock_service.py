"""
Stock Service - 비즈니스 로직 레이어
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.database.stocks import StockMetadata
from app.database.database.strategy import UserStrategy
from app.repositories.stock_repository import StockRepository

logger = logging.getLogger(__name__)


class StockService:
    """주식 전략 관련 비즈니스 로직"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = StockRepository(db)

    async def create_user_strategy(
        self,
        user_id: int,
        strategy_id: int,
        ls_ratio: float,
        tp_ratio: float,
    ) -> UserStrategy:
        """
        사용자 전략 등록

        1. 전략 존재 여부 확인
        2. 중복 등록 체크
        3. 저장
        """
        # 전략 존재 확인
        strategy_info = await self.repo.get_strategy_info(strategy_id)
        if not strategy_info:
            raise ValueError("존재하지 않는 전략입니다")

        # 중복 체크
        existing = await self.repo.get_user_strategy(user_id, strategy_id)
        if existing:
            raise ValueError("이미 등록한 전략입니다")

        # 생성
        user_strategy = UserStrategy(
            user_id=user_id,
            strategy_id=strategy_id,
            ls_ratio=ls_ratio,
            tp_ratio=tp_ratio,
        )

        return await self.repo.create_user_strategy(user_strategy)

    async def get_user_strategies(self, user_id: int) -> list[UserStrategy]:
        """사용자의 전략 목록 조회"""
        return await self.repo.get_user_strategies(user_id)

    async def update_user_strategy(
        self,
        user_id: int,
        strategy_id: int,
        ls_ratio: float | None = None,
        tp_ratio: float | None = None,
        status: str | None = None,
        is_auto: bool | None = None,
    ) -> UserStrategy:
        """
        사용자 전략 업데이트

        1. 전략 존재 확인
        2. 사용자 전략 조회
        3. 업데이트
        """
        # 사용자 전략 조회
        user_strategy = await self.repo.get_user_strategy(user_id, strategy_id)
        if not user_strategy:
            raise ValueError("존재하지 않는 전략입니다")

        # 업데이트
        return await self.repo.update_user_strategy(
            user_strategy=user_strategy,
            ls_ratio=ls_ratio,
            tp_ratio=tp_ratio,
            status=status,
            is_auto=is_auto,
        )

    async def delete_user_strategy(self, user_id: int, strategy_id: int) -> bool:
        """사용자 전략 삭제"""
        user_strategy = await self.repo.get_user_strategy(user_id, strategy_id)
        if not user_strategy:
            return False

        await self.repo.delete_user_strategy(user_strategy)
        return True

    async def get_metadata(self, stock_code: str) -> StockMetadata | None:
        return await self.repo.get_metadata(stock_code)