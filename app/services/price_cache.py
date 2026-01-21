"""
실시간 가격 데이터 인메모리 캐시

매일 18시(KST)까지 가격 데이터를 메모리에 저장
하루 전체 틱 데이터를 리스트로 누적 저장
"""

import asyncio
import logging
from datetime import datetime, timedelta, date
from typing import Optional, Dict, List
from threading import Lock
from zoneinfo import ZoneInfo

from app.schemas.price import PriceMessage

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")
MARKET_CLOSE_HOUR = 18  # 18시까지 캐시 유지


class PriceCache:
    """실시간 가격 데이터 인메모리 캐시 (매일 18시 KST까지)"""

    def __init__(self):
        # {stock_code: [PriceMessage, PriceMessage, ...]} - 하루 전체 틱 데이터
        self._cache: Dict[str, List[PriceMessage]] = {}
        self._cache_date: Optional[date] = None  # 캐시 날짜
        self._lock = Lock()
        self._cleanup_task: Optional[asyncio.Task] = None

    def _check_and_reset_if_new_day(self) -> None:
        """새로운 날이면 캐시 초기화"""
        today = datetime.now(KST).date()
        if self._cache_date != today:
            self._cache.clear()
            self._cache_date = today
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

    def set(self, price_msg: PriceMessage) -> None:
        """
        가격 데이터 저장 (리스트에 추가)

        Args:
            price_msg: 가격 메시지
        """
        with self._lock:
            self._check_and_reset_if_new_day()

            stock_code = price_msg.stock_code
            if stock_code not in self._cache:
                self._cache[stock_code] = []

            self._cache[stock_code].append(price_msg)

            # logger.debug(
            #     f"Price cached: stock_code={stock_code}, "
            #     f"current_price={price_msg.current_price}, "
            #     f"total_ticks={len(self._cache[stock_code])}"
            # )

    def get(self, stock_code: str) -> Optional[PriceMessage]:
        """
        최신 가격 데이터 조회 (기존 SSE 호환)

        Args:
            stock_code: 종목 코드

        Returns:
            최신 가격 메시지 또는 None
        """
        with self._lock:
            self._check_and_reset_if_new_day()

            if stock_code not in self._cache or not self._cache[stock_code]:
                return None

            return self._cache[stock_code][-1]  # 마지막(최신) 데이터 반환

    def get_all(self) -> Dict[str, PriceMessage]:
        """
        모든 종목의 최신 가격 데이터 조회 (기존 호환)

        Returns:
            {stock_code: 최신 price_message} 딕셔너리
        """
        with self._lock:
            self._check_and_reset_if_new_day()

            result = {}
            for stock_code, ticks in self._cache.items():
                if ticks:
                    result[stock_code] = ticks[-1]
            return result

    def get_ticks(self, stock_code: str) -> List[PriceMessage]:
        """
        특정 종목의 전체 틱 데이터 조회

        Args:
            stock_code: 종목 코드

        Returns:
            틱 데이터 리스트
        """
        with self._lock:
            self._check_and_reset_if_new_day()
            return self._cache.get(stock_code, []).copy()

    def get_all_ticks(self) -> Dict[str, List[PriceMessage]]:
        """
        모든 종목의 전체 틱 데이터 조회 (시간봉 생성용)

        Returns:
            {stock_code: [tick1, tick2, ...]} 딕셔너리
        """
        with self._lock:
            self._check_and_reset_if_new_day()
            return {k: v.copy() for k, v in self._cache.items()}

    def get_tick_count(self, stock_code: str) -> int:
        """특정 종목의 틱 데이터 개수 반환"""
        with self._lock:
            return len(self._cache.get(stock_code, []))

    def delete(self, stock_code: str) -> bool:
        """
        가격 데이터 삭제

        Args:
            stock_code: 종목 코드

        Returns:
            삭제 성공 여부
        """
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
                # 오늘 18시
                today_close = now.replace(hour=MARKET_CLOSE_HOUR, minute=0, second=0, microsecond=0)

                if now >= today_close:
                    # 이미 18시 지났으면 내일 18시까지 대기
                    today_close += timedelta(days=1)

                wait_seconds = (today_close - now).total_seconds()
                logger.info(f"Price cache will be cleared at {today_close} (in {wait_seconds:.0f} seconds)")

                await asyncio.sleep(wait_seconds)
                self.clear()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in price cache cleanup: {e}", exc_info=True)
                await asyncio.sleep(60)  # 에러 시 1분 후 재시도


# 싱글톤 인스턴스
_price_cache_instance: Optional[PriceCache] = None


def get_price_cache() -> PriceCache:
    """Price Cache 싱글톤 인스턴스 반환"""
    global _price_cache_instance
    if _price_cache_instance is None:
        _price_cache_instance = PriceCache()
    return _price_cache_instance
