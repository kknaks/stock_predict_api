"""
실시간 가격 데이터 핸들러

Kafka에서 받은 가격 데이터를 메모리 캐시에 저장
시간이 바뀌면 직전 시간 데이터를 시간봉/분봉으로 만들어 DB 저장
"""

import asyncio
import logging
from datetime import date, datetime, time
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

from sqlalchemy.dialects.postgresql import insert

from app.schemas.price import PriceMessage
from app.services.price_cache import get_price_cache
from app.config.db_connections import get_session_factory
from app.database.database.strategy import HourCandleData, MinuteCandleData

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")


class HourCandleAggregator:
    """틱 데이터를 1시간봉으로 집계"""

    def __init__(self):
        self.open: Optional[float] = None
        self.high: Optional[float] = None
        self.low: Optional[float] = None
        self.close: Optional[float] = None
        self.volume: int = 0
        self.trade_count: int = 0

    def add_tick(self, price: float, volume: int) -> None:
        """틱 데이터 추가"""
        if self.open is None:
            self.open = price

        if self.high is None or price > self.high:
            self.high = price

        if self.low is None or price < self.low:
            self.low = price

        self.close = price
        self.volume += volume
        self.trade_count += 1

    def to_dict(self, stock_code: str, candle_date: date, hour: int) -> dict:
        """딕셔너리로 변환"""
        return {
            "stock_code": stock_code,
            "candle_date": candle_date,
            "hour": hour,
            "open": self.open or 0,
            "high": self.high or 0,
            "low": self.low or 0,
            "close": self.close or 0,
            "volume": self.volume,
            "trade_count": self.trade_count,
        }


def aggregate_ticks_to_candle(
    stock_code: str,
    ticks: List[PriceMessage],
    candle_date: date,
    hour: int
) -> Optional[dict]:
    """틱 데이터를 단일 시간봉으로 집계"""
    if not ticks:
        return None

    aggregator = HourCandleAggregator()

    for tick in ticks:
        try:
            price = float(tick.current_price)
            volume = int(tick.trade_volume)
            aggregator.add_tick(price, volume)
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid tick data: {e}")
            continue

    if aggregator.trade_count == 0:
        return None

    return aggregator.to_dict(stock_code, candle_date, hour)


def aggregate_ticks_to_minute_candles(
    stock_code: str,
    ticks: List[PriceMessage],
    candle_date: date,
    minute_interval: int = 1
) -> List[dict]:
    """틱 데이터를 분봉으로 집계"""
    if not ticks:
        return []

    # 분 단위로 그룹핑 (trade_time: HHMMSS -> HHMM)
    minute_groups: Dict[int, List[PriceMessage]] = {}
    for tick in ticks:
        minute_key = int(tick.trade_time[:4])  # HHMM
        if minute_key not in minute_groups:
            minute_groups[minute_key] = []
        minute_groups[minute_key].append(tick)

    candles = []
    for minute_key, minute_ticks in sorted(minute_groups.items()):
        aggregator = HourCandleAggregator()  # 같은 로직 재사용
        for tick in minute_ticks:
            try:
                price = float(tick.current_price)
                volume = int(tick.trade_volume)
                aggregator.add_tick(price, volume)
            except (ValueError, TypeError):
                continue

        if aggregator.trade_count > 0:
            hh, mm = divmod(minute_key, 100)
            candles.append({
                "stock_code": stock_code,
                "candle_date": candle_date,
                "candle_time": time(hh, mm, 0),
                "minute_interval": minute_interval,
                "open": aggregator.open or 0,
                "high": aggregator.high or 0,
                "low": aggregator.low or 0,
                "close": aggregator.close or 0,
                "volume": aggregator.volume,
                "trade_count": aggregator.trade_count,
            })

    return candles


