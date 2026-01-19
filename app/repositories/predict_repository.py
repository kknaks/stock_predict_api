from datetime import date as date_type

from app.database.database.strategy import GapPredictions
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import DbSession


class PredictRepository:
    def __init__(self, db: DbSession):
        self.db = db

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