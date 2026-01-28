"""
Candle Service - 비즈니스 로직 레이어
"""

import logging
from datetime import date, time
from typing import List, Dict, Any, Set
from collections import defaultdict

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.candle_repository import CandleRepository
from app.repositories.predict_repository import PredictRepository
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
        """분봉 데이터 조회 (DB에서 1분봉 가져와서 interval로 집계)"""
        # DB에서 1분봉 조회
        one_min_candles = await self.repo.get_minute_candles(stock_code, start_date, end_date)

        # 요청한 interval로 집계
        aggregated = self._aggregate_minute_candles(one_min_candles, minute_interval)

        # 시가/종가 조회 (end_date 기준)
        price_info = await self._get_price_info(stock_code, end_date)

        return {
            "stock_code": stock_code,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "minute_interval": minute_interval,
            "count": len(aggregated),
            "candles": aggregated,
            "open_price": price_info["open_price"],
            "close_price": price_info["close_price"],
        }

    async def get_today_minute_candles(
        self,
        stock_code: str,
        minute_interval: int = 1,
    ) -> Dict[str, Any]:
        """오늘 분봉 데이터 조회 (DB 1분봉 + 캐시 실시간 → interval로 집계)"""
        today = date.today()
        all_candles = []
        db_times: Set = set()

        # 1. DB에서 오늘 1분봉 조회 → interval로 집계
        try:
            one_min_candles = await self.repo.get_minute_candles_by_date(stock_code, today)
            aggregated = self._aggregate_minute_candles(one_min_candles, minute_interval)
            for c in aggregated:
                all_candles.append(c)
                db_times.add(c["candle_time"])
        except Exception as e:
            logger.error(f"Error fetching minute candles from DB: {e}", exc_info=True)

        # 2. 캐시에서 현재 시간 틱 데이터 → interval로 집계
        ticks = self.price_cache.get_ticks(stock_code)
        if ticks:
            cache_candles = aggregate_ticks_to_minute_candles(
                stock_code, ticks, today, minute_interval
            )
            for c in cache_candles:
                candle_time_str = c["candle_time"].strftime("%H:%M:%S")
                if candle_time_str not in db_times:
                    all_candles.append({
                        "candle_date": c["candle_date"].isoformat(),
                        "candle_time": candle_time_str,
                        "open": c["open"],
                        "high": c["high"],
                        "low": c["low"],
                        "close": c["close"],
                        "volume": c["volume"],
                        "trade_count": c["trade_count"],
                    })

        # 시간순 정렬
        all_candles.sort(key=lambda x: x["candle_time"])

        # 시가/종가 조회
        price_info = await self._get_price_info(stock_code, today)

        return {
            "stock_code": stock_code,
            "date": today.isoformat(),
            "minute_interval": minute_interval,
            "source": self._get_source(bool(db_times), bool(ticks)),
            "count": len(all_candles),
            "candles": all_candles,
            "open_price": price_info["open_price"],
            "close_price": price_info["close_price"],
        }

    def _aggregate_minute_candles(
        self,
        one_min_candles: List,
        minute_interval: int
    ) -> List[Dict[str, Any]]:
        """1분봉을 요청한 interval로 집계"""
        if minute_interval == 1:
            return [self._format_minute_candle(c) for c in one_min_candles]

        # interval별로 그룹핑
        groups: Dict[str, List] = defaultdict(list)
        for candle in one_min_candles:
            # candle_time을 interval에 맞게 정렬
            hh = candle.candle_time.hour
            mm = candle.candle_time.minute
            aligned_mm = (mm // minute_interval) * minute_interval
            key = f"{candle.candle_date.isoformat()}_{hh:02d}:{aligned_mm:02d}:00"
            groups[key].append(candle)

        # 각 그룹을 하나의 캔들로 집계
        result = []
        for key, candles in sorted(groups.items()):
            candle_date_str, candle_time_str = key.split("_")
            result.append({
                "candle_date": candle_date_str,
                "candle_time": candle_time_str,
                "open": candles[0].open,  # 첫 번째 캔들의 시가
                "high": max(c.high for c in candles),
                "low": min(c.low for c in candles),
                "close": candles[-1].close,  # 마지막 캔들의 종가
                "volume": sum(c.volume for c in candles),
                "trade_count": sum(c.trade_count for c in candles),
            })

        return result

    # ========================
    # Helper methods
    # ========================

    async def _get_price_info(self, stock_code: str, target_date: date) -> Dict[str, Any]:
        """시가/종가 조회 (GapPredictions 기반)"""
        predict_repo = PredictRepository(self.db)
        prediction = await predict_repo.get_prediction_by_stock_and_date(
            stock_code, target_date.isoformat()
        )

        return {
            "open_price": prediction.stock_open if prediction else None,
            "close_price": prediction.actual_close if prediction else None,
        }

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
