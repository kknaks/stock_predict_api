"""
시간봉 캔들 생성 핸들러

STOP 신호를 받으면 캐시에 남아있는 마지막 시간 데이터를 시간봉으로 변환 후 DB 저장
"""

import logging
from datetime import datetime, date
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

from sqlalchemy.dialects.postgresql import insert

from app.config.db_connections import get_session_factory
from app.services.price_cache import get_price_cache
from app.schemas.price import PriceMessage
from app.kafka.websocket_command_consumer import WebSocketCommandMessage
from app.database.database.strategy import HourCandleData

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


class CandleHandler:
    """시간봉 캔들 생성 핸들러"""

    def __init__(self):
        self._price_cache = get_price_cache()
        self._session_factory = get_session_factory()

    async def handle_stop_command(self, command_msg: WebSocketCommandMessage) -> None:
        """
        STOP 명령 처리 - 캐시에 남아있는 마지막 시간 데이터를 시간봉으로 변환 후 DB 저장

        Args:
            command_msg: 웹소켓 명령 메시지
        """
        if command_msg.command != "STOP":
            return

        logger.info(f"Processing STOP command: {command_msg}")

        try:
            # 캐시에서 마지막 시간 데이터 추출 및 삭제
            current_hour, hour_data = self._price_cache.extract_all_data()

            if not hour_data or current_hour is None:
                logger.info("No tick data in cache to process")
                return

            # 장 시간 필터 (09:00 ~ 15:30)
            if current_hour < 9 or current_hour > 15:
                logger.info(f"Skipping hour {current_hour} (outside market hours)")
                return

            # 캐시 날짜 확인
            cache_date = self._price_cache.get_cache_date()
            if cache_date is None:
                cache_date = datetime.now(KST).date()

            logger.info(
                f"Processing last hour data: hour={current_hour}, "
                f"date={cache_date}, stocks={len(hour_data)}, "
                f"total_ticks={sum(len(t) for t in hour_data.values())}"
            )

            # 종목별로 시간봉 생성
            candles = []
            for stock_code, ticks in hour_data.items():
                candle = aggregate_ticks_to_candle(stock_code, ticks, cache_date, current_hour)
                if candle:
                    candles.append(candle)

            if not candles:
                logger.info("No candles generated from tick data")
                return

            # DB에 저장
            await self._save_candles_to_db(candles)
            logger.info(f"Successfully saved {len(candles)} hour candles for hour {current_hour}")

        except Exception as e:
            logger.error(f"Error processing STOP command: {e}", exc_info=True)

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


# 싱글톤 인스턴스
_candle_handler_instance: Optional[CandleHandler] = None


def get_candle_handler() -> CandleHandler:
    """Candle Handler 싱글톤 인스턴스 반환"""
    global _candle_handler_instance
    if _candle_handler_instance is None:
        _candle_handler_instance = CandleHandler()
    return _candle_handler_instance
