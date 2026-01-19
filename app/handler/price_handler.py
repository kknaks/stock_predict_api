"""
실시간 가격 데이터 핸들러

Kafka에서 받은 가격 데이터를 메모리 캐시에 저장
"""

import logging

from app.schemas.price import PriceMessage
from app.services.price_cache import get_price_cache

logger = logging.getLogger(__name__)


class PriceHandler:
    """실시간 가격 데이터 핸들러"""

    def __init__(self):
        self._price_cache = get_price_cache()

    async def handle_price(self, price_msg: PriceMessage) -> None:
        """
        가격 메시지 처리 (메모리 캐시에 저장)

        Args:
            price_msg: 가격 메시지
        """
        try:
            # 메모리 캐시에 저장 (TTL 10분)
            self._price_cache.set(price_msg)
            logger.debug(
                f"Price saved to cache: stock_code={price_msg.stock_code}, "
                f"current_price={price_msg.current_price}"
            )
        except Exception as e:
            logger.error(f"Error handling price message: {e}", exc_info=True)


# 싱글톤 인스턴스
_price_handler_instance = None


def get_price_handler() -> PriceHandler:
    """Price Handler 싱글톤 인스턴스 반환"""
    global _price_handler_instance
    if _price_handler_instance is None:
        _price_handler_instance = PriceHandler()
    return _price_handler_instance
