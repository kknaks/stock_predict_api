"""
Candle Repository - DB 접근 레이어
"""

from datetime import date, time
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.database.strategy import HourCandleData, MinuteCandleData


class CandleRepository:
    """캔들 데이터 DB 접근"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ========================
    # 시간봉 조회
    # ========================

    async def get_hour_candles(
        self,
        stock_code: str,
        start_date: date,
        end_date: date,
    ) -> List[HourCandleData]:
        """시간봉 데이터 조회"""
        stmt = (
            select(HourCandleData)
            .where(HourCandleData.stock_code == stock_code)
            .where(HourCandleData.candle_date >= start_date)
            .where(HourCandleData.candle_date <= end_date)
            .order_by(HourCandleData.candle_date, HourCandleData.hour)
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_hour_candles_by_date(
        self,
        stock_code: str,
        candle_date: date,
    ) -> List[HourCandleData]:
        """특정 날짜의 시간봉 데이터 조회"""
        stmt = (
            select(HourCandleData)
            .where(HourCandleData.stock_code == stock_code)
            .where(HourCandleData.candle_date == candle_date)
            .order_by(HourCandleData.hour)
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    # ========================
    # 분봉 조회
    # ========================

    async def get_minute_candles(
        self,
        stock_code: str,
        start_date: date,
        end_date: date,
    ) -> List[MinuteCandleData]:
        """1분봉 데이터 조회 (DB에는 1분봉만 저장)"""
        stmt = (
            select(MinuteCandleData)
            .where(MinuteCandleData.stock_code == stock_code)
            .where(MinuteCandleData.candle_date >= start_date)
            .where(MinuteCandleData.candle_date <= end_date)
            .where(MinuteCandleData.minute_interval == 1)
            .order_by(MinuteCandleData.candle_date, MinuteCandleData.candle_time)
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_minute_candles_by_date(
        self,
        stock_code: str,
        candle_date: date,
    ) -> List[MinuteCandleData]:
        """특정 날짜의 1분봉 데이터 조회 (DB에는 1분봉만 저장)"""
        stmt = (
            select(MinuteCandleData)
            .where(MinuteCandleData.stock_code == stock_code)
            .where(MinuteCandleData.candle_date == candle_date)
            .where(MinuteCandleData.minute_interval == 1)
            .order_by(MinuteCandleData.candle_time)
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())
