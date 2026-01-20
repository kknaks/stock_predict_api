"""
시간봉 캔들 생성 핸들러

STOP 신호를 받으면 캐시에서 틱 데이터를 가져와 1시간봉으로 변환 후 DB 저장
"""

import logging
from collections import defaultdict
from datetime import datetime, date
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.config.db_connections import get_session_factory
from app.services.price_cache import get_price_cache
from app.schemas.price import PriceMessage
from app.kafka.websocket_command_consumer import WebSocketCommandMessage
from app.database.database.strategy import HourCandleData

logger = logging.getLogger(__name__)


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


def parse_trade_time_hour(trade_time: str) -> Optional[int]:
    """
    체결 시간에서 시간(hour) 추출

    Args:
        trade_time: HHMMSS 형식 (예: "093015")

    Returns:
        시간 (9, 10, 11, ..., 15) 또는 None
    """
    try:
        if len(trade_time) >= 2:
            return int(trade_time[:2])
    except (ValueError, TypeError):
        pass
    return None


def aggregate_ticks_to_hour_candles(
    stock_code: str,
    ticks: List[PriceMessage],
    candle_date: date
) -> Dict[int, dict]:
    """
    틱 데이터를 시간별로 집계

    Args:
        stock_code: 종목 코드
        ticks: 틱 데이터 리스트
        candle_date: 캔들 날짜

    Returns:
        {hour: candle_dict} 딕셔너리
    """
    # 시간별 aggregator
    aggregators: Dict[int, HourCandleAggregator] = defaultdict(HourCandleAggregator)

    for tick in ticks:
        hour = parse_trade_time_hour(tick.trade_time)
        if hour is None:
            continue

        # 장 시간 필터 (09:00 ~ 15:30)
        if hour < 9 or hour > 15:
            continue

        try:
            price = float(tick.current_price)
            volume = int(tick.trade_volume)
            aggregators[hour].add_tick(price, volume)
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid tick data: {e}")
            continue

    # 결과 변환
    result = {}
    for hour, agg in aggregators.items():
        if agg.trade_count > 0:
            result[hour] = agg.to_dict(stock_code, candle_date, hour)

    return result


class CandleHandler:
    """시간봉 캔들 생성 핸들러"""

    def __init__(self):
        self._price_cache = get_price_cache()
        self._session_factory = get_session_factory()

    async def handle_stop_command(self, command_msg: WebSocketCommandMessage) -> None:
        """
        STOP 명령 처리 - 캐시 데이터를 시간봉으로 변환 후 DB 저장

        Args:
            command_msg: 웹소켓 명령 메시지
        """
        if command_msg.command != "STOP":
            return

        logger.info(f"Processing STOP command: {command_msg}")

        try:
            # 캐시에서 모든 틱 데이터 가져오기
            all_ticks = self._price_cache.get_all_ticks()

            if not all_ticks:
                logger.info("No tick data in cache to process")
                return

            # 캐시 날짜 확인
            cache_date = self._price_cache.get_cache_date()
            if cache_date is None:
                cache_date = datetime.now().date()

            logger.info(
                f"Processing tick data: "
                f"{len(all_ticks)} stocks, "
                f"{sum(len(t) for t in all_ticks.values())} total ticks, "
                f"date={cache_date}"
            )

            # 종목별로 시간봉 생성
            all_candles = []
            for stock_code, ticks in all_ticks.items():
                candles = aggregate_ticks_to_hour_candles(stock_code, ticks, cache_date)
                all_candles.extend(candles.values())
                logger.debug(f"Generated {len(candles)} hour candles for {stock_code}")

            if not all_candles:
                logger.info("No candles generated from tick data")
                return

            # DB에 저장
            await self._save_candles_to_db(all_candles)

            logger.info(f"Successfully saved {len(all_candles)} hour candles to database")

        except Exception as e:
            logger.error(f"Error processing STOP command: {e}", exc_info=True)

    async def _save_candles_to_db(self, candles: List[dict]) -> None:
        """
        시간봉 데이터를 DB에 저장 (upsert)

        Args:
            candles: 캔들 데이터 리스트
        """
        if HourCandleData is None:
            logger.error("HourCandleData model not available")
            return

        async with self._session_factory() as session:
            try:
                # PostgreSQL upsert (ON CONFLICT DO UPDATE)
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