class PriceHandler:
    """실시간 가격 데이터 핸들러"""

    def __init__(self):
        self._price_cache = get_price_cache()
        self._session_factory = get_session_factory()

    async def handle_price(self, price_msg: PriceMessage) -> None:
        """
        가격 메시지 처리
        - 메모리 캐시에 저장
        - 시간 변경 시 직전 시간 데이터를 시간봉으로 DB 저장

        Args:
            price_msg: 가격 메시지
        """
        try:
            # 캐시에 저장하고 시간 변경 여부 확인
            hour_changed, prev_hour, prev_hour_data = self._price_cache.set(price_msg)

            # 시간이 바뀌었으면 직전 시간 데이터를 시간봉/분봉으로 저장
            if hour_changed and prev_hour is not None and prev_hour_data:
                # 장 시간 필터 (09:00 ~ 15:30)
                if 9 <= prev_hour <= 15:
                    asyncio.create_task(
                        self._save_hour_candles(prev_hour, prev_hour_data)
                    )
                    asyncio.create_task(
                        self._save_minute_candles(prev_hour_data)
                    )

        except Exception as e:
            logger.error(f"Error handling price message: {e}", exc_info=True)

    async def _save_hour_candles(
        self,
        hour: int,
        hour_data: Dict[str, List[PriceMessage]]
    ) -> None:
        """
        시간봉 데이터를 DB에 저장

        Args:
            hour: 시간 (9, 10, 11, ...)
            hour_data: {stock_code: [ticks]} 딕셔너리
        """
        try:
            cache_date = self._price_cache.get_cache_date()
            if cache_date is None:
                cache_date = datetime.now(KST).date()

            logger.info(
                f"Saving hour candles: hour={hour}, date={cache_date}, "
                f"stocks={len(hour_data)}, "
                f"total_ticks={sum(len(t) for t in hour_data.values())}"
            )

            # 종목별로 시간봉 생성
            candles = []
            for stock_code, ticks in hour_data.items():
                candle = aggregate_ticks_to_candle(stock_code, ticks, cache_date, hour)
                if candle:
                    candles.append(candle)

            if not candles:
                logger.info(f"No candles generated for hour {hour}")
                return

            # DB에 저장
            await self._save_candles_to_db(candles)
            logger.info(f"Successfully saved {len(candles)} hour candles for hour {hour}")

        except Exception as e:
            logger.error(f"Error saving hour candles: {e}", exc_info=True)

    async def _save_candles_to_db(self, candles: List[dict]) -> None:
        """시간봉 데이터를 DB에 저장 (upsert)"""
        if HourCandleData is None:
            logger.error("HourCandleData model not available")
            return

        async with self._session_factory() as session:
            try:
                stmt = insert(HourCandleData).values(candles)
                stmt = stmt.on_conflict_do_update(
                    constraint='uq_hour_candle_stock_date_hour',
                    set_={
                        'open': stmt.excluded.open,
                        'high': stmt.excluded.high,
                        'low': stmt.excluded.low,
                        'close': stmt.excluded.close,
                        'volume': stmt.excluded.volume,
                        'trade_count': stmt.excluded.trade_count,
                    }
                )

                await session.execute(stmt)
                await session.commit()

            except Exception as e:
                await session.rollback()
                logger.error(f"Error saving candles to database: {e}", exc_info=True)
                raise

    async def _save_minute_candles(
        self,
        hour_data: Dict[str, List[PriceMessage]]
    ) -> None:
        """분봉 데이터를 DB에 저장"""
        try:
            cache_date = self._price_cache.get_cache_date()
            if cache_date is None:
                cache_date = datetime.now(KST).date()

            all_candles = []
            for stock_code, ticks in hour_data.items():
                candles = aggregate_ticks_to_minute_candles(stock_code, ticks, cache_date)
                all_candles.extend(candles)

            if not all_candles:
                logger.info("No minute candles generated")
                return

            await self._save_minute_candles_to_db(all_candles)
            logger.info(f"Successfully saved {len(all_candles)} minute candles")

        except Exception as e:
            logger.error(f"Error saving minute candles: {e}", exc_info=True)

    async def _save_minute_candles_to_db(self, candles: List[dict]) -> None:
        """분봉 데이터를 DB에 저장 (upsert)"""
        if MinuteCandleData is None:
            logger.error("MinuteCandleData model not available")
            return

        async with self._session_factory() as session:
            try:
                stmt = insert(MinuteCandleData).values(candles)
                stmt = stmt.on_conflict_do_update(
                    constraint='uq_minute_candle_stock_date_time_interval',
                    set_={
                        'open': stmt.excluded.open,
                        'high': stmt.excluded.high,
                        'low': stmt.excluded.low,
                        'close': stmt.excluded.close,
                        'volume': stmt.excluded.volume,
                        'trade_count': stmt.excluded.trade_count,
                    }
                )

                await session.execute(stmt)
                await session.commit()

            except Exception as e:
                await session.rollback()
                logger.error(f"Error saving minute candles to database: {e}", exc_info=True)
                raise


# 싱글톤 인스턴스
_price_handler_instance = None


def get_price_handler() -> PriceHandler:
    """Price Handler 싱글톤 인스턴스 반환"""
    global _price_handler_instance
    if _price_handler_instance is None:
        _price_handler_instance = PriceHandler()
    return _price_handler_instance
