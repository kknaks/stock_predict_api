"""
실시간 가격 데이터 인메모리 캐시

매일 18시(KST)까지 가격 데이터를 메모리에 저장
"""

import asyncio
import logging
from datetime import datetime, timedelta, time
from typing import Optional, Dict
from threading import Lock
from zoneinfo import ZoneInfo

from app.schemas.price import PriceMessage

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")
MARKET_CLOSE_HOUR = 18  # 18시까지 캐시 유지


class PriceCache:
    """실시간 가격 데이터 인메모리 캐시 (매일 18시 KST까지)"""

    def __init__(self):
        # {stock_code: (price_data, expires_at)}
        self._cache: Dict[str, tuple[PriceMessage, datetime]] = {}
        self._lock = Lock()
        self._cleanup_task: Optional[asyncio.Task] = None

    def _get_expires_at(self) -> datetime:
        """오늘 18시(KST)까지 만료 시간 계산"""
        now = datetime.now(KST)
        today_close = now.replace(hour=MARKET_CLOSE_HOUR, minute=0, second=0, microsecond=0)

        # 이미 18시가 지났으면 내일 18시까지
        if now >= today_close:
            today_close += timedelta(days=1)

        return today_close

    async def start(self) -> None:
        """캐시 시작 및 정리 태스크 시작"""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_expired())
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
        가격 데이터 저장

        Args:
            price_msg: 가격 메시지
        """
        with self._lock:
            expires_at = self._get_expires_at()
            self._cache[price_msg.stock_code] = (price_msg, expires_at)
            logger.debug(
                f"Price cached: stock_code={price_msg.stock_code}, "
                f"current_price={price_msg.current_price}, "
                f"expires_at={expires_at}"
            )

    def get(self, stock_code: str) -> Optional[PriceMessage]:
        """
        가격 데이터 조회

        Args:
            stock_code: 종목 코드

        Returns:
            가격 메시지 또는 None (만료되었거나 없으면)
        """
        with self._lock:
            if stock_code not in self._cache:
                return None

            price_msg, expires_at = self._cache[stock_code]

            # 만료 확인 (KST 기준)
            if datetime.now(KST) >= expires_at:
                del self._cache[stock_code]
                logger.debug(f"Price expired and removed: stock_code={stock_code}")
                return None

            return price_msg

    def get_all(self) -> Dict[str, PriceMessage]:
        """
        모든 유효한 가격 데이터 조회

        Returns:
            {stock_code: price_message} 딕셔너리
        """
        with self._lock:
            result = {}
            now = datetime.now(KST)
            expired_keys = []

            for stock_code, (price_msg, expires_at) in self._cache.items():
                if now < expires_at:
                    result[stock_code] = price_msg
                else:
                    expired_keys.append(stock_code)

            # 만료된 항목 제거
            for key in expired_keys:
                del self._cache[key]

            return result

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
            count = len(self._cache)
            self._cache.clear()
            logger.info(f"Price cache cleared: {count} items removed")

    def size(self) -> int:
        """캐시에 저장된 항목 수 반환"""
        with self._lock:
            return len(self._cache)

    async def _cleanup_expired(self) -> None:
        """만료된 항목 정리 (백그라운드 태스크)"""
        while True:
            try:
                await asyncio.sleep(60)  # 1분마다 정리
                self._cleanup_expired_items()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in price cache cleanup: {e}", exc_info=True)

    def _cleanup_expired_items(self) -> None:
        """만료된 항목 제거"""
        with self._lock:
            now = datetime.now(KST)
            expired_keys = [
                stock_code
                for stock_code, (_, expires_at) in self._cache.items()
                if now >= expires_at
            ]

            for key in expired_keys:
                del self._cache[key]

            if expired_keys:
                logger.debug(f"Cleaned up {len(expired_keys)} expired price items")


# 싱글톤 인스턴스
_price_cache_instance: Optional[PriceCache] = None


def get_price_cache() -> PriceCache:
    """Price Cache 싱글톤 인스턴스 반환"""
    global _price_cache_instance
    if _price_cache_instance is None:
        _price_cache_instance = PriceCache()
    return _price_cache_instance
