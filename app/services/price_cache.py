"""
실시간 가격 데이터 인메모리 캐시

현재 시간의 틱 데이터만 메모리에 저장
시간이 바뀌면 직전 시간 데이터는 DB에 저장 후 삭제
"""

import asyncio
import logging
from datetime import datetime, timedelta, date
from typing import Optional, Dict, List, Tuple
from threading import Lock
from zoneinfo import ZoneInfo

from app.schemas.price import PriceMessage

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")
MARKET_CLOSE_HOUR = 18


def parse_trade_time_hour(trade_time: str) -> Optional[int]:
    """체결 시간에서 시간(hour) 추출 (HHMMSS -> HH)"""
    try:
        if trade_time and len(trade_time) >= 2:
            return int(trade_time[:2])
    except (ValueError, TypeError):
        pass
    return None


class PriceCache:
    """실시간 가격 데이터 인메모리 캐시 (현재 시간만 유지)"""

    def __init__(self):
        # {stock_code: [PriceMessage, ...]} - 현재 시간의 틱 데이터만 저장
        self._cache: Dict[str, List[PriceMessage]] = {}
        self._cache_date: Optional[date] = None
        self._current_hour: Optional[int] = None  # 현재 캐시에 저장된 시간
        self._lock = Lock()
        self._cleanup_task: Optional[asyncio.Task] = None

    def _check_and_reset_if_new_day(self) -> None:
        """새로운 날이면 캐시 초기화"""
        today = datetime.now(KST).date()
        if self._cache_date != today:
            self._cache.clear()
            self._cache_date = today
            self._current_hour = None
            logger.info(f"Price cache reset for new day: {today}")

    async def start(self) -> None:
        """캐시 시작 및 정리 태스크 시작"""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_at_market_close())
            logger.info("Price cache cleanup task started")

    async def stop(self) -> None:
        """캐시 중지 및 정리 태스크 중지"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
        logger.info("Price cache stopped")

    def set(self, price_msg: PriceMessage) -> Tuple[bool, Optional[int], Optional[Dict[str, List[PriceMessage]]]]:
        """
        가격 데이터 저장

        Args:
            price_msg: 가격 메시지

        Returns:
            (시간변경여부, 직전시간, 직전시간데이터)
            시간이 바뀌면 (True, prev_hour, {stock_code: [ticks]}) 반환
            시간이 안바뀌면 (False, None, None) 반환
        """
        current_hour = parse_trade_time_hour(price_msg.trade_time)
        if current_hour is None:
            return (False, None, None)

        with self._lock:
            self._check_and_reset_if_new_day()

            hour_changed = False
            prev_hour = None
            prev_hour_data = None

            # 시간이 바뀌었는지 확인
            if self._current_hour is not None and current_hour != self._current_hour:
                hour_changed = True
                prev_hour = self._current_hour
                # 직전 시간 데이터 추출 및 삭제
                prev_hour_data = {k: v.copy() for k, v in self._cache.items() if v}
                self._cache.clear()
                logger.info(
                    f"Hour changed: {prev_hour} -> {current_hour}, "
                    f"extracted {len(prev_hour_data)} stocks data"
                )

            self._current_hour = current_hour

            # 현재 시간 데이터 저장
            stock_code = price_msg.stock_code
            if stock_code not in self._cache:
                self._cache[stock_code] = []
            self._cache[stock_code].append(price_msg)

            return (hour_changed, prev_hour, prev_hour_data)

    def get(self, stock_code: str) -> Optional[PriceMessage]:
        """최신 가격 데이터 조회 (SSE용)"""
        with self._lock:
            self._check_and_reset_if_new_day()

            if stock_code not in self._cache or not self._cache[stock_code]:
                return None

            return self._cache[stock_code][-1]

    def get_all(self) -> Dict[str, PriceMessage]:
        """모든 종목의 최신 가격 데이터 조회"""
        with self._lock:
            self._check_and_reset_if_new_day()

            result = {}
            for stock_code, ticks in self._cache.items():
                if ticks:
                    result[stock_code] = ticks[-1]
            return result

    def get_ticks(self, stock_code: str) -> List[PriceMessage]:
        """특정 종목의 현재 시간 틱 데이터 조회"""
        with self._lock:
            self._check_and_reset_if_new_day()
            return self._cache.get(stock_code, []).copy()

    def get_all_ticks(self) -> Dict[str, List[PriceMessage]]:
        """모든 종목의 현재 시간 틱 데이터 조회"""
        with self._lock:
            self._check_and_reset_if_new_day()
            return {k: v.copy() for k, v in self._cache.items()}

    def get_current_hour(self) -> Optional[int]:
        """현재 캐시에 저장된 시간 반환"""
        return self._current_hour

    def get_tick_count(self, stock_code: str) -> int:
        """특정 종목의 틱 데이터 개수 반환"""
        with self._lock:
            return len(self._cache.get(stock_code, []))

    def extract_all_data(self) -> Tuple[Optional[int], Dict[str, List[PriceMessage]]]:
        """
        현재 캐시의 모든 데이터 추출 및 삭제 (STOP 명령용)

        Returns:
            (현재시간, {stock_code: [ticks]})
        """
        with self._lock:
            current_hour = self._current_hour
            data = {k: v.copy() for k, v in self._cache.items() if v}
            self._cache.clear()
            self._current_hour = None
            logger.info(f"Extracted all data: hour={current_hour}, stocks={len(data)}")
            return (current_hour, data)

    def delete(self, stock_code: str) -> bool:
        """가격 데이터 삭제"""
        with self._lock:
            if stock_code in self._cache:
                del self._cache[stock_code]
                logger.debug(f"Price deleted: stock_code={stock_code}")
                return True
            return False

    def clear(self) -> None:
        """모든 캐시 데이터 삭제"""
        with self._lock:
            total_ticks = sum(len(ticks) for ticks in self._cache.values())
            stock_count = len(self._cache)
            self._cache.clear()
            self._current_hour = None
            logger.info(f"Price cache cleared: {stock_count} stocks, {total_ticks} ticks removed")

    def size(self) -> int:
        """캐시에 저장된 종목 수 반환"""
        with self._lock:
            return len(self._cache)

    def total_ticks(self) -> int:
        """캐시에 저장된 전체 틱 수 반환"""
        with self._lock:
            return sum(len(ticks) for ticks in self._cache.values())

    def get_cache_date(self) -> Optional[date]:
        """캐시 날짜 반환"""
        return self._cache_date

    async def _cleanup_at_market_close(self) -> None:
        """18시에 캐시 정리 (백그라운드 태스크)"""
        while True:
            try:
                now = datetime.now(KST)
                today_close = now.replace(hour=MARKET_CLOSE_HOUR, minute=0, second=0, microsecond=0)

                if now >= today_close:
                    today_close += timedelta(days=1)

                wait_seconds = (today_close - now).total_seconds()
                logger.info(f"Price cache will be cleared at {today_close} (in {wait_seconds:.0f} seconds)")

                await asyncio.sleep(wait_seconds)
                self.clear()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in price cache cleanup: {e}", exc_info=True)
                await asyncio.sleep(60)


# 싱글톤 인스턴스
_price_cache_instance: Optional[PriceCache] = None


def get_price_cache() -> PriceCache:
    """Price Cache 싱글톤 인스턴스 반환"""
    global _price_cache_instance
    if _price_cache_instance is None:
        _price_cache_instance = PriceCache()
    return _price_cache_instance
