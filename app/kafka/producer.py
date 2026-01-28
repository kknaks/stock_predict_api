"""
Kafka Producer
"""

import json
import logging
from typing import Optional

from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaConnectionError

from app.config.kafka_connections import get_kafka_config

logger = logging.getLogger(__name__)


class KafkaProducer:
    """Kafka 메시지 프로듀서"""

    def __init__(self):
        self._config = get_kafka_config()
        self._producer: Optional[AIOKafkaProducer] = None

    async def start(self) -> bool:
        """Producer 시작"""
        try:
            self._producer = AIOKafkaProducer(
                bootstrap_servers=self._config.bootstrap_servers_list,
                value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
            )
            await self._producer.start()
            logger.info(f"Kafka producer started. Servers: {self._config.bootstrap_servers}")
            return True
        except KafkaConnectionError as e:
            logger.error(f"Failed to connect to Kafka: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error starting producer: {e}", exc_info=True)
            return False

    async def stop(self) -> None:
        """Producer 중지"""
        if self._producer:
            await self._producer.stop()
            logger.info("Kafka producer stopped")

    async def send(self, topic: str, message: dict) -> bool:
        """메시지 전송"""
        if not self._producer:
            logger.error("Producer not started")
            return False

        try:
            await self._producer.send_and_wait(topic, message)
            logger.info(f"Message sent to topic '{topic}': {message}")
            return True
        except Exception as e:
            logger.error(f"Failed to send message: {e}", exc_info=True)
            return False

    async def send_manual_sell_signal(self, message: dict) -> bool:
        """수동 매도 시그널 전송"""
        return await self.send(self._config.topic_manual_sell_signal, message)


_producer_instance: Optional[KafkaProducer] = None


def get_kafka_producer() -> KafkaProducer:
    """Kafka Producer 싱글톤 인스턴스 반환"""
    global _producer_instance
    if _producer_instance is None:
        _producer_instance = KafkaProducer()
    return _producer_instance
