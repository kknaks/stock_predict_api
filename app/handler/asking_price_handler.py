"""
실시간 호가 데이터 핸들러

Kafka에서 받은 호가 데이터를 메모리 캐시에 저장
"""

import logging
from typing import Optional

from app.schemas.asking_price import AskingPriceMessage
from app.services.asking_price_cache import get_asking_price_cache

logger = logging.getLogger(__name__)


class AskingPriceHandler:
    """실시간 호가 데이터 핸들러"""

    def __init__(self):
        self._asking_price_cache = get_asking_price_cache()

    async def handle_asking_price(self, asking_price_msg: AskingPriceMessage) -> None:
        """
        호가 메시지 처리 - 메모리 캐시에 저장

        Args:
            asking_price_msg: 호가 메시지
        """
        try:
            self._asking_price_cache.set(asking_price_msg)
        except Exception as e:
            logger.error(f"Error handling asking price message: {e}", exc_info=True)


# 싱글톤 인스턴스
_asking_price_handler_instance: Optional[AskingPriceHandler] = None


def get_asking_price_handler() -> AskingPriceHandler:
    """Asking Price Handler 싱글톤 인스턴스 반환"""
    global _asking_price_handler_instance
    if _asking_price_handler_instance is None:
        _asking_price_handler_instance = AskingPriceHandler()
    return _asking_price_handler_instance
