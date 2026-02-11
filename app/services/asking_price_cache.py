"""
실시간 호가 데이터 인메모리 캐시

종목별 최신 호가만 메모리에 저장
"""

import asyncio
import logging
from datetime import datetime, timedelta, date
from typing import Optional, Dict
from threading import Lock
from zoneinfo import ZoneInfo

from app.schemas.asking_price import AskingPriceMessage

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")
MARKET_CLOSE_HOUR = 8  # 익일 08시에 전일 캐시 정리


class AskingPriceCache:
    """실시간 호가 데이터 인메모리 캐시 (종목별 최신 호가만 유지)"""

    def __init__(self):
        # {stock_code: AskingPriceMessage} - 종목별 최신 호가만 저장
        self._cache: Dict[str, AskingPriceMessage] = {}
        self._cache_date: Optional[date] = None
        self._lock = Lock()
        self._cleanup_task: Optional[asyncio.Task] = None

    def _check_and_reset_if_new_day(self) -> None:
        """새로운 날이면 캐시 초기화"""
        today = datetime.now(KST).date()
        if self._cache_date != today:
            self._cache.clear()
            self._cache_date = today
            logger.info(f"Asking price cache reset for new day: {today}")

    async def start(self) -> None:
        """캐시 시작 및 정리 태스크 시작"""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_at_market_close())
            logger.info("Asking price cache cleanup task started")

    async def stop(self) -> None:
        """캐시 중지 및 정리 태스크 중지"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
        logger.info("Asking price cache stopped")

    def set(self, asking_price_msg: AskingPriceMessage) -> None:
        """
        호가 데이터 저장 (최신 데이터로 덮어쓰기)

        Args:
            asking_price_msg: 호가 메시지
        """
        with self._lock:
            self._check_and_reset_if_new_day()
            stock_code = asking_price_msg.stock_code
            self._cache[stock_code] = asking_price_msg

    def get(self, stock_code: str) -> Optional[AskingPriceMessage]:
        """특정 종목의 최신 호가 데이터 조회"""
        with self._lock:
            self._check_and_reset_if_new_day()
            return self._cache.get(stock_code)

    def get_all(self) -> Dict[str, AskingPriceMessage]:
        """모든 종목의 최신 호가 데이터 조회"""
        with self._lock:
            self._check_and_reset_if_new_day()
            return self._cache.copy()

    def get_best_prices(self, stock_code: str) -> Optional[Dict[str, str]]:
        """특정 종목의 최우선 호가 조회 (매도1호가, 매수1호가)"""
        with self._lock:
            self._check_and_reset_if_new_day()
            asking_price = self._cache.get(stock_code)
            if asking_price:
                return {
                    "askp1": asking_price.askp1,  # 매도1호가
                    "bidp1": asking_price.bidp1,  # 매수1호가
                    "askp_rsqn1": asking_price.askp_rsqn1,  # 매도1호가잔량
                    "bidp_rsqn1": asking_price.bidp_rsqn1,  # 매수1호가잔량
                }
            return None

    def delete(self, stock_code: str) -> bool:
        """호가 데이터 삭제"""
        with self._lock:
            if stock_code in self._cache:
                del self._cache[stock_code]
                logger.debug(f"Asking price deleted: stock_code={stock_code}")
                return True
            return False

    def clear(self) -> None:
        """모든 캐시 데이터 삭제"""
        with self._lock:
            stock_count = len(self._cache)
            self._cache.clear()
            logger.info(f"Asking price cache cleared: {stock_count} stocks removed")

    def size(self) -> int:
        """캐시에 저장된 종목 수 반환"""
        with self._lock:
            return len(self._cache)

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
                logger.info(f"Asking price cache will be cleared at {today_close} (in {wait_seconds:.0f} seconds)")

                await asyncio.sleep(wait_seconds)
                self.clear()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in asking price cache cleanup: {e}", exc_info=True)
                await asyncio.sleep(60)


# 싱글톤 인스턴스
_asking_price_cache_instance: Optional[AskingPriceCache] = None


def get_asking_price_cache() -> AskingPriceCache:
    """Asking Price Cache 싱글톤 인스턴스 반환"""
    global _asking_price_cache_instance
    if _asking_price_cache_instance is None:
        _asking_price_cache_instance = AskingPriceCache()
    return _asking_price_cache_instance
