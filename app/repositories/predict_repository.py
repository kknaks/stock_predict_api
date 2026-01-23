import logging
from datetime import date as date_type

from app.database.database.strategy import GapPredictions, StrategyInfo
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import DbSession

logger = logging.getLogger(__name__)


class PredictRepository:
    def __init__(self, db: DbSession):
        self.db = db

    async def get_predict_by_type_all(self, date: str) -> list[StrategyInfo]:
        """전략별로 그룹화하여 예측 목록 조회"""
        prediction_date = date_type.fromisoformat(date)

        result = await self.db.execute(
            select(StrategyInfo)
            .join(GapPredictions, StrategyInfo.id == GapPredictions.strategy_id)
            .where(GapPredictions.prediction_date == prediction_date)
            .distinct()
            .options(selectinload(StrategyInfo.gap_predictions))
        )
        strategies = list(result.scalars().all())
        logger.info(f"[predict_repo] Found {len(strategies)} strategies for date {date}")

        # 각 전략의 예측을 날짜로 필터링하고 정렬
        for strategy in strategies:
            before_count = len(strategy.gap_predictions)
            strategy.gap_predictions = [
                pred for pred in strategy.gap_predictions
                if pred.prediction_date == prediction_date
            ]
            logger.info(f"[predict_repo] Strategy {strategy.id}: {before_count} -> {len(strategy.gap_predictions)} predictions after date filter")
            strategy.gap_predictions.sort(key=lambda x: x.expected_return, reverse=True)

        return strategies

    async def get_predict_list(self, date: str) -> list[GapPredictions]:
        """예측 목록 조회"""
        # 문자열 날짜를 date 객체로 변환
        prediction_date = date_type.fromisoformat(date)

        result = await self.db.execute(
            select(GapPredictions)
            .where(GapPredictions.prediction_date == prediction_date)
            .order_by(GapPredictions.expected_return.desc())
        )
        return list(result.scalars().all())