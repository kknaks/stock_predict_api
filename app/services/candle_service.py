"""
Candle Service - 비즈니스 로직 레이어
"""

import logging
from datetime import date
from typing import List, Dict, Any, Set

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.candle_repository import CandleRepository
from app.services.price_cache import get_price_cache
from app.handler.price_handler import aggregate_ticks_to_candle, aggregate_ticks_to_minute_candles

logger = logging.getLogger(__name__)


class CandleService:
    """캔들 데이터 비즈니스 로직"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = CandleRepository(db)
        self.price_cache = get_price_cache()

    # ========================
    # 시간봉
    # ========================

    async def get_hour_candles(
        self,
        stock_code: str,
        start_date: date,
        end_date: date,
    ) -> Dict[str, Any]:
        """시간봉 데이터 조회 (DB only)"""
        candles = await self.repo.get_hour_candles(stock_code, start_date, end_date)

        return {
            "stock_code": stock_code,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "count": len(candles),
            "candles": [self._format_hour_candle(c) for c in candles],
        }

    async def get_today_hour_candles(
        self,
        stock_code: str,
    ) -> Dict[str, Any]:
        """오늘 시간봉 데이터 조회 (DB + 캐시 실시간)"""
        today = date.today()
        all_candles = []
        db_hours: Set[int] = set()

        # 1. DB에서 오늘 저장된 시간봉 조회
        try:
            db_candles = await self.repo.get_hour_candles_by_date(stock_code, today)
            for c in db_candles:
                all_candles.append(self._format_hour_candle(c))
                db_hours.add(c.hour)
        except Exception as e:
            logger.error(f"Error fetching hour candles from DB: {e}", exc_info=True)

        # 2. 캐시에서 현재 시간 틱 데이터 → 시간봉 계산
        current_hour = self.price_cache.get_current_hour()
        ticks = self.price_cache.get_ticks(stock_code)

        if ticks and current_hour is not None and current_hour not in db_hours:
            candle = aggregate_ticks_to_candle(stock_code, ticks, today, current_hour)
            if candle:
                candle["candle_date"] = today.isoformat()
                all_candles.append(candle)

        # 시간순 정렬
        all_candles.sort(key=lambda x: x["hour"])

        return {
            "stock_code": stock_code,
            "date": today.isoformat(),
            "source": self._get_source(bool(db_hours), bool(ticks)),
            "current_hour": current_hour,
            "count": len(all_candles),
            "candles": all_candles,
        }

    # ========================
    # 분봉
    # ========================

    async def get_minute_candles(
        self,
        stock_code: str,
        start_date: date,
        end_date: date,
        minute_interval: int = 1,
    ) -> Dict[str, Any]:
        """분봉 데이터 조회 (DB only)"""
        candles = await self.repo.get_minute_candles(
            stock_code, start_date, end_date, minute_interval
        )

        return {
            "stock_code": stock_code,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "minute_interval": minute_interval,
            "count": len(candles),
            "candles": [self._format_minute_candle(c) for c in candles],
        }

    async def get_today_minute_candles(
        self,
        stock_code: str,
        minute_interval: int = 1,
    ) -> Dict[str, Any]:
        """오늘 분봉 데이터 조회 (DB + 캐시 실시간)"""
        today = date.today()
        all_candles = []
        db_times: Set = set()

        # 1. DB에서 오늘 저장된 분봉 조회
        try:
            db_candles = await self.repo.get_minute_candles_by_date(
                stock_code, today, minute_interval
            )
            for c in db_candles:
                all_candles.append(self._format_minute_candle(c))
                db_times.add(c.candle_time)
        except Exception as e:
            logger.error(f"Error fetching minute candles from DB: {e}", exc_info=True)

        # 2. 캐시에서 현재 시간 틱 데이터 → 분봉 계산
        ticks = self.price_cache.get_ticks(stock_code)
        if ticks:
            cache_candles = aggregate_ticks_to_minute_candles(
                stock_code, ticks, today, minute_interval
            )
            for c in cache_candles:
                if c["candle_time"] not in db_times:
                    all_candles.append({
                        "candle_date": c["candle_date"].isoformat(),
                        "candle_time": c["candle_time"].strftime("%H:%M:%S"),
                        "open": c["open"],
                        "high": c["high"],
                        "low": c["low"],
                        "close": c["close"],
                        "volume": c["volume"],
                        "trade_count": c["trade_count"],
                    })

        # 시간순 정렬
        all_candles.sort(key=lambda x: x["candle_time"])

        return {
            "stock_code": stock_code,
            "date": today.isoformat(),
            "minute_interval": minute_interval,
            "source": self._get_source(bool(db_times), bool(ticks)),
            "count": len(all_candles),
            "candles": all_candles,
        }

    # ========================
    # Helper methods
    # ========================

    def _format_hour_candle(self, candle) -> Dict[str, Any]:
        """시간봉 데이터 포맷팅"""
        return {
            "candle_date": candle.candle_date.isoformat(),
            "hour": candle.hour,
            "open": candle.open,
            "high": candle.high,
            "low": candle.low,
            "close": candle.close,
            "volume": candle.volume,
            "trade_count": candle.trade_count,
        }

    def _format_minute_candle(self, candle) -> Dict[str, Any]:
        """분봉 데이터 포맷팅"""
        return {
            "candle_date": candle.candle_date.isoformat(),
            "candle_time": candle.candle_time.strftime("%H:%M:%S"),
            "open": candle.open,
            "high": candle.high,
            "low": candle.low,
            "close": candle.close,
            "volume": candle.volume,
            "trade_count": candle.trade_count,
        }

    def _get_source(self, has_db: bool, has_cache: bool) -> str:
        """데이터 소스 문자열 반환"""
        if has_db and has_cache:
            return "db+cache"
        elif has_db:
            return "database"
        elif has_cache:
            return "cache"
        return "none"
